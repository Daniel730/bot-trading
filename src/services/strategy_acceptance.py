"""Strategy Acceptance Protocol — objective gates before LIVE (research track).

Guards against selection bias: a candidate must pass statistical floors,
cost-aware metrics, robustness (±10% params), and walk-forward discipline
documented in the report — not just an impressive in-sample Sharpe.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional


@dataclass
class AcceptanceThresholds:
    min_sharpe: float = 1.0
    min_sortino: float = 1.2
    min_profit_factor: float = 1.3
    max_drawdown: float = 0.20  # fraction
    min_expectancy: float = 0.0  # per trade, same units as report
    min_trades: int = 50
    # Robustness: after ±10% param shock, metrics must stay within this relative drop
    max_robustness_sharpe_drop: float = 0.35  # 35% relative
    require_walk_forward: bool = True
    require_costs_modeled: bool = True
    require_oos_split: bool = True


@dataclass
class AcceptanceResult:
    accepted: bool
    checks: list[dict[str, Any]] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "checks": self.checks,
            "failures": self.failures,
            "warnings": self.warnings,
        }


def _num(report: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in report and report[key] is not None:
            return report[key]
        metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
        if key in metrics and metrics[key] is not None:
            return metrics[key]
    return default


def evaluate_strategy_report(
    report: Mapping[str, Any],
    *,
    thresholds: Optional[AcceptanceThresholds] = None,
) -> AcceptanceResult:
    """Evaluate a research report JSON against the Strategy Acceptance Protocol."""
    thr = thresholds or AcceptanceThresholds()
    result = AcceptanceResult(accepted=True)

    def check(name: str, ok: bool, detail: str, *, hard: bool = True) -> None:
        result.checks.append({"name": name, "ok": ok, "detail": detail, "hard": hard})
        if not ok:
            if hard:
                result.accepted = False
                result.failures.append(f"{name}: {detail}")
            else:
                result.warnings.append(f"{name}: {detail}")

    sharpe = float(_num(report, "sharpe", "Sharpe", default=0) or 0)
    sortino = float(_num(report, "sortino", "Sortino", default=0) or 0)
    pf = float(_num(report, "profit_factor", "profitFactor", default=0) or 0)
    mdd = abs(float(_num(report, "max_drawdown", "maxDrawdown", default=1) or 1))
    if mdd > 1.0:
        mdd = mdd / 100.0
    expectancy = float(_num(report, "expectancy", default=0) or 0)
    n_trades = int(_num(report, "n_trades", "trades", "trade_count", default=0) or 0)

    check("sharpe", sharpe >= thr.min_sharpe, f"{sharpe:.3f} >= {thr.min_sharpe}")
    check("sortino", sortino >= thr.min_sortino, f"{sortino:.3f} >= {thr.min_sortino}")
    check("profit_factor", pf >= thr.min_profit_factor, f"{pf:.3f} >= {thr.min_profit_factor}")
    check("max_drawdown", mdd <= thr.max_drawdown, f"{mdd:.3f} <= {thr.max_drawdown}")
    check("expectancy", expectancy > thr.min_expectancy, f"{expectancy} > {thr.min_expectancy}")
    check("min_trades", n_trades >= thr.min_trades, f"{n_trades} >= {thr.min_trades}")

    # Costs
    costs = report.get("costs") if isinstance(report.get("costs"), dict) else {}
    costs_ok = all(
        bool(costs.get(k))
        for k in ("spread", "slippage", "commission")
    ) or bool(report.get("costs_modeled"))
    check(
        "costs_modeled",
        costs_ok or not thr.require_costs_modeled,
        f"costs={costs or report.get('costs_modeled')}",
        hard=thr.require_costs_modeled,
    )
    if not costs.get("latency") and not report.get("latency_modeled"):
        result.warnings.append("latency: not modeled in report")
    if not costs.get("partial_fills") and not report.get("partial_fills_modeled"):
        result.warnings.append("partial_fills: not modeled in report")

    # Walk-forward / OOS discipline
    wf = report.get("walk_forward") if isinstance(report.get("walk_forward"), dict) else {}
    wf_ok = bool(wf.get("completed")) or bool(report.get("walk_forward_completed"))
    check(
        "walk_forward",
        wf_ok or not thr.require_walk_forward,
        f"walk_forward={wf or report.get('walk_forward_completed')}",
        hard=thr.require_walk_forward,
    )
    oos = report.get("out_of_sample") if isinstance(report.get("out_of_sample"), dict) else {}
    oos_ok = bool(oos.get("completed")) or bool(report.get("oos_completed"))
    check(
        "out_of_sample",
        oos_ok or not thr.require_oos_split,
        f"oos={oos or report.get('oos_completed')}",
        hard=thr.require_oos_split,
    )
    if wf.get("parameters_refit_on_test"):
        check(
            "no_lookahead_refit",
            False,
            "parameters were refit looking at the test window",
            hard=True,
        )

    # Robustness ±10%
    rob = report.get("robustness") if isinstance(report.get("robustness"), dict) else {}
    shocked = rob.get("param_shock_pm_10pct") if isinstance(rob.get("param_shock_pm_10pct"), dict) else {}
    if shocked:
        base = float(shocked.get("base_sharpe", sharpe) or sharpe)
        worst = float(shocked.get("worst_sharpe", base) or base)
        if base > 0:
            drop = (base - worst) / base
            check(
                "robustness_pm_10pct",
                drop <= thr.max_robustness_sharpe_drop,
                f"sharpe_drop={drop:.3f} <= {thr.max_robustness_sharpe_drop}",
            )
        else:
            check("robustness_pm_10pct", False, "base_sharpe non-positive")
    else:
        check(
            "robustness_pm_10pct",
            False,
            "missing robustness.param_shock_pm_10pct",
            hard=True,
        )

    # Selection-bias disclosure
    explored = report.get("search_space") if isinstance(report.get("search_space"), dict) else {}
    combos = int(explored.get("combinations_tested", 0) or 0)
    if combos > 100:
        result.warnings.append(
            f"selection_bias_risk: {combos} combinations tested — require multiple-testing correction / holdout"
        )
    if explored.get("multiple_testing_corrected") is False and combos > 20:
        check(
            "multiple_testing",
            False,
            "large search without multiple-testing correction",
            hard=True,
        )

    return result


def evaluate_strategy_report_file(path: str | Path, **kwargs: Any) -> AcceptanceResult:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return evaluate_strategy_report(data, **kwargs)
