"""Read-only signal-level reconciliation planner CLI."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from src.services.brokerage_service import BrokerageService
from src.services.ledger_reconcile_service import (
    log_signal_reconciliation_plans,
    plan_signal_level_reconciliation,
    signal_reconciliation_plan_to_dict,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("plan_signal_reconciliation")


async def main() -> int:
    brokerage = BrokerageService()
    result = await plan_signal_level_reconciliation(brokerage=brokerage)
    log_signal_reconciliation_plans(result)
    if "--json" in sys.argv[1:]:
        serializable = {
            "examined_rows": result.get("examined_rows"),
            "signal_count": result.get("signal_count"),
            "broker_ok": result.get("broker_ok"),
            "broker_error": result.get("broker_error"),
            "summary": result.get("summary"),
            "plans": [
                signal_reconciliation_plan_to_dict(plan)
                for plan in result.get("plans", [])
            ],
        }
        print(json.dumps(serializable, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
