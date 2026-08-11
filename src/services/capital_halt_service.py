"""Capital halt / daily-loss circuit breaker (audit F-002).

Stops *new* opens when:
- ``operational_status`` is already a pause / degraded state, or
- today's realized PnL loss exceeds ``MAX_DRAWDOWN`` of the reference capital, or
- rolling max drawdown from performance metrics meets ``MAX_DRAWDOWN``.

Does not auto-flatten open positions — that remains the financial kill-switch /
manual path. Shadow paper still enforces the gate so soak/paper mirrors live.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.config import settings

logger = logging.getLogger(__name__)

# States that must block new execute_trade opens.
_BLOCKING_OPERATIONAL_STATES = frozenset(
    {
        "PAUSED",
        "PAUSED_REQUIRES_MANUAL_REVIEW",
        "DEGRADED_MODE",
        "DAILY_LOSS_HALT",
        "MAX_DRAWDOWN_HALT",
    }
)


def reference_capital_usd() -> float:
    """Capital base for daily-loss % — prefer Alpaca budget, else paper starting cash."""
    budget = float(getattr(settings, "ALPACA_BUDGET_USD", 0.0) or 0.0)
    if budget > 0:
        return budget
    return float(getattr(settings, "PAPER_TRADING_STARTING_CASH", 10000.0) or 10000.0)


async def evaluate_capital_halt(
    *,
    persistence_service: Any,
    performance_service: Optional[Any] = None,
) -> dict[str, Any]:
    """Return ``{halt: bool, reason: str|None, details: dict}``."""
    details: dict[str, Any] = {}

    try:
        operational = await persistence_service.get_system_state("operational_status", "NORMAL")
    except Exception as exc:  # noqa: BLE001
        logger.warning("capital_halt: could not read operational_status: %s", exc)
        operational = "NORMAL"
    operational = (operational or "NORMAL").strip()
    details["operational_status"] = operational
    if operational in _BLOCKING_OPERATIONAL_STATES:
        return {
            "halt": True,
            "reason": f"operational_status:{operational}",
            "details": details,
        }

    today = datetime.now(timezone.utc).date().isoformat()
    try:
        daily_pnl = float(await persistence_service.get_daily_pnl_for_date(today) or 0.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("capital_halt: daily PnL unavailable: %s", exc)
        # Fail-closed for broker/live opens when PnL cannot be read (Phase-2 F-002 residual).
        if not bool(getattr(settings, "PAPER_TRADING", True)):
            return {
                "halt": True,
                "reason": "daily_pnl_unavailable",
                "details": {**details, "error": str(exc)},
            }
        daily_pnl = 0.0
    details["daily_pnl"] = daily_pnl
    details["date"] = today

    ref = reference_capital_usd()
    details["reference_capital"] = ref
    max_dd = float(getattr(settings, "MAX_DRAWDOWN", 0.10) or 0.10)
    details["max_drawdown_limit"] = max_dd

    if ref > 0 and daily_pnl < 0:
        loss_frac = abs(daily_pnl) / ref
        details["daily_loss_fraction"] = loss_frac
        if loss_frac >= max_dd:
            return {
                "halt": True,
                "reason": "daily_loss_exceeds_max_drawdown",
                "details": details,
            }

    if performance_service is not None:
        try:
            metrics = await performance_service.calculate_rolling_metrics()
            dd = metrics.get("max_drawdown")
            if dd is not None:
                dd_f = abs(float(dd))
                details["rolling_max_drawdown"] = dd_f
                # performance_service may return fraction (0.12) or already abs.
                if dd_f > 1.0:
                    dd_f = dd_f / 100.0
                if dd_f >= max_dd:
                    return {
                        "halt": True,
                        "reason": "rolling_max_drawdown_exceeds_limit",
                        "details": details,
                    }
        except Exception as exc:  # noqa: BLE001
            logger.warning("capital_halt: rolling metrics unavailable: %s", exc)

    # R-303: equity HWM / unrealized drawdown.
    # Under IGNORE_UNMANAGED_POSITIONS, track *managed* equity (broker equity minus
    # unmanaged MV) — same risk base as sizing_base (#149 / #150). Full broker
    # equity remains the base when ignore-unmanaged is off.
    equity_halt = await _evaluate_equity_drawdown(
        persistence_service=persistence_service,
        max_dd=max_dd,
        details=details,
    )
    if equity_halt is not None:
        return equity_halt

    return {"halt": False, "reason": None, "details": details}


async def _managed_equity_for_hwm(
    *,
    brokerage: Any,
    broker_equity: float,
    persistence_service: Any,
    details: dict[str, Any],
) -> Optional[float]:
    """Return equity used for HWM / drawdown, or None when probe must fail-close.

    Decision (#150): when ``IGNORE_UNMANAGED_POSITIONS`` is True on a broker path
    (``PAPER_TRADING=false``), HWM tracks managed equity = broker equity − unmanaged MV.
    Shadow paper keeps broker equity unchanged (no foreign-inventory probe).
    """
    details["broker_equity"] = broker_equity
    ignore_unmanaged = bool(getattr(settings, "IGNORE_UNMANAGED_POSITIONS", False))
    details["equity_base"] = "managed" if ignore_unmanaged and not bool(
        getattr(settings, "PAPER_TRADING", True)
    ) else "broker"

    if details["equity_base"] != "managed":
        details["unmanaged_mv"] = 0.0
        return broker_equity

    try:
        import inspect

        from src.services.unmanaged_positions_service import unmanaged_market_value

        maybe_positions = brokerage.get_positions()
        positions = (
            await maybe_positions if inspect.isawaitable(maybe_positions) else maybe_positions
        )
        open_signals = await persistence_service.get_open_signals()
        unmanaged_mv = float(unmanaged_market_value(positions or [], open_signals or []) or 0.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("capital_halt: unmanaged MV unavailable for managed HWM: %s", exc)
        details["error"] = str(exc)
        details["unmanaged_mv"] = None
        return None

    details["unmanaged_mv"] = unmanaged_mv
    return max(0.0, float(broker_equity) - unmanaged_mv)


async def _evaluate_equity_drawdown(
    *,
    persistence_service: Any,
    max_dd: float,
    details: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Halt when (HWM - current_equity) / HWM >= MAX_DRAWDOWN.

    Updates ``equity_high_water_mark`` in system_state when equity makes new highs.
    Fail-closed on broker/live when equity (or managed-equity inputs) cannot be read.
    """
    try:
        from src.services.brokerage_service import BrokerageService

        brokerage = BrokerageService()
        equity = await brokerage.get_account_equity()
        broker_equity = float(equity or 0.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("capital_halt: equity unavailable: %s", exc)
        if not bool(getattr(settings, "PAPER_TRADING", True)):
            return {
                "halt": True,
                "reason": "equity_unavailable",
                "details": {**details, "error": str(exc)},
            }
        return None

    equity_f = await _managed_equity_for_hwm(
        brokerage=brokerage,
        broker_equity=broker_equity,
        persistence_service=persistence_service,
        details=details,
    )
    if equity_f is None:
        if not bool(getattr(settings, "PAPER_TRADING", True)):
            return {
                "halt": True,
                "reason": "managed_equity_unavailable",
                "details": details,
            }
        return None

    details["current_equity"] = equity_f
    if equity_f <= 0:
        if not bool(getattr(settings, "PAPER_TRADING", True)):
            return {
                "halt": True,
                "reason": "equity_non_positive",
                "details": details,
            }
        return None

    try:
        raw_hwm = await persistence_service.get_system_state("equity_high_water_mark")
        hwm = float(raw_hwm) if raw_hwm is not None else 0.0
    except Exception:
        hwm = 0.0

    if equity_f > hwm:
        hwm = equity_f
        try:
            await persistence_service.set_system_state("equity_high_water_mark", str(hwm))
        except Exception as exc:  # noqa: BLE001
            logger.warning("capital_halt: failed to persist HWM: %s", exc)

    details["equity_high_water_mark"] = hwm
    if hwm > 0:
        dd_frac = max(0.0, (hwm - equity_f) / hwm)
        details["equity_drawdown_fraction"] = dd_frac
        if dd_frac >= max_dd:
            return {
                "halt": True,
                "reason": "equity_drawdown_exceeds_max_drawdown",
                "details": details,
            }
    return None


async def enforce_capital_halt_or_raise_state(
    *,
    persistence_service: Any,
    performance_service: Optional[Any] = None,
    notification_service: Optional[Any] = None,
) -> dict[str, Any]:
    """Evaluate halt; if newly tripped, persist ``DAILY_LOSS_HALT`` / drawdown state."""
    result = await evaluate_capital_halt(
        persistence_service=persistence_service,
        performance_service=performance_service,
    )
    if not result["halt"]:
        return result

    reason = result["reason"] or "capital_halt"
    # Do not overwrite an existing pause with a less specific label.
    current = result["details"].get("operational_status") or "NORMAL"
    if current in _BLOCKING_OPERATIONAL_STATES and not current.endswith("_HALT"):
        return result

    new_state = (
        "MAX_DRAWDOWN_HALT"
        if ("rolling_max_drawdown" in reason or "equity_drawdown" in reason)
        else "DAILY_LOSS_HALT"
        if "daily_loss" in reason
        else current
        if current in _BLOCKING_OPERATIONAL_STATES
        else "DAILY_LOSS_HALT"
    )
    try:
        if current not in _BLOCKING_OPERATIONAL_STATES:
            await persistence_service.set_system_state("operational_status", new_state)
            result["details"]["operational_status"] = new_state
            msg = (
                f"Capital halt engaged ({reason}). New opens blocked until "
                f"operational_status is cleared. details={result['details']}"
            )
            logger.critical(msg)
            if notification_service is not None:
                await notification_service.send_message(msg)
    except Exception as exc:  # noqa: BLE001
        logger.error("capital_halt: failed to persist halt state: %s", exc)
    return result
