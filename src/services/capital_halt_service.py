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

    return {"halt": False, "reason": None, "details": details}


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
        if "rolling_max_drawdown" in reason
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
