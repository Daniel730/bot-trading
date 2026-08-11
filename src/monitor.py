import asyncio
import json
import logging
import math
from rich.logging import RichHandler
from rich.console import Console
from rich.theme import Theme
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta, timezone
from pathlib import Path
from src.config import settings
from src.services.data_service import data_service
from src.services.arbitrage_service import arbitrage_service, ArbitrageService
from src.services.budget_service import budget_service
from src.services.persistence_service import persistence_service, OrderSide, OrderStatus
from src.services.redis_service import redis_service
from src.agents.orchestrator import orchestrator
from src.services.shadow_service import shadow_service
from src.services.notification_service import notification_service
from src.services.audit_service import audit_service
from src.services.risk_service import risk_service
from src.services.market_regime_service import market_regime_service
from src.services.brokerage_service import BrokerageService
from src.services.pair_eligibility_service import filter_pair_universe
from src.services.venue_metadata import estimate_round_trip_cost_pct
from src.services.persistence_service import ExitReason
from src.services.dashboard_service import dashboard_service, dashboard_state
from src.services.background_task_watchdog import background_task_watchdog
from src.services.decision_trace_service import decision_recorder
from src.services.trade_math import (
    build_pair_legs,
    cap_pair_notional,
    estimate_pair_profit,
    is_broker_fill_complete,
)
import gc
import uuid
import pytz
import inspect
from src.monitor_helpers import (
    is_crypto_pair,
    is_executable_bid_ask,
    normalize_history_close_frame,
    resolve_history_column,
    resolve_pair_sector,
    resolve_kalman_pair_id,
    resolve_hedge_ratio,
    resolve_profit_guard_friction_pct,
    compute_entry_zscore,
    should_take_profit_exit,
    prune_active_signals,
    prune_dict_to_keys,
    rotate_jsonl_if_large,
    evict_ttl_cache,
)
from src.monitor_scan_helpers import (
    build_candidate_pairs,
    build_scan_pairs,
    gather_bounded,
    normalize_scan_results,
    open_signal_tickers,
    summarize_scan_funnel,
    summarize_scan_iteration,
    build_close_orders,
    calculate_realized_pnl,
)
from src.services.execution_lane import (
    LANE_SHADOW,
    close_uses_broker,
    signal_is_shadow,
)

# Initialize Rich Console with a custom theme
custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "critical": "bold white on red",
    "success": "bold green",
    "scan": "magenta",
    "signal": "bold yellow",
    "trade": "bold blue"
})
console = Console(theme=custom_theme)
log_console = Console(theme=custom_theme, stderr=True)
STRUCTURED_LOG_PATH = Path("logs") / "structured_logs.jsonl"


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

# Disable yfinance cache or use a cross-platform temp path
import tempfile
import os
yf_cache_path = os.path.join(tempfile.gettempdir(), "yf_cache")
yf.set_tz_cache_location(yf_cache_path)

# Configure logging
def _resolve_log_level(raw_level: str) -> int:
    level_name = str(raw_level or "INFO").strip().upper()
    return logging._nameToLevel.get(level_name, logging.INFO)


def setup_logging():
    # Remove existing handlers
    """
    Configure the root Python logger to use Rich for formatted console output and reduce noise from common third-party libraries.

    This function clears any existing root logger handlers, installs a RichHandler that displays message-only output with timestamps and paths, sets the root logger level from `LOG_LEVEL`, and lowers verbosity for `urllib3` and `yfinance`.

    Returns:
        logging.Logger: A logger scoped to this module's __name__.
    """
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Rich logging handler
    rich_handler = RichHandler(
        console=log_console,
        rich_tracebacks=True,
        markup=True,
        show_time=True,
        show_path=True
    )
    rich_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(rich_handler)
    STRUCTURED_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    structured_handler = logging.FileHandler(STRUCTURED_LOG_PATH, encoding="utf-8")
    structured_handler.setFormatter(JsonLineFormatter())
    root_logger.addHandler(structured_handler)
    root_logger.setLevel(_resolve_log_level(settings.LOG_LEVEL))

    # Silence some noisy loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.ERROR)

    return logging.getLogger(__name__)

logger = setup_logging()

KALMAN_BETA_CLIP_MIN = 0.001
KALMAN_BETA_CLIP_MAX = 1000.0
KALMAN_MAX_REASONABLE_ABS_ZSCORE = 100.0
SPREAD_GUARD_DETAIL_FIELDS = (
    "bid_a",
    "ask_a",
    "bid_b",
    "ask_b",
    "spread_a_pct",
    "spread_b_pct",
    "total_spread_pct",
    "max_spread_pct",
)
PROFIT_GUARD_DETAIL_FIELDS = (
    "profit_guard_net_profit",
    "profit_guard_gross_profit",
    "profit_guard_friction_usd",
    "profit_guard_profit_margin_pct",
    "profit_guard_expected_loss",
    "profit_guard_loss_margin_pct",
    "profit_guard_spread_capture",
    "profit_guard_stop_spread_move",
    "profit_guard_friction_pct",
    "profit_guard_gross_notional",
    "profit_guard_quantity_a",
    "profit_guard_quantity_b",
    "profit_guard_notional_a",
    "profit_guard_notional_b",
    "profit_guard_side_a",
    "profit_guard_side_b",
    "profit_guard_direction",
    "profit_guard_z_score",
    "profit_guard_spread",
    "profit_guard_innovation_variance",
    "profit_guard_take_profit_zscore",
    "profit_guard_stop_loss_zscore",
)
TRADE_DECISION_DETAIL_FIELDS = SPREAD_GUARD_DETAIL_FIELDS + PROFIT_GUARD_DETAIL_FIELDS
CRYPTO_PRICE_SANITY_RANGES = {
    "BTC-USD": (10_000.0, 1_000_000.0),
    "ETH-USD": (100.0, 20_000.0),
    "LTC-USD": (10.0, 1_000.0),
    "BCH-USD": (50.0, 5_000.0),
    "SOL-USD": (1.0, 1_000.0),
    "AVAX-USD": (1.0, 500.0),
    "ADA-USD": (0.01, 10.0),
    "DOT-USD": (0.1, 100.0),
    "LINK-USD": (0.5, 200.0),
    "XRP-USD": (0.01, 50.0),
    "XLM-USD": (0.001, 10.0),
    "DOGE-USD": (0.001, 10.0),
    "SHIB-USD": (0.00000001, 0.01),
}
# Floor for price-only unchanged-marker repeats (no trade/quote timestamp).
CRYPTO_SNAPSHOT_STALE_REPEAT_LIMIT = 5
# Target wall-clock span before price-only repeats trip, scaled by SCAN_INTERVAL.
CRYPTO_SNAPSHOT_STALE_TARGET_SECONDS = 120
# Absolute max age for Alpaca crypto trade/quote timestamps vs wall clock.
# Quiet markets may keep the same mid for several scans; age—not identity—is the
# true staleness signal when metadata is present (shared scan snapshot pacing).
CRYPTO_PRICE_MAX_AGE_SECONDS = 180


def crypto_stale_repeat_limit(scan_interval_seconds: int) -> int:
    """Repeats so price-only unchanged markers span ~CRYPTO_SNAPSHOT_STALE_TARGET_SECONDS."""
    interval = max(1, int(scan_interval_seconds))
    return max(
        CRYPTO_SNAPSHOT_STALE_REPEAT_LIMIT,
        int(math.ceil(CRYPTO_SNAPSHOT_STALE_TARGET_SECONDS / interval)),
    )


def crypto_price_max_age_seconds(scan_interval_seconds: int) -> float:
    """Absolute quote/trade age budget, never tighter than ~8 scan cycles."""
    interval = max(1, int(scan_interval_seconds))
    return float(max(CRYPTO_PRICE_MAX_AGE_SECONDS, 8 * interval))


def parse_price_timestamp(value) -> datetime | None:
    """Parse ISO / pandas-like price timestamps to timezone-aware UTC."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    try:
        timestamp = pd.Timestamp(value)
        if pd.isna(timestamp):
            return None
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize(timezone.utc)
        else:
            timestamp = timestamp.tz_convert(timezone.utc)
        return timestamp.to_pydatetime()
    except Exception:
        return None


def crypto_leg_freshness_marker(
    ticker: str,
    price: float,
    price_timestamps: dict,
) -> tuple[str, float | str]:
    """Prefer trade/quote timestamp; fall back to price when metadata is absent."""
    raw_ts = price_timestamps.get(ticker) if price_timestamps else None
    if raw_ts is not None and str(raw_ts).strip():
        return ("ts", str(raw_ts))
    return ("price", float(price))


class ArbitrageMonitor:
    def __init__(self, mode: str = "live"):
        self.brokerage = BrokerageService()
        self.mode = mode
        self.active_pairs = []
        self.active_signals = []
        # PATCH 3b: Initialize eagerly — reload_pairs acquires this before any
        # signal is processed, so lazy init causes AttributeError on first restart.
        self._signals_lock: asyncio.Lock = asyncio.Lock()
        self.last_dev_warning = datetime.min
        self.current_day = None
        self.daily_start_cash = 0.0
        self.daily_halted = False
        # Tracks the calendar date on which each pair's cointegration was last
        # re-validated. Keyed by pair_id; value is a datetime.date object.
        self.last_cointegration_check: dict = {}
        # Tracks which pairs have had their Kalman uncertainty bumped today.
        self.bumped_pairs_today: dict = {}
        self.kalman_quarantined_pairs: set[str] = set()
        self._kalman_quarantine_reload_requested = False
        # Pairs whose one-shot historical rebuild has already been attempted.
        # Prevents structurally-untradeable pairs (e.g. hedge ratio beyond the
        # beta clip) from being re-quarantined and triggering a full pair reload
        # every scan cycle — which otherwise resets the dashboard stage back to
        # "pre_warming" forever and re-fetches 30d history on a loop.
        self._kalman_rebuild_attempted: set[str] = set()
        # pair_id -> (freshness_marker_pair, consecutive_unchanged_count)
        self._crypto_snapshot_pair_prices: dict[str, tuple[tuple, int]] = {}
        # In-memory lock set for closing positions to prevent duplicate broker orders
        self._closing_signals: set = set()
        # Serialize heavy daily cointegration history pulls on shared Mini PC hosts.
        self._coint_recheck_sem = asyncio.Semaphore(
            max(1, int(settings.SCAN_COINT_RECHECK_CONCURRENCY))
        )
        self.trade_decision_report_path = Path("logs") / "trade_decision_reports.jsonl"

    async def _await_order_fill(self, order_id: str, timeout: float = 30) -> dict | None:
        """PATCH 5: Poll Alpaca until order_id is filled or timeout elapses.

        Returns normalized order snapshot when terminal (filled/partial/rejected),
        else None on timeout/error.
        """
        import time
        deadline = time.monotonic() + timeout
        poll_interval = 2.0
        while time.monotonic() < deadline:
            try:
                orders = await self.brokerage.get_pending_orders()
                matching = [o for o in orders if str(o.get("id")) == str(order_id)]
                if not matching:
                    get_order = getattr(self.brokerage, "get_order", None)
                    if get_order:
                        snap = await get_order(order_id)
                        if snap:
                            return snap
                    logger.warning(
                        "Order %s is not open, but no order snapshot confirmed its terminal state.",
                        order_id,
                    )
                    return None
                order_status = matching[0].get("status", "").lower()
                if order_status == "filled":
                    return matching[0]
                if order_status in ("partially_filled", "partial_fill"):
                    return matching[0]
                if order_status in ("cancelled", "canceled", "expired", "rejected"):
                    logger.error("Order %s ended in non-fill status: %s", order_id, order_status)
                    return matching[0]
            except Exception as exc:
                logger.warning("_await_order_fill poll error for %s: %s", order_id, exc)
            await asyncio.sleep(poll_interval)
        return None  # timeout

    async def _upsert_active_signal(
        self,
        ticker_a: str,
        ticker_b: str,
        *,
        z_score: float,
        status: str,
        confidence: float | None = None,
        hedge_ratio: float | None = None,
    ) -> None:
        """Keep dashboard-facing signal state live for z-score and confidence."""
        if self._signals_lock is None:
            self._signals_lock = asyncio.Lock()
        async with self._signals_lock:
            signal_entry = next(
                (s for s in self.active_signals if s["ticker_a"] == ticker_a and s["ticker_b"] == ticker_b),
                None,
            )
            if signal_entry is None:
                signal_entry = {"ticker_a": ticker_a, "ticker_b": ticker_b}
                self.active_signals.append(signal_entry)
            signal_entry["z_score"] = z_score
            signal_entry["status"] = status
            if confidence is not None:
                signal_entry["confidence"] = confidence
            if hedge_ratio is not None:
                signal_entry["hedge_ratio"] = hedge_ratio

    async def _remove_active_signal(self, ticker_a: str, ticker_b: str) -> None:
        if self._signals_lock is None:
            self._signals_lock = asyncio.Lock()
        async with self._signals_lock:
            self.active_signals = [
                s
                for s in self.active_signals
                if not (s["ticker_a"] == ticker_a and s["ticker_b"] == ticker_b)
            ]

    async def _has_active_pair_or_pending_order(
        self,
        ticker_a: str,
        ticker_b: str,
        *,
        notify: bool = True,
    ) -> bool:
        pair_symbols = {
            self._canonical_position_symbol(ticker_a),
            self._canonical_position_symbol(ticker_b),
        }
        try:
            open_signals = await persistence_service.get_open_signals()
        except Exception as exc:
            msg = (
                f"Execution blocked for {ticker_a}/{ticker_b}: could not verify "
                f"open ledger positions ({exc})."
            )
            logger.critical(msg)
            if notify:
                await notification_service.send_message(msg)
            return True

        # F-015 / Phase-4: treat in-flight reservations as occupied slots (Postgres authority).
        try:
            from src.services.open_slot_reservation import open_slot_reservation_service

            open_signals = list(open_signals or []) + await open_slot_reservation_service.active_as_open_signals_async()
        except Exception as exc:  # noqa: BLE001
            if settings.PAPER_TRADING or settings.should_auto_approve_trades:
                logger.warning(
                    "Reservation store unavailable in paper lane (continuing): %s",
                    exc,
                )
            else:
                logger.critical(
                    "Could not load distributed open-slot reservations (fail-closed): %s",
                    exc,
                )
                if notify:
                    await notification_service.send_message(
                        f"Execution blocked for {ticker_a}/{ticker_b}: reservation store unavailable."
                    )
                return True

        for signal in open_signals or []:
            leg_symbols = {
                self._canonical_position_symbol(leg.get("ticker"))
                for leg in signal.get("legs", [])
                if leg.get("ticker")
            }
            if pair_symbols.issubset(leg_symbols):
                msg = (
                    f"Duplicate entry blocked for {ticker_a}/{ticker_b}: "
                    f"active ledger signal {signal.get('signal_id')} already covers this pair."
                )
                logger.warning(msg)
                if notify:
                    await notification_service.send_message(msg)
                return True

        if settings.BLOCK_SHARED_LEG_OPENS:
            from src.services.portfolio_book_guards import find_shared_leg_conflict

            conflict = find_shared_leg_conflict(
                ticker_a,
                ticker_b,
                open_signals,
                canonicalize=self._canonical_position_symbol,
            )
            if conflict:
                msg = (
                    f"Shared-leg entry blocked for {ticker_a}/{ticker_b}: "
                    f"overlap {conflict['overlap']} with open signal "
                    f"{conflict.get('signal_id')}."
                )
                logger.warning(msg)
                if notify:
                    await notification_service.send_message(msg)
                return True

        open_count = len(open_signals or [])
        from src.services.portfolio_book_guards import check_max_open_pairs

        slot_check = check_max_open_pairs(open_count, settings.MAX_OPEN_PAIRS)
        if not slot_check["allowed"]:
            msg = (
                f"Open-pair slot limit blocked for {ticker_a}/{ticker_b}: "
                f"{slot_check['reason']}."
            )
            logger.warning(msg)
            if notify:
                await notification_service.send_message(msg)
            return True

        # Undetermined / manual ledger exposure must block new opens even when
        # those rows are excluded from get_open_signals (no TP/SL path).
        try:
            unresolved = await persistence_service.get_unresolved_exposure_tickers()
        except Exception as exc:
            msg = (
                f"Execution blocked for {ticker_a}/{ticker_b}: could not verify "
                f"unresolved ledger exposure ({exc})."
            )
            logger.critical(msg)
            if notify:
                await notification_service.send_message(msg)
            return True

        for row in unresolved or []:
            row_sym = self._canonical_position_symbol(row.get("ticker"))
            if row_sym and row_sym in pair_symbols:
                msg = (
                    f"Execution blocked for {ticker_a}/{ticker_b}: unresolved "
                    f"ledger exposure on {row.get('ticker')} "
                    f"(status={row.get('status')}, signal={row.get('signal_id')}). "
                    "Reconcile before opening new exposure."
                )
                logger.critical(msg)
                if notify:
                    await notification_service.send_message(msg)
                return True

        if settings.PAPER_TRADING:
            return False

        try:
            pending_orders = await self.brokerage.get_pending_orders()
        except Exception as exc:
            msg = (
                f"Execution blocked for {ticker_a}/{ticker_b}: could not verify "
                f"pending broker orders ({exc})."
            )
            logger.critical(msg)
            if notify:
                await notification_service.send_message(msg)
            return True

        for order in pending_orders or []:
            raw_symbol = (
                order.get("ticker")
                or order.get("symbol")
                or order.get("instrumentTicker")
                or order.get("instrument")
            )
            if self._canonical_position_symbol(raw_symbol) in pair_symbols:
                msg = (
                    f"Duplicate entry blocked for {ticker_a}/{ticker_b}: "
                    f"pending broker order exists for {raw_symbol}."
                )
                logger.warning(msg)
                if notify:
                    await notification_service.send_message(msg)
                return True

        # Broker-only inventory on a proposed leg: IGNORE_UNMANAGED continues
        # scanning, but must never average into / re-enter overlapping symbols.
        try:
            broker_positions = await self.brokerage.get_positions()
        except Exception as exc:
            msg = (
                f"Execution blocked for {ticker_a}/{ticker_b}: could not verify "
                f"broker positions ({exc})."
            )
            logger.critical(msg)
            if notify:
                await notification_service.send_message(msg)
            return True

        ledger_leg_symbols = set()
        for signal in open_signals or []:
            for leg in signal.get("legs", []) or []:
                sym = self._canonical_position_symbol(leg.get("ticker"))
                if sym:
                    ledger_leg_symbols.add(sym)

        for pos in broker_positions or []:
            raw_symbol = (
                pos.get("ticker")
                or pos.get("symbol")
                or pos.get("instrumentTicker")
                or pos.get("instrument")
            )
            canonical = self._canonical_position_symbol(raw_symbol)
            if not canonical or canonical not in pair_symbols:
                continue
            qty = float(
                pos.get("quantityAvailableForTrading")
                if pos.get("quantityAvailableForTrading") is not None
                else pos.get("quantity")
                or 0.0
            )
            if abs(qty) <= 1e-12:
                continue
            if canonical not in ledger_leg_symbols:
                msg = (
                    f"Execution blocked for {ticker_a}/{ticker_b}: broker holds "
                    f"unmanaged inventory on {raw_symbol} (qty={qty}). "
                    "Close or acknowledge and keep IGNORE_UNMANAGED from averaging "
                    "into foreign inventory."
                )
                logger.critical(msg)
                if notify:
                    await notification_service.send_message(msg)
                return True

        return False

    def get_market_config(self, ticker: str) -> dict:
        """
        Returns the market window and timezone for a given ticker.
        Supported: .HK (Hong Kong), .DE/.AS/.PA/.L (Europe), Default (US).
        """
        ticker = ticker.upper()
        # Hong Kong
        if ticker.endswith(".HK"):
            return {
                "start_h": 9, "start_m": 30, "end_h": 16, "end_m": 0,
                "tz": "Asia/Hong_Kong",
                "holiday_calendar": "HK",
            }
        # Europe (London, Frankfurt, Paris, Amsterdam) - approximate venue windows.
        european_markets = {
            ".DE": {
                "holiday_calendar": "DE",
                "tz": "Europe/London",
                "start_h": 8,
                "start_m": 0,
                "end_h": 16,
                "end_m": 30,
            },
            ".AS": {
                "holiday_calendar": "NL",
                "tz": "Europe/Amsterdam",
                "start_h": 9,
                "start_m": 0,
                "end_h": 17,
                "end_m": 30,
            },
            ".PA": {
                "holiday_calendar": "FR",
                "tz": "Europe/Paris",
                "start_h": 9,
                "start_m": 0,
                "end_h": 17,
                "end_m": 30,
            },
            ".LS": {
                "holiday_calendar": "PT",
                "tz": "Europe/London",
                "start_h": 8,
                "start_m": 0,
                "end_h": 16,
                "end_m": 30,
            },
            ".L": {
                "holiday_calendar": "GB",
                "tz": "Europe/London",
                "start_h": 8,
                "start_m": 0,
                "end_h": 16,
                "end_m": 30,
            },
        }
        for suffix, market_config in european_markets.items():
            if ticker.endswith(suffix):
                return market_config
        # Default: US (NYSE/NASDAQ)
        return {
            "start_h": settings.START_HOUR,
            "start_m": settings.START_MINUTE,
            "end_h": settings.END_HOUR,
            "end_m": settings.END_MINUTE,
            "tz": settings.MARKET_TIMEZONE,
            "holiday_calendar": "NYSE",
        }

    def _is_market_holiday(self, market_config: dict, now) -> bool:
        calendar_code = market_config.get("holiday_calendar")
        if not calendar_code:
            return False

        try:
            import holidays

            current_date = now.date()
            if calendar_code == "DE" and (current_date.month, current_date.day) in ((12, 24), (12, 31)):
                return True

            year = now.date().year
            if calendar_code == "NYSE":
                market_holidays = holidays.financial_holidays("NYSE", years=[year])
            else:
                market_holidays = holidays.country_holidays(calendar_code, years=[year])
            return now.date() in market_holidays
        except Exception as exc:
            logger.warning(
                "Market holiday calendar %s unavailable; treating market as closed: %s",
                calendar_code,
                exc,
            )
            return True

    def _market_early_close_time(self, market_config: dict, now):
        calendar_code = market_config.get("holiday_calendar")
        if calendar_code == "HK":
            current_date = now.date()
            if (current_date.month, current_date.day) in ((12, 24), (12, 31)):
                return now.replace(hour=12, minute=0, second=0, microsecond=0)

            if current_date.month in (1, 2):
                try:
                    import holidays

                    next_day = current_date + timedelta(days=1)
                    market_holidays = holidays.country_holidays("HK", years=[current_date.year, next_day.year])
                    if "Lunar New Year" in str(market_holidays.get(next_day, "")):
                        return now.replace(hour=12, minute=0, second=0, microsecond=0)
                except Exception as exc:
                    logger.warning(
                        "HK early-close calendar unavailable; treating market as closed: %s",
                        exc,
                    )
                    return now.replace(hour=0, minute=0, second=0, microsecond=0)
            return None

        if calendar_code == "GB":
            current_date = now.date()
            if (current_date.month, current_date.day) in ((12, 24), (12, 31)):
                return now.replace(hour=12, minute=30, second=0, microsecond=0)
            return None

        if calendar_code in ("NL", "FR"):
            current_date = now.date()
            if (current_date.month, current_date.day) in ((12, 24), (12, 31)):
                return now.replace(hour=14, minute=5, second=0, microsecond=0)
            return None

        if calendar_code != "NYSE":
            return None

        current_date = now.date()
        is_christmas_eve = current_date.month == 12 and current_date.day == 24
        is_independence_day_eve = current_date.month == 7 and current_date.day == 3
        if is_christmas_eve or is_independence_day_eve:
            return now.replace(hour=13, minute=0, second=0, microsecond=0)

        if current_date.month == 11 and current_date.weekday() == 4:
            try:
                import holidays

                previous_day = current_date - timedelta(days=1)
                market_holidays = holidays.financial_holidays("NYSE", years=[current_date.year])
                if "Thanksgiving" in str(market_holidays.get(previous_day, "")):
                    return now.replace(hour=13, minute=0, second=0, microsecond=0)
            except Exception as exc:
                logger.warning(
                    "NYSE early-close calendar unavailable; treating market as closed: %s",
                    exc,
                )
                return now.replace(hour=0, minute=0, second=0, microsecond=0)
        return None

    def is_market_open(self, ticker: str = "SPY") -> bool:
        """
        Checks if the market for a specific ticker is currently open.
        """
        if settings.DEV_MODE:
            return True

        mkt = self.get_market_config(ticker)
        tz = pytz.timezone(mkt["tz"])
        now = datetime.now(tz)

        # Weekend check
        if now.weekday() >= 5:
            return False
        if self._is_market_holiday(mkt, now):
            return False

        start_time = now.replace(hour=mkt["start_h"], minute=mkt["start_m"], second=0, microsecond=0)
        end_time = now.replace(hour=mkt["end_h"], minute=mkt["end_m"], second=0, microsecond=0)
        early_close_time = self._market_early_close_time(mkt, now)
        if early_close_time is not None:
            end_time = min(end_time, early_close_time)

        return start_time <= now <= end_time

    def next_market_open(self) -> datetime:
        """
        FR-006: Returns the next NYSE open in MARKET_TIMEZONE.
        If called while the market is currently open, returns today's open timestamp.
        """
        tz = pytz.timezone(settings.MARKET_TIMEZONE)
        now = datetime.now(tz)
        candidate = now.replace(
            hour=settings.START_HOUR, minute=settings.START_MINUTE,
            second=0, microsecond=0
        )
        # If today's open has already passed, roll forward one day.
        if now > candidate:
            from datetime import timedelta
            candidate = candidate + timedelta(days=1)
        # Skip Saturday (5) and Sunday (6).
        while candidate.weekday() >= 5:
            from datetime import timedelta
            candidate = candidate + timedelta(days=1)
        return candidate

    def log_preflight(self) -> None:
        """
        FR-006: Single informative startup line so the operator immediately
        knows mode, pair universe size, and when the next trading window opens.
        """
        runtime = dashboard_state.runtime_info()
        mode = runtime["mode"]
        next_open = self.next_market_open()
        logger.info(
            "Runtime mode resolved: execution_mode=%s execution_lane=%s "
            "broker_paper_trading=%s alpaca_endpoint_class=%s paper_trading=%s "
            "live_capital_danger=%s",
            runtime["execution_mode"],
            runtime.get("execution_lane", settings.execution_lane),
            runtime["broker_paper_trading"],
            runtime["alpaca_endpoint_class"],
            runtime["paper_trading"],
            runtime["live_capital_danger"],
        )

        table = Table(title="Bot Pre-flight Configuration", show_header=False, box=None)
        table.add_row("Mode", f"[bold cyan]{mode}[/]")
        table.add_row("Execution Mode", f"[bold cyan]{runtime['execution_mode']}[/]")
        table.add_row(
            "Execution Lane",
            f"[bold cyan]{runtime.get('execution_lane', settings.execution_lane)}[/]",
        )
        table.add_row("Alpaca Endpoint", f"{runtime['alpaca_endpoint_class']}")
        table.add_row("Dev Mode", f"{'[green]Enabled[/]' if settings.DEV_MODE else '[yellow]Disabled[/]'}")

        if settings.DEV_MODE:
            pair_count = len(settings.CRYPTO_TEST_PAIRS)
            table.add_row("Pair Universe", f"{pair_count} crypto pairs")
            table.add_row("Market Hours", "24/7 (Crypto)")
        else:
            equity_count = len(settings.ARBITRAGE_PAIRS)
            crypto_count = len(settings.CRYPTO_TEST_PAIRS)
            table.add_row("Pair Universe", f"{equity_count} equity + {crypto_count} crypto")
            table.add_row("Next NYSE Open", f"[bold yellow]{next_open.strftime('%Y-%m-%d %H:%M %Z')}[/]")

        console.print(Panel(table, title="[bold blue]Arbitrage Elite Engine[/]", border_style="blue"))

    async def _preflight_live_sell_inventory(self, legs: list[dict]) -> bool:
        """Fail closed if a live sell leg tries to sell more than owned."""
        for leg in legs:
            if leg["side"].upper() != "SELL":
                continue

            ticker = leg["ticker"]
            if "-USD" in str(ticker).upper():
                logger.debug(
                    "Skipping T212 inventory preflight for crypto ticker %s; "
                    "availability must be validated by the execution venue.",
                    ticker,
                )
                continue
            required = float(leg["quantity"])
            try:
                maybe_available = self.brokerage.get_available_quantity(ticker)
                available = await maybe_available if inspect.isawaitable(maybe_available) else maybe_available
                available = float(available or 0.0)
            except Exception as e:
                msg = (
                    f"Execution skipped before broker for {leg['display_ticker']}: "
                    f"could not verify available shares for SELL leg ({e})."
                )
                logger.warning(msg)
                await notification_service.send_message(msg)
                return False

            if available + 1e-9 < required:
                msg = (
                    f"Execution skipped before broker for {leg['display_ticker']}: "
                    f"SELL leg requires {required:.6f} shares, but the broker reports "
                    f"{available:.6f} available. This prevents 'selling more than owned'."
                )
                logger.warning(msg)
                await notification_service.send_message(msg)
                return False

        return True

    async def verify_entropy_baselines(self, pairs: list[dict]):
        """
        US1: Enforce mandatory startup check against Redis L2 entropy baselines.
        Refuses to boot if baselines are missing for any active pair when LIVE_CAPITAL_DANGER=True.
        """
        logger.info(
            "VALIDATING L2 ENTROPY BASELINES FOR %s PAIRS (LIVE_CAPITAL_DANGER=%s)...",
            len(pairs),
            settings.LIVE_CAPITAL_DANGER,
        )

        # Extract unique tickers to minimize Redis calls
        unique_tickers = set()
        for p in pairs:
            unique_tickers.add(p['ticker_a'])
            unique_tickers.add(p['ticker_b'])

        missing_baselines = []
        for ticker in unique_tickers:
            # Entropy service stores baselines as 'entropy_baseline:{ticker}'
            baseline = await redis_service.client.get(f"entropy_baseline:{ticker}")
            if not baseline:
                missing_baselines.append(ticker)

        if missing_baselines:
            error_msg = f"CRITICAL: Missing L2 Entropy Baselines for: {list(set(missing_baselines))}. Refusing to boot in LIVE mode."
            logger.critical(error_msg)
            # Send alert before exiting
            await notification_service.send_message(error_msg)
            raise SystemExit(error_msg)

        logger.info("L2 ENTROPY BASELINES VALIDATED. Proceeding with Live Startup.")

    async def initialize_pairs(self):
        """
        Initialize the monitor's active pair universe and prepare cointegration and Kalman filter state for each eligible pair.

        Selects candidate pairs (from persisted active pairs or config), applies eligibility gates, validates cointegration (optionally with rolling-window stability), sanitizes hedge ratios, warms or restores Kalman filter state, computes spread metrics, and registers prepared pair records in self.active_pairs. Updates dashboard pre-warming progress and records last_cointegration_check dates; may persist a bootstrapped active-pair list when the database is empty.
        """
        db_pairs = await persistence_service.get_active_trading_pairs()
        if not db_pairs:
            logger.info("No active pairs in database. Initializing from config.")
            candidate_pairs = build_candidate_pairs(
                settings.CRYPTO_TEST_PAIRS if settings.DEV_MODE else settings.ARBITRAGE_PAIRS,
                settings.CRYPTO_TEST_PAIRS,
                settings.MAX_ACTIVE_PAIRS,
                dev_mode=settings.DEV_MODE,
            )
            await persistence_service.save_trading_pairs(candidate_pairs)
        else:
            logger.info(f"Loaded {len(db_pairs)} active pairs from database.")
            candidate_pairs = build_candidate_pairs(
                db_pairs,
                settings.CRYPTO_TEST_PAIRS,
                settings.MAX_ACTIVE_PAIRS,
                dev_mode=settings.DEV_MODE,
            )

        # Quarantine / denylist: never warm Kalman for known junk pairs (e.g. BTC/BCH).
        from src.services.pair_discovery_helpers import is_pair_denied

        denied_ids = settings.pair_denylist_ids
        if denied_ids:
            kept: list[dict] = []
            for pair in candidate_pairs:
                pair_id = pair.get("id") or f"{pair['ticker_a']}_{pair['ticker_b']}"
                if is_pair_denied(pair_id=pair_id, denylist=denied_ids):
                    logger.warning("PAIR DENYLIST: skipping %s at initialize", pair_id)
                    try:
                        await persistence_service.update_pair_status(pair_id, "Benched")
                    except Exception as exc:
                        logger.debug("Denylist bench failed for %s: %s", pair_id, exc)
                    continue
                kept.append(pair)
            candidate_pairs = kept

        # Spec 037: pair-eligibility gate. Reject cross-currency, cross-session,
        # LSE-stamp-duty and cost-above-ceiling pairs *before* allocating
        # Kalman state for them. This avoids spending compute and Redis state
        # on pairs that the strategy can never profitably trade.
        pairs_to_init, rejected = await filter_pair_universe(
            candidate_pairs,
            account_currency=settings.ACCOUNT_CURRENCY,
            max_round_trip_cost_pct=settings.PAIR_MAX_ROUND_TRIP_COST_PCT,
            block_cross_currency=settings.BLOCK_CROSS_CURRENCY_PAIRS,
            block_lse_short_hold=settings.BLOCK_LSE_PAIRS_FOR_SHORT_HOLD,
            allow_eu_continental_overlap=settings.ALLOW_EU_CONTINENTAL_OVERLAP,
            denylist=settings.pair_denylist_ids,
            max_abs_hedge=None,
            min_correlation=settings.PAIR_DISCOVERY_MIN_CORRELATION,
            max_pvalue=settings.PAIR_DISCOVERY_MAX_PVALUE,
        )

        # US1: Verify entropy baselines ONLY for actual live broker endpoints.
        # Key off endpoint/shadow — not broker_paper_trading (False under DEV_MODE
        # even when ALPACA_BASE_URL is paper-api, which must never block paper).
        if settings.requires_l2_entropy_baselines:
            await self.verify_entropy_baselines(pairs_to_init)
        elif settings.LIVE_CAPITAL_DANGER:
            runtime = dashboard_state.runtime_info()
            logger.info(
                "Skipping L2 entropy baseline startup check in %s mode "
                "(paper_trading=%s alpaca_endpoint_class=%s); "
                "baseline enforcement remains required for actual live endpoints.",
                runtime.get("execution_mode", "UNKNOWN"),
                runtime.get("paper_trading"),
                runtime.get("alpaca_endpoint_class"),
            )
        logger.info(
            f"Initializing {len(pairs_to_init)} pairs in "
            f"{'DEV' if settings.DEV_MODE else 'PROD'} mode "
            f"(stocks={len(settings.ARBITRAGE_PAIRS) if not settings.DEV_MODE else 0}, "
            f"crypto={len(settings.CRYPTO_TEST_PAIRS)}, "
            f"rejected_by_eligibility={len(rejected)})..."
        )
        total_pairs = len(pairs_to_init)
        if total_pairs > 0:
            await dashboard_service.update(
                "pre_warming",
                f"Reading pair list 0/{total_pairs}...",
            )
        if rejected:
            # One concise summary line per rejection reason so the operator
            # can spot configuration-driven exclusions at boot.
            from collections import Counter
            reasons = Counter(r["rejection"]["reason"] for r in rejected)
            for reason, count in reasons.most_common():
                logger.info(f"  ↳ eligibility rejection: {reason} × {count}")

        for idx, pair_config in enumerate(pairs_to_init, start=1):
            ticker_a, ticker_b = pair_config['ticker_a'], pair_config['ticker_b']
            await dashboard_service.update(
                "pre_warming",
                f"Reading pair list {idx}/{total_pairs}: {ticker_a}/{ticker_b}",
            )
            try:
                hist_data = await data_service.get_historical_data_async([ticker_a, ticker_b])
                if hist_data is None or hist_data.empty:
                    logger.warning(f"SKIP {ticker_a}/{ticker_b}: No historical data returned.")
                    continue

                # Flatten MultiIndex and exact-match columns (GOOG must not bind GOOGL).
                hist_data = normalize_history_close_frame(hist_data)
                if hist_data is None or hist_data.empty:
                    logger.warning(f"SKIP {ticker_a}/{ticker_b}: No usable close columns.")
                    continue

                col_a = resolve_history_column(hist_data.columns, ticker_a)
                col_b = resolve_history_column(hist_data.columns, ticker_b)

                if not col_a or not col_b:
                    logger.warning(
                        f"SKIP {ticker_a}/{ticker_b}: Columns not found in data. "
                        f"Found: {hist_data.columns.tolist()}"
                    )
                    continue

                pair_id = f"{ticker_a}_{ticker_b}"
                if ArbitrageService.series_has_corporate_action_jump(
                    hist_data[col_a],
                    hist_data[col_b],
                    threshold=settings.CORP_ACTION_PRICE_JUMP_PCT,
                ):
                    logger.warning(
                        "SKIP %s/%s: corporate-action-sized price jump "
                        "(threshold=%.0f%%); invalidating Kalman and benching.",
                        ticker_a,
                        ticker_b,
                        settings.CORP_ACTION_PRICE_JUMP_PCT * 100.0,
                    )
                    await arbitrage_service.invalidate_pair_state(
                        pair_id, reason="corporate_action_jump"
                    )
                    try:
                        await persistence_service.save_trading_pairs([{
                            "id": pair_id,
                            "ticker_a": ticker_a,
                            "ticker_b": ticker_b,
                            "hedge_ratio": 0.0,
                            "is_cointegrated": False,
                            "status": "Benched",
                        }])
                    except Exception:
                        try:
                            await persistence_service.update_pair_status(pair_id, "Benched")
                        except Exception:
                            pass
                    continue

                is_crypto = is_crypto_pair(ticker_a, ticker_b)
                p_thresh = (
                    settings.CRYPTO_COINTEGRATION_PVALUE_THRESHOLD
                    if is_crypto
                    else settings.COINTEGRATION_PVALUE_THRESHOLD
                )
                pass_thresh = 0.2 if is_crypto else settings.COINTEGRATION_ROLLING_PASS_RATE

                is_coint, p_val, hedge = arbitrage_service.check_cointegration(
                    hist_data[col_a], hist_data[col_b], pvalue_threshold=p_thresh
                )

                # Spec 037: rolling-window stability check on top of the
                # static ADF. A pair that flunked stability across rolling
                # sub-windows is unsafe for Kalman pairs trading even if its
                # full-period ADF p-value looks great.
                stability = None
                if settings.COINTEGRATION_ROLLING_ENABLED:
                    stability = ArbitrageService.check_rolling_cointegration(
                        hist_data[col_a],
                        hist_data[col_b],
                        window=settings.COINTEGRATION_ROLLING_WINDOW,
                        step=settings.COINTEGRATION_ROLLING_STEP,
                        min_pass_rate=pass_thresh,
                        pvalue_threshold=p_thresh,
                    )
                    if not stability["stable"]:
                        is_coint = False
                        logger.info(
                            "ROLLING COINT FAIL %s/%s: pass_rate=%.2f windows=%d median_p=%.3f "
                            "→ pair benched (does not occupy an Active scan slot).",
                            ticker_a,
                            ticker_b,
                            stability["pass_rate"],
                            stability["windows_total"],
                            stability["median_pvalue"],
                        )

                # Bug L-01: Guard against NaN/Inf hedge ratio
                if pd.isna(hedge) or np.isinf(hedge):
                    logger.warning(f"Invalid hedge ratio for {ticker_a}/{ticker_b}: {hedge}. Using 1.0.")
                    hedge = 1.0

                from src.services.pair_discovery_helpers import is_hedge_ratio_sane, max_abs_hedge_limit

                hedge_cap = max_abs_hedge_limit(ticker_a, ticker_b)
                if not is_hedge_ratio_sane(
                    hedge,
                    max_abs_hedge=hedge_cap,
                    min_abs_hedge=settings.PAIR_DISCOVERY_MIN_ABS_HEDGE,
                ):
                    logger.warning(
                        "SKIP %s/%s: insane hedge_ratio=%.6f "
                        "(min_abs=%.3f max_abs=%.1f)",
                        ticker_a,
                        ticker_b,
                        float(hedge),
                        settings.PAIR_DISCOVERY_MIN_ABS_HEDGE,
                        hedge_cap,
                    )
                    try:
                        await persistence_service.save_trading_pairs([{
                            "id": pair_id,
                            "ticker_a": ticker_a,
                            "ticker_b": ticker_b,
                            "hedge_ratio": float(hedge),
                            "is_cointegrated": False,
                            "status": "Benched",
                        }])
                    except Exception:
                        try:
                            await persistence_service.update_pair_status(pair_id, "Benched")
                        except Exception:
                            pass
                    continue

                # Failed static / rolling cointegration must free the Active slot.
                # Soft-admit + skip used to leave dead equity/crypto burning MAX_ACTIVE_PAIRS.
                if not is_coint:
                    logger.warning(
                        "SKIP %s/%s: not cointegrated (p=%.4f thresh=%.3f); benching Active slot.",
                        ticker_a,
                        ticker_b,
                        float(p_val) if p_val is not None else float("nan"),
                        float(p_thresh),
                    )
                    try:
                        await persistence_service.save_trading_pairs([{
                            "id": pair_id,
                            "ticker_a": ticker_a,
                            "ticker_b": ticker_b,
                            "hedge_ratio": float(hedge),
                            "is_cointegrated": False,
                            "status": "Benched",
                        }])
                    except Exception:
                        try:
                            await persistence_service.update_pair_status(pair_id, "Benched")
                        except Exception:
                            pass
                    continue

                if pair_id in self.kalman_quarantined_pairs:
                    arbitrage_service.filters.pop(pair_id, None)
                    arbitrage_service.filter_fingerprints.pop(pair_id, None)
                    try:
                        await redis_service.delete_kalman_state(pair_id)
                    except Exception as exc:
                        logger.warning("KALMAN QUARANTINE: Redis state delete failed for %s: %s", pair_id, exc)

                # Initialize Kalman filter.
                # Do NOT pass initial_state here — that would bypass both Redis
                # warm-start and 30-day historical pre-warming, leaving P=eye(2)*10
                # so large that the filter absorbs all price variation on tick-1
                # and every z-score collapses to 0.00 indefinitely.
                # get_or_create_filter will:
                #   1. Warm-start from Redis if a saved state exists, OR
                #   2. Pre-warm with 30d of hourly data so P has converged before
                #      the first live tick.
                kf = await arbitrage_service.get_or_create_filter(
                    pair_id,
                    delta=settings.KALMAN_DELTA,
                    r=settings.KALMAN_R,
                    prewarm_data=hist_data
                )
                if pair_id in self.kalman_quarantined_pairs:
                    self.kalman_quarantined_pairs.discard(pair_id)
                    logger.info("KALMAN QUARANTINE CLEARED for %s after historical rebuild.", pair_id)

                metrics = arbitrage_service.get_spread_metrics(hist_data[col_a], hist_data[col_b], hedge)
                pair_record = {
                    "id": pair_id, "ticker_a": ticker_a, "ticker_b": ticker_b,
                    "hedge_ratio": hedge, "mean": metrics['mean'], "std": metrics['std'],
                    "is_cointegrated": is_coint,
                    "estimated_cost_pct": pair_config.get("estimated_cost_pct", 0.0),
                }
                if stability is not None:
                    pair_record["coint_stability"] = stability
                self.active_pairs.append(pair_record)
                # Mark the pair as already validated today so the daily re-check
                # in the scan loop doesn't immediately fire again 15 s after boot.
                self.last_cointegration_check[pair_id] = datetime.now().date()
                # Persist cointegration / hedge so elite rotation can bench broken pairs.
                try:
                    await persistence_service.save_trading_pairs([{
                        "id": pair_id,
                        "ticker_a": ticker_a,
                        "ticker_b": ticker_b,
                        "hedge_ratio": float(hedge),
                        "is_cointegrated": bool(is_coint),
                        "status": "Active",
                    }])
                except Exception as persist_exc:
                    logger.warning(
                        "Failed to persist cointegration state for %s: %s",
                        pair_id,
                        persist_exc,
                    )
                logger.info(f"SUCCESS: Pair {ticker_a}/{ticker_b} initialized.")

                # Pacing: Avoid blasting the data API (Yahoo/Polygon) during boot
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"FATAL ERROR initializing {ticker_a}/{ticker_b}: {e}")

        logger.info(f"Initialization Summary: {len(self.active_pairs)}/{total_pairs} pairs successfully loaded.")
        if total_pairs > 0:
            await dashboard_service.update(
                "pre_warming",
                f"Pair list pre-warming complete ({len(self.active_pairs)}/{total_pairs}).",
            )

    async def _rotate_elite_pairs(self):
        """
        Promote scout candidates into the Active universe, then hot-reload
        in-memory pair state when anything changed.
        """
        logger.info("ELITE SQUAD: Checking for potential pair rotation...")
        from src.agents.portfolio_manager_agent import portfolio_manager

        result = await portfolio_manager.rotate_pairs()
        if result.get("status") != "rotated":
            logger.info("ELITE SQUAD: %s", result.get("status", "noop"))
            return result

        await self.reload_pairs()
        return result

    async def _auto_scout_and_rotate_loop(self):
        """
        Background task that periodically runs the discovery engine (Scouting)
        and promotes the best pairs (Rotation).
        """
        if not settings.PAIR_DISCOVERY_ENABLED:
            logger.info("AUTO-SCOUT: disabled via PAIR_DISCOVERY_ENABLED=false.")
            return

        # Wait after startup before the first scout cycle so Kalman warm-up
        # and the first market-data burst are not starved by yfinance scouts.
        initial_delay = max(60, int(settings.SCOUT_INITIAL_DELAY_SECONDS))
        logger.info(
            "AUTO-SCOUT: first cycle in %.0f minutes.",
            initial_delay / 60,
        )
        await asyncio.sleep(initial_delay)

        while True:
            try:
                if not settings.PAIR_DISCOVERY_ENABLED:
                    logger.info("AUTO-SCOUT: disabled; sleeping until re-enabled.")
                    await asyncio.sleep(3600)
                    continue

                logger.info("AUTO-UPDATE: Starting periodic Scouting & Rotation cycle...")

                from src.agents.portfolio_manager_agent import portfolio_manager
                await portfolio_manager.run_discovery()

                if settings.PAIR_DISCOVERY_AUTO_PROMOTE:
                    await self._rotate_elite_pairs()
                else:
                    logger.info("AUTO-UPDATE: auto-promote disabled; candidates stored only.")

                logger.info(f"AUTO-UPDATE: Cycle complete. Next run in {settings.SCOUT_INTERVAL_HOURS} hours.")
                await asyncio.sleep(settings.SCOUT_INTERVAL_HOURS * 3600)
            except Exception as e:
                logger.error(f"Error in auto-scout loop: {e}")
                await asyncio.sleep(3600) # Retry in 1 hour



    def _read_process_rss_mib(self) -> int | None:
        """Return current process RSS in MiB, or None if unavailable."""
        try:
            with open("/proc/self/status", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("VmRSS:"):
                        # VmRSS is in kB on Linux.
                        return int(line.split()[1]) // 1024
        except Exception:
            pass
        try:
            import psutil

            return int(psutil.Process().memory_info().rss / (1024 * 1024))
        except Exception:
            return None

    def _prune_runtime_caches(self, *, aggressive: bool = False) -> dict[str, int]:
        """Drop retainable scan scrap that is safe to forget between iterations."""
        active_ids = {
            str(pair.get("id") or f"{pair.get('ticker_a')}_{pair.get('ticker_b')}")
            for pair in self.active_pairs
        }
        active_tickers = {
            str(ticker)
            for pair in self.active_pairs
            for ticker in (pair.get("ticker_a"), pair.get("ticker_b"))
            if ticker
        }
        stats = {
            "signals_before": len(self.active_signals),
            "signals_after": 0,
            "crypto_markers_removed": 0,
            "price_meta_removed": 0,
            "jsonl_rotated": 0,
            "decision_events_cleared": 0,
            "regime_evicted": 0,
        }

        max_signals = max(
            int(getattr(settings, "MEMORY_ACTIVE_SIGNAL_MAX", 0) or 0),
            int(settings.MAX_ACTIVE_PAIRS) * 2,
        )
        self.active_signals = prune_active_signals(
            self.active_signals,
            active_pair_ids=active_ids,
            max_signals=max_signals,
            drop_terminal=aggressive,
        )
        stats["signals_after"] = len(self.active_signals)

        stats["crypto_markers_removed"] = prune_dict_to_keys(
            self._crypto_snapshot_pair_prices,
            active_ids,
        )
        # Stale Kalman fingerprints for pairs no longer Active.
        for pid in list(arbitrage_service.filter_fingerprints.keys()):
            if pid not in active_ids and pid not in arbitrage_service.filters:
                arbitrage_service.filter_fingerprints.pop(pid, None)

        price_sources = getattr(data_service, "last_price_sources", None)
        price_timestamps = getattr(data_service, "last_price_timestamps", None)
        if isinstance(price_sources, dict):
            stats["price_meta_removed"] += prune_dict_to_keys(price_sources, active_tickers)
        if isinstance(price_timestamps, dict):
            stats["price_meta_removed"] += prune_dict_to_keys(price_timestamps, active_tickers)

        decision_max = int(getattr(settings, "STRUCTURED_LOG_MAX_BYTES", 5_000_000) or 5_000_000)
        trade_max = int(
            getattr(settings, "TRADE_DECISION_LOG_MAX_BYTES", 10_000_000) or 10_000_000
        )
        if rotate_jsonl_if_large(STRUCTURED_LOG_PATH, max_bytes=decision_max):
            stats["jsonl_rotated"] += 1
        if rotate_jsonl_if_large(self.trade_decision_report_path, max_bytes=trade_max):
            stats["jsonl_rotated"] += 1

        if aggressive:
            from src.services.decision_trace_service import decision_recorder as live_recorder

            before = len(live_recorder._events)
            # Keep promoted/anomaly crumbs; drop routine skip noise.
            retained = [
                event
                for event in live_recorder._events
                if event.promoted or event.outcome in ("anomaly", "execute", "veto")
            ]
            from collections import deque

            live_recorder._events = deque(
                retained,
                maxlen=max(1, live_recorder._maxsize),
            )
            stats["decision_events_cleared"] = max(0, before - len(live_recorder._events))

            try:
                import time as _time

                stats["regime_evicted"] += evict_ttl_cache(
                    market_regime_service._regime_cache,
                    now=_time.monotonic(),
                    ttl_seconds=float(market_regime_service.cache_ttl_seconds),
                    max_entries=32,
                )
            except Exception:
                pass

        return stats

    def _maybe_relieve_memory_pressure(self, *, reason: str, threshold_mib: int | None = None) -> None:
        """Prune retainable caches and GC when RSS nears the compose mem_limit.

        The bot container is capped at 1280m; without periodic reclaim, pandas/yfinance
        scrap from scouts + scans can push the cgroup to the limit and eventually OOM-kill
        (exit 137). Soft prune runs every scan; aggressive prune+GC only above threshold.
        """
        if threshold_mib is None:
            threshold_mib = int(getattr(settings, "MEMORY_PRESSURE_THRESHOLD_MIB", 900) or 900)

        # Cheap soft prune every scan (no GC) to stop slow list/dict growth.
        soft_stats = self._prune_runtime_caches(aggressive=False)

        rss_mib = self._read_process_rss_mib()
        if rss_mib is None:
            return
        if rss_mib < threshold_mib:
            if soft_stats["signals_before"] != soft_stats["signals_after"]:
                logger.debug(
                    "MEMORY HYGIENE [%s]: rss≈%dMiB signals %d→%d",
                    reason,
                    rss_mib,
                    soft_stats["signals_before"],
                    soft_stats["signals_after"],
                )
            return

        hard_stats = self._prune_runtime_caches(aggressive=True)
        collected = gc.collect()
        logger.warning(
            "MEMORY PRESSURE [%s]: rss≈%dMiB (threshold=%dMiB); "
            "gc.collect()=%d signals=%d→%d crypto_markers_removed=%d "
            "price_meta_removed=%d jsonl_rotated=%d decision_cleared=%d",
            reason,
            rss_mib,
            threshold_mib,
            collected,
            soft_stats["signals_before"],
            hard_stats["signals_after"],
            hard_stats["crypto_markers_removed"],
            hard_stats["price_meta_removed"],
            hard_stats["jsonl_rotated"],
            hard_stats["decision_events_cleared"],
        )

    async def reload_pairs(self):
        """
        Reload the active pair universe from settings and update in-memory state.

        Builds a new list of active pairs by calling initialize_pairs() while holding the signals lock;
        replaces the existing active_pairs and resets last_cointegration_check. After reloading,
        removes any in-memory Kalman filters that correspond to pairs no longer active to prevent
        memory growth and logs a summary of added/removed pairs.
        """
        async with self._signals_lock:
            old_pairs = list(self.active_pairs)
            old_ids = {p['id'] for p in old_pairs}

            # Reset and rebuild via the existing initializer.
            self.active_pairs = []
            self.last_cointegration_check = {}
            await self.initialize_pairs()
            new_ids = {p['id'] for p in self.active_pairs}

            # Safety net: if the reload produced ZERO pairs (e.g. Yahoo rate-limited
            # during run_discovery), restore the previous set so the scan loop is
            # never left with 0/0 pairs.
            if not self.active_pairs and old_pairs:
                logger.warning(
                    "reload_pairs: new initialization returned 0 pairs — "
                    "keeping existing %d pairs to avoid scan blackout.",
                    len(old_pairs),
                )
                self.active_pairs = old_pairs
                self.last_cointegration_check = {
                    p['id']: __import__('datetime').date.today()
                    for p in old_pairs
                }
                return

            # Forget Kalman filters for pairs that were removed so memory
            # doesn't accumulate across reloads.
            removed = old_ids - new_ids
            if removed:
                for pid in removed:
                    await self._drop_kalman_runtime_state(pid)
                logger.info(f"reload_pairs: dropped {len(removed)} pairs ({sorted(removed)})")
            logger.info(
                f"reload_pairs complete: {len(new_ids)} active pairs "
                f"(+{len(new_ids - old_ids)} new, -{len(removed)} removed)"
            )

    async def _drop_kalman_runtime_state(self, pair_id: str) -> None:
        """Drop in-memory Kalman filter/fingerprint and Redis state for *pair_id*."""
        arbitrage_service.filters.pop(pair_id, None)
        arbitrage_service.filter_fingerprints.pop(pair_id, None)
        self._crypto_snapshot_pair_prices.pop(pair_id, None)
        try:
            await redis_service.delete_kalman_state(pair_id)
        except Exception as exc:
            logger.warning(
                "KALMAN GUARD: failed to delete Redis state for %s: %s",
                pair_id,
                exc,
            )

    @staticmethod
    def _normalize_pair_history_frame(hist_data: pd.DataFrame) -> pd.DataFrame:
        """Flatten MultiIndex yfinance frames to a ticker->close DataFrame."""
        normalized = normalize_history_close_frame(hist_data)
        return hist_data if normalized is None else normalized

    async def _rebuild_quarantined_kalman_pair(self, pair: dict) -> bool:
        """Re-warm a single quarantined pair without reloading the whole universe.

        Full ``reload_pairs()`` re-fetches 30d history for every Active pair and
        resets the dashboard stage -- expensive for RAM and hostile when
        ``PAIR_DISCOVERY_ENABLED=false`` (slots cannot be refilled). Targeted
        rebuild keeps the rest of the scan universe intact.
        """
        pair_id = pair.get("id") or f"{pair['ticker_a']}_{pair['ticker_b']}"
        ticker_a, ticker_b = pair["ticker_a"], pair["ticker_b"]

        await self._drop_kalman_runtime_state(pair_id)

        hist_data = await data_service.get_historical_data_async(
            [ticker_a, ticker_b],
            "30d",
            "1h",
        )
        if hist_data is None or hist_data.empty:
            logger.warning(
                "KALMAN QUARANTINE: targeted rebuild for %s failed -- no history.",
                pair_id,
            )
            return False

        hist_data = self._normalize_pair_history_frame(hist_data)
        col_a = resolve_history_column(hist_data.columns, ticker_a)
        col_b = resolve_history_column(hist_data.columns, ticker_b)
        if not col_a or not col_b:
            logger.warning(
                "KALMAN QUARANTINE: targeted rebuild for %s failed -- columns missing (%s).",
                pair_id,
                list(hist_data.columns),
            )
            return False

        await arbitrage_service.get_or_create_filter(
            pair_id,
            delta=settings.KALMAN_DELTA,
            r=settings.KALMAN_R,
            prewarm_data=hist_data,
        )
        self.kalman_quarantined_pairs.discard(pair_id)
        logger.info(
            "KALMAN QUARANTINE CLEARED for %s after targeted historical rebuild.",
            pair_id,
        )
        return True

    async def _retire_failed_kalman_pair(
        self,
        pair: dict,
        *,
        reason: str = "kalman_quarantine_exhausted",
    ) -> None:
        """Bench a pair that stayed invalid after its one-shot rebuild.

        Stuck ``kalman_state_quarantined`` skips used to keep burning Active
        slots (and Redis/in-memory filter residue) forever -- especially painful
        with discovery pinned off on the server.
        """
        pair_id = pair.get("id") or f"{pair['ticker_a']}_{pair['ticker_b']}"
        ticker_a, ticker_b = pair["ticker_a"], pair["ticker_b"]

        await self._drop_kalman_runtime_state(pair_id)

        before = len(self.active_pairs)
        self.active_pairs = [p for p in self.active_pairs if p.get("id") != pair_id]
        removed = before - len(self.active_pairs)

        self.kalman_quarantined_pairs.discard(pair_id)
        # Allow a future re-promote (elite rotation) one fresh rebuild chance.
        self._kalman_rebuild_attempted.discard(pair_id)
        self.last_cointegration_check.pop(pair_id, None)
        self.bumped_pairs_today.pop(pair_id, None)

        try:
            await persistence_service.save_trading_pairs([{
                "id": pair_id,
                "ticker_a": ticker_a,
                "ticker_b": ticker_b,
                "hedge_ratio": float(pair.get("hedge_ratio") or 0.0),
                "is_cointegrated": False,
                "status": "Benched",
            }])
        except Exception:
            try:
                await persistence_service.update_pair_status(pair_id, "Benched")
            except Exception as exc:
                logger.warning(
                    "KALMAN QUARANTINE: failed to bench %s after %s: %s",
                    pair_id,
                    reason,
                    exc,
                )

        logger.warning(
            "KALMAN QUARANTINE RETIRE [%s/%s]: %s -- benched and freed Active slot "
            "(removed_from_memory=%s).",
            ticker_a,
            ticker_b,
            reason,
            bool(removed),
        )

    async def _reload_quarantined_pairs_if_requested(self) -> bool:
        if not self._kalman_quarantine_reload_requested:
            return False
        if not self.kalman_quarantined_pairs:
            self._kalman_quarantine_reload_requested = False
            return False

        quarantined = sorted(self.kalman_quarantined_pairs)
        self._kalman_quarantine_reload_requested = False
        logger.warning(
            "KALMAN QUARANTINE: targeted rebuild after scan (no full universe reload): %s",
            quarantined,
        )
        pairs_by_id = {p["id"]: p for p in self.active_pairs if p.get("id")}
        rebuilt_any = False
        for pair_id in quarantined:
            pair = pairs_by_id.get(pair_id)
            if pair is None:
                self.kalman_quarantined_pairs.discard(pair_id)
                await self._drop_kalman_runtime_state(pair_id)
                continue
            try:
                rebuilt_any = await self._rebuild_quarantined_kalman_pair(pair) or rebuilt_any
            except Exception as exc:
                logger.warning(
                    "KALMAN QUARANTINE: targeted rebuild failed for %s: %s",
                    pair_id,
                    exc,
                )
        return rebuilt_any or bool(quarantined)

    async def _unmanaged_market_value(self) -> float:
        """Abs market value of broker positions not on open ledger legs.

        Used when ``IGNORE_UNMANAGED_POSITIONS`` so foreign inventory cannot inflate
        Kelly / allocation / sector denominators. Positions without a resolvable
        symbol are skipped (not treated as unmanaged).
        """
        if settings.PAPER_TRADING:
            return 0.0
        maybe_positions = self.brokerage.get_positions()
        broker_positions = (
            await maybe_positions if inspect.isawaitable(maybe_positions) else maybe_positions
        )
        open_signals = await persistence_service.get_open_signals()
        ledger_symbols: set[str] = set()
        for signal in open_signals or []:
            for leg in signal.get("legs", []) or []:
                sym = self._canonical_position_symbol(leg.get("ticker"))
                if sym:
                    ledger_symbols.add(sym)

        total = 0.0
        for pos in broker_positions or []:
            raw_symbol = (
                pos.get("ticker")
                or pos.get("symbol")
                or pos.get("instrumentTicker")
                or pos.get("instrument")
            )
            canonical = self._canonical_position_symbol(raw_symbol)
            if not canonical or canonical in ledger_symbols:
                continue
            qty = float(
                pos.get("quantityAvailableForTrading")
                if pos.get("quantityAvailableForTrading") is not None
                else pos.get("quantity")
                or 0.0
            )
            if abs(qty) <= 1e-12:
                continue
            mv = pos.get("marketValue")
            if mv is None:
                mv = pos.get("market_value")
            if mv is None:
                px = (
                    pos.get("currentPrice")
                    or pos.get("current_price")
                    or pos.get("averagePrice")
                    or pos.get("avg_entry_price")
                )
                if px is None:
                    continue
                mv = abs(qty) * float(px)
            total += abs(float(mv))
        return total

    async def _get_sizing_base(self) -> float:
        """Helper to fetch the current account equity/cash for sizing calculations."""
        if settings.PAPER_TRADING:
            venue_budget_cap = settings.ALPACA_BUDGET_USD
            return venue_budget_cap if venue_budget_cap > 0 else settings.PAPER_TRADING_STARTING_CASH

        try:
            maybe_equity = self.brokerage.get_account_equity()
            equity = await maybe_equity if inspect.isawaitable(maybe_equity) else maybe_equity
            base = float(equity or 0.0)
            if getattr(settings, "IGNORE_UNMANAGED_POSITIONS", False) and base > 0:
                try:
                    unmanaged_mv = await self._unmanaged_market_value()
                    base = max(0.0, base - float(unmanaged_mv or 0.0))
                except Exception as um_exc:
                    logger.warning(
                        "Unmanaged MV probe failed during sizing_base (%s); "
                        "using full equity (execute path fail-closes separately).",
                        um_exc,
                    )
            return base
        except Exception as e:
            logger.warning(f"Failed to fetch sizing base from brokerage: {e}. Falling back to default.")
            return settings.PAPER_TRADING_STARTING_CASH

    async def _sellable_notional(self, ticker: str, mark_price: float) -> float:
        """Return USD notional available to sell for *ticker* (0 if none)."""
        price = float(mark_price or 0.0)
        if price <= 0:
            return 0.0
        try:
            maybe_positions = self.brokerage.get_positions(ticker)
            positions = await maybe_positions if inspect.isawaitable(maybe_positions) else maybe_positions
        except Exception as exc:
            logger.warning("Inventory read failed for %s: %s", ticker, exc)
            return 0.0
        if not positions:
            return 0.0
        pos = positions[0]
        qty = float(
            pos.get("quantityAvailableForTrading")
            if pos.get("quantityAvailableForTrading") is not None
            else pos.get("quantity")
            or 0.0
        )
        if qty <= 0:
            return 0.0
        mv = float(pos.get("marketValue") or 0.0)
        # Prefer market value when present; otherwise qty * mark.
        if mv > 0:
            return max(0.0, mv)
        return max(0.0, qty * price)

    async def _scale_legs_to_sellable_inventory(
        self,
        legs,
        *,
        ticker_a: str,
        ticker_b: str,
        price_a: float,
        price_b: float,
        hedge_ratio: float,
        direction: str,
        crypto_pair: bool,
    ):
        """Scale pair gross down so SELL legs fit current holdings.

        For crypto (spot, no short), missing inventory force-scales or rejects.
        For equities we still cap when holdings are known; unconstrained shorts
        keep the original plan when no position record exists.
        """
        if legs.gross_notional <= 0:
            return None

        limit_gross = float(legs.gross_notional)
        for ticker, side, notional, price in (
            (ticker_a, legs.side_a, legs.notional_a, price_a),
            (ticker_b, legs.side_b, legs.notional_b, price_b),
        ):
            if side != "SELL" or notional <= 0 or legs.gross_notional <= 0:
                continue
            sellable = await self._sellable_notional(ticker, price)
            if sellable <= 0:
                if crypto_pair:
                    logger.warning(
                        "INVENTORY GUARD: No sellable inventory for crypto %s (%s leg).",
                        ticker, side,
                    )
                    return None
                # Equity may be shortable without a long position — leave uncapped.
                continue
            # Preserve hedge ratio by scaling whole pair from the constrained sell share.
            sell_share = notional / legs.gross_notional
            if sell_share <= 0:
                continue
            # Keep a 2% buffer for price drift between size and submit.
            max_gross_for_leg = (sellable * 0.98) / sell_share
            if max_gross_for_leg < limit_gross:
                logger.info(
                    "INVENTORY GUARD: Scaling %s/%s gross $%.2f -> $%.2f (sellable %s=$%.2f)",
                    ticker_a, ticker_b, limit_gross, max_gross_for_leg, ticker, sellable,
                )
                limit_gross = max_gross_for_leg

        if limit_gross + 1e-9 < settings.MIN_TRADE_VALUE:
            return None
        if abs(limit_gross - legs.gross_notional) < 1e-6:
            return legs
        return build_pair_legs(
            price_a=price_a,
            price_b=price_b,
            hedge_ratio=hedge_ratio,
            gross_notional=limit_gross,
            direction=direction,
        )

    def _write_trade_decision_report(
        self,
        *,
        scan_pairs: list[dict],
        results: list[dict],
        latest_prices: dict,
        latest_price_sources: dict | None = None,
        latest_price_timestamps: dict | None = None,
        open_signals: list,
        active_signal_count: int,
        vetoed_count: int,
        sizing_base: float,
    ) -> dict:
        latest_price_sources = latest_price_sources or {}
        latest_price_timestamps = latest_price_timestamps or {}
        decisions = []

        def pair_identity(pair: dict) -> str:
            return str(pair.get("id") or f"{pair.get('ticker_a')}_{pair.get('ticker_b')}")

        def append_decision(pair: dict, result: dict | None) -> None:
            ticker_a = pair.get("ticker_a")
            ticker_b = pair.get("ticker_b")
            result = result or {}
            decision = {
                "pair_id": pair.get("id"),
                "ticker_a": ticker_a,
                "ticker_b": ticker_b,
                "verdict": result.get("verdict", "UNKNOWN"),
                "confidence": float(result.get("confidence", 0.0) or 0.0),
                "has_price_a": ticker_a in latest_prices,
                "has_price_b": ticker_b in latest_prices,
                "price_a": latest_prices.get(ticker_a),
                "price_b": latest_prices.get(ticker_b),
                "price_source_a": (
                    latest_price_sources.get(ticker_a, "unknown")
                    if ticker_a in latest_prices
                    else None
                ),
                "price_source_b": (
                    latest_price_sources.get(ticker_b, "unknown")
                    if ticker_b in latest_prices
                    else None
                ),
                "price_timestamp_a": (
                    latest_price_timestamps.get(ticker_a)
                    if ticker_a in latest_prices
                    else None
                ),
                "price_timestamp_b": (
                    latest_price_timestamps.get(ticker_b)
                    if ticker_b in latest_prices
                    else None
                ),
            }
            if result.get("reason"):
                decision["reason"] = result["reason"]
                decision["rejection_reason"] = result["reason"]
            for field in TRADE_DECISION_DETAIL_FIELDS:
                if field in result:
                    decision[field] = result[field]
            decisions.append(decision)

        for pair, result in zip(scan_pairs, results):
            append_decision(pair, result)

        scanned_pair_ids = {pair_identity(pair) for pair in scan_pairs}
        for pair in self.active_pairs:
            if pair_identity(pair) in scanned_pair_ids:
                continue
            ticker_a = pair.get("ticker_a")
            ticker_b = pair.get("ticker_b")
            if pair.get("is_cointegrated", True) is False:
                reason = "not_cointegrated"
            elif not is_crypto_pair(ticker_a, ticker_b) and not self.is_market_open(ticker_a):
                reason = "market_closed"
            else:
                reason = "not_scanned"
            append_decision(
                pair,
                {
                    "verdict": "IGNORED",
                    "confidence": 0.0,
                    "reason": reason,
                },
            )

        report = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "mode": "paper" if settings.PAPER_TRADING else "live",
            "pairs_loaded": len(self.active_pairs),
            "pairs_scanned": len(scan_pairs),
            "prices_received": len(latest_prices),
            "signals": int(active_signal_count),
            "vetoed": int(vetoed_count),
            "open_positions": len(open_signals),
            "sizing_base": float(sizing_base or 0.0),
            "decisions": decisions,
        }

        report_path = Path(self.trade_decision_report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(report, sort_keys=True) + "\n")
        return report

    async def process_pair(self, pair: dict, latest_prices: dict, sizing_base: float = 0.0) -> dict:
        """Processes a single pair for signals and validation."""
        diagnostic = {"confidence": 0.0, "verdict": "IGNORED"}
        try:
            t_a, t_b = pair['ticker_a'], pair['ticker_b']
            decision_recorder.set_pair_id(pair.get("id") or f"{t_a}_{t_b}")
            decision_recorder.set_signal_id(None)

            def skip(reason: str, stage: str = "pre_signal", **inputs) -> dict:
                diagnostic["reason"] = reason
                decision_recorder.record(
                    stage=stage,
                    outcome="skip",
                    reason=reason,
                    inputs=inputs or None,
                )
                logger.info("PAIR SKIP [%s/%s]: %s", t_a, t_b, reason)
                return diagnostic

            # Multi-Market Hour Enforcement
            is_crypto = is_crypto_pair(t_a, t_b)
            if not is_crypto and not self.is_market_open(t_a):
                return skip("market_closed")

            # Skip pairs whose cointegration has broken (detected by daily re-check).
            if not pair.get('is_cointegrated', True):
                return skip("not_cointegrated")

            if pair['id'] in self.kalman_quarantined_pairs:
                # Quarantined + rebuild already attempted + no reload pending means
                # the one-shot rebuild finished and the pair was re-quarantined.
                # Free the Active slot instead of skipping forever (burns slots
                # when discovery is pinned off). While reload is still queued,
                # keep skipping so the targeted rebuild can run.
                if (
                    pair['id'] in self._kalman_rebuild_attempted
                    and not self._kalman_quarantine_reload_requested
                ):
                    await self._retire_failed_kalman_pair(
                        pair,
                        reason="kalman_quarantine_exhausted",
                    )
                    return skip("kalman_quarantine_benched", stage="kalman")
                return skip("kalman_state_quarantined")

            if t_a not in latest_prices or t_b not in latest_prices:
                return skip("missing_price")

            price_a = latest_prices[t_a]
            price_b = latest_prices[t_b]

            if is_crypto:
                invalid_prices = []
                for ticker, price in ((t_a, price_a), (t_b, price_b)):
                    try:
                        parsed_price = float(price)
                    except (TypeError, ValueError):
                        invalid_prices.append(f"{ticker}={price}")
                        continue
                    bounds = CRYPTO_PRICE_SANITY_RANGES.get(ticker)
                    if not np.isfinite(parsed_price) or parsed_price <= 0.0:
                        invalid_prices.append(f"{ticker}={price}")
                    elif bounds and not (bounds[0] <= parsed_price <= bounds[1]):
                        invalid_prices.append(f"{ticker}={parsed_price} outside {bounds[0]}..{bounds[1]}")
                if invalid_prices:
                    logger.warning(
                        "PRICE SANITY [%s/%s]: invalid latest price(s): %s. "
                        "Blocking before Kalman update.",
                        t_a,
                        t_b,
                        "; ".join(invalid_prices),
                    )
                    return skip("price_sanity_invalid", details="; ".join(invalid_prices))

                price_sources = getattr(data_service, "last_price_sources", {})
                source_a = price_sources.get(t_a)
                source_b = price_sources.get(t_b)
                alpaca_crypto_sources = {"alpaca_crypto_snapshot", "alpaca_crypto_quote_mid"}
                # Fail closed: mixed/unknown sources (redis/yfinance/missing) have no
                # trustworthy age — never feed Kalman / open a new trade on them.
                if source_a not in alpaca_crypto_sources or source_b not in alpaca_crypto_sources:
                    self._crypto_snapshot_pair_prices.pop(pair["id"], None)
                    logger.warning(
                        "PRICE FRESHNESS [%s/%s]: crypto sources not both Alpaca "
                        "(%s=%s, %s=%s). Blocking before Kalman update.",
                        t_a,
                        t_b,
                        t_a,
                        source_a,
                        t_b,
                        source_b,
                    )
                    return skip(
                        "price_freshness_unknown",
                        stage="price_guard",
                        source_a=source_a,
                        source_b=source_b,
                    )

                price_timestamps = getattr(data_service, "last_price_timestamps", {}) or {}
                now_utc = datetime.now(timezone.utc)
                max_age = crypto_price_max_age_seconds(settings.SCAN_INTERVAL_SECONDS)
                missing_ts = []
                for ticker, source in ((t_a, source_a), (t_b, source_b)):
                    parsed_ts = parse_price_timestamp(price_timestamps.get(ticker))
                    if parsed_ts is None:
                        missing_ts.append(ticker)
                        continue
                    age_seconds = (now_utc - parsed_ts).total_seconds()
                    if age_seconds > max_age:
                        logger.warning(
                            "PRICE STALENESS [%s/%s]: %s %s timestamp age "
                            "%.1fs exceeds max %.1fs (scan_interval=%ss). "
                            "Blocking before Kalman update.",
                            t_a,
                            t_b,
                            ticker,
                            source,
                            age_seconds,
                            max_age,
                            settings.SCAN_INTERVAL_SECONDS,
                        )
                        return skip(
                            "stale_price_snapshot",
                            stage="price_guard",
                            age_seconds=age_seconds,
                            max_age_seconds=max_age,
                        )

                # Missing trade/quote timestamps = invalid freshness (not "maybe fine").
                if missing_ts:
                    self._crypto_snapshot_pair_prices.pop(pair["id"], None)
                    logger.warning(
                        "PRICE FRESHNESS [%s/%s]: missing Alpaca timestamps for %s. "
                        "Blocking before Kalman update.",
                        t_a,
                        t_b,
                        ",".join(missing_ts),
                    )
                    return skip(
                        "price_freshness_unknown",
                        stage="price_guard",
                        missing_timestamps=missing_ts,
                    )

                # Both legs timestamped and within max age — clear legacy price-only state.
                self._crypto_snapshot_pair_prices.pop(pair["id"], None)

            # Feature 007: Kalman Filter Update
            kf = await arbitrage_service.get_or_create_filter(
                pair["id"],
                delta=settings.KALMAN_DELTA,
                r=settings.KALMAN_R,
            )
            if kf is None:
                logger.warning("Kalman filter unavailable for pair %s — skipping tick.", pair['id'])
                return skip("kalman_unavailable", stage="kalman")

            # Spec 037: Session-boundary Q/P adjustment applied BEFORE this
            # tick's update so the inflated noise is in effect for the very
            # first bar after market open. inflate_q() then decays Q linearly
            # back to base over the next KALMAN_Q_SESSION_BARS updates.
            today = datetime.now().date()
            if not is_crypto and self.bumped_pairs_today.get(pair['id']) != today:
                if settings.KALMAN_USE_Q_INFLATION:
                    kf.inflate_q(
                        factor=settings.KALMAN_Q_SESSION_FACTOR,
                        n_bars=settings.KALMAN_Q_SESSION_BARS,
                    )
                    logger.info(
                        f"KALMAN Q-INFLATION engaged for {pair['id']} on session open "
                        f"(factor={settings.KALMAN_Q_SESSION_FACTOR}, "
                        f"bars={settings.KALMAN_Q_SESSION_BARS})."
                    )
                else:
                    kf.bump_uncertainty(multiplier=10.0)
                    logger.info(f"KALMAN BUMP applied to {pair['id']} for market open.")
                self.bumped_pairs_today[pair['id']] = today

            # Single Kalman update. z_score is computed from the PRIOR state
            # (before this tick's measurement is absorbed) — correct for signals.
            state_vec, innovation_var, z_score, spread = kf.update(price_a, price_b)

            try:
                beta = float(state_vec[1])
                z_score_value = float(z_score)
                innovation_value = float(innovation_var)
                spread_value = float(spread)
                invalid_kalman_state = (
                    not np.isfinite(beta)
                    or not np.isfinite(z_score_value)
                    or not np.isfinite(innovation_value)
                    or not np.isfinite(spread_value)
                    or innovation_value <= 0.0
                    or beta <= KALMAN_BETA_CLIP_MIN
                    or beta >= KALMAN_BETA_CLIP_MAX
                    or abs(z_score_value) > KALMAN_MAX_REASONABLE_ABS_ZSCORE
                )
            except (TypeError, ValueError, IndexError):
                beta = None
                z_score_value = z_score
                innovation_value = innovation_var
                spread_value = spread
                invalid_kalman_state = True

            if invalid_kalman_state:
                already_quarantined = pair['id'] in self.kalman_quarantined_pairs
                self.kalman_quarantined_pairs.add(pair['id'])
                await self._drop_kalman_runtime_state(pair['id'])
                logger.warning(
                    "KALMAN GUARD [%s/%s]: invalid state. beta=%s z_score=%s "
                    "innovation_var=%s spread=%s. Blocking entry before state persistence/approval.",
                    t_a,
                    t_b,
                    beta,
                    z_score_value,
                    innovation_value,
                    spread_value,
                )
                if not already_quarantined and pair['id'] not in self._kalman_rebuild_attempted:
                    self._kalman_quarantine_reload_requested = True
                    self._kalman_rebuild_attempted.add(pair['id'])
                    logger.warning(
                        "KALMAN QUARANTINE [%s/%s]: queued targeted historical rebuild after this scan.",
                        t_a,
                        t_b,
                    )
                    return skip(
                        "kalman_state_invalid",
                        stage="kalman",
                        beta=beta,
                        z_score=z_score_value,
                    )

                # Rebuild already tried and the state is still invalid (e.g. an
                # extreme price-ratio pair pinned at the beta clip). Bench the
                # pair so it stops occupying an Active slot -- do NOT request
                # another universe reload (that resets stage + re-warms on a loop).
                await self._retire_failed_kalman_pair(
                    pair,
                    reason="kalman_quarantine_exhausted",
                )
                return skip(
                    "kalman_quarantine_benched",
                    stage="kalman",
                    beta=beta,
                    z_score=z_score_value,
                )

            # Valid state this scan: allow a fresh one-shot rebuild if this pair
            # ever goes transiently invalid again in the future.
            self._kalman_rebuild_attempted.discard(pair['id'])

            # Admission hedge cap must also apply to live Kalman beta. OLS can
            # pass the asset-class abs-hedge ceiling at warm-up while the filter
            # drifts past it. Crypto uses PAIR_DISCOVERY_MAX_ABS_HEDGE_CRYPTO.
            from src.services.pair_discovery_helpers import is_hedge_ratio_sane, max_abs_hedge_limit

            hedge_cap = max_abs_hedge_limit(t_a, t_b)
            if not is_hedge_ratio_sane(
                state_vec[1], max_abs_hedge=hedge_cap
            ):
                return skip(
                    "extreme_kalman_beta",
                    stage="kalman",
                    beta=float(state_vec[1]),
                    max_abs_hedge=float(hedge_cap),
                )

            # Persist Kalman state to Redis
            await arbitrage_service.save_filter_state(pair['id'], kf, z_score)

            # Signal Generation - Spec 038: optionally scale the entry z-score
            # by this pair's round-trip cost so that high-friction pairs (HK,
            # Swiss, cross-currency) require more statistical edge before
            # firing. Falls back to the global threshold when the toggle is off
            # or when no cost estimate is available on the pair record.
            entry_zscore = compute_entry_zscore(
                settings.MONITOR_ENTRY_ZSCORE,
                cost_scaling_enabled=settings.MONITOR_ENTRY_ZSCORE_COST_SCALING_ENABLED,
                pair_estimated_cost_pct=float(pair.get("estimated_cost_pct") or 0.0),
                cost_baseline=float(settings.MONITOR_ENTRY_ZSCORE_COST_BASELINE),
                scaling_cap=float(settings.MONITOR_ENTRY_ZSCORE_COST_SCALING_CAP),
                cost_ceiling=float(settings.PAIR_MAX_ROUND_TRIP_COST_PCT),
            )

            # Sprint J: Heartbeat log for pair health
            # US-033: Increased precision and diagnostic visibility
            z_color = "yellow" if abs(z_score) > entry_zscore * 0.8 else "cyan"
            logger.info(f"SCAN [{t_a}/{t_b}] Z-Score: [bold {z_color}]{z_score:.4f}[/] | Beta: {state_vec[1]:.4f}")

            # Log raw diagnostics for the first few pairs to debug "zero-drift"
            if pair['id'] in [p['id'] for p in self.active_pairs[:5]]:
                 logger.debug(f"DEBUG [{t_a}/{t_b}] spread={spread:.6f} inv_var={innovation_var:.6f}")

            # Only enter inside the tradeable band: beyond the stop-loss z-score a
            # fresh entry would already be in stop-out territory, so the profit
            # guard always vetoes it. Skipping here avoids a full (and pointless)
            # AI orchestration + risk pass on every scan for a persistently
            # dislocated pair.
            stop_loss_zscore = settings.STOP_LOSS_ZSCORE
            in_entry_band = abs(z_score) > entry_zscore and abs(z_score) < stop_loss_zscore
            beyond_stop = entry_zscore < stop_loss_zscore and abs(z_score) >= stop_loss_zscore

            if in_entry_band:
                signal_id = str(uuid.uuid4())
                diagnostic["reason"] = "entry_band"
                diagnostic["z_score"] = float(z_score)
                diagnostic["entry_zscore"] = float(entry_zscore)
                diagnostic["asset_class"] = "crypto" if is_crypto else "equity"
                diagnostic["near_miss"] = False
                decision_recorder.set_signal_id(signal_id)
                decision_recorder.record(
                    stage="signal",
                    outcome="continue",
                    reason="entry_band",
                    inputs={
                        "z_score": float(z_score),
                        "entry_zscore": float(entry_zscore),
                        "signal_id": signal_id,
                    },
                    signal_id=signal_id,
                )
                logger.info(f"SIGNAL [{t_a}/{t_b}] z={z_score:.3f} beta={state_vec[1]:.4f} — running AI validation")

                # Update Active Signals for Dashboard
                await self._upsert_active_signal(
                    t_a, t_b,
                    z_score=z_score,
                    status="Analyzing",
                    hedge_ratio=float(pair.get("hedge_ratio", 1.0))
                )

                # AI Validation
                # Look up this pair's sector so the orchestrator uses the right beacon asset.
                # IMPORTANT: default is "Unassigned" (not "Technology"). The orchestrator
                # maps "Unassigned" -> SPY (market-wide beacon) via BEACON_ASSETS.get(...).
                # Defaulting to "Technology" caused NVDA's 4.63% drop on 2026-04-30
                # to veto every unmapped pair (PNC/USB, healthcare, energy, etc.).
                pair_sector = resolve_pair_sector(pair["id"], t_a, t_b, settings.PAIR_SECTORS)
                signal_context = {
                    "ticker_a": t_a, "ticker_b": t_b,
                    "z_score": z_score, "dynamic_beta": state_vec[1],
                    "signal_id": signal_id,
                    "sector": pair_sector,
                }

                # Wrap orchestrator in a configurable hard deadline.
                # If any LLM call or Redis read hangs, we veto the signal rather
                # than stalling the entire scan loop for all other pairs.
                try:
                    decision_state = await asyncio.wait_for(
                        orchestrator.ainvoke({"signal_context": signal_context}),
                        timeout=settings.ORCHESTRATOR_TIMEOUT_SECONDS
                    )
                except asyncio.TimeoutError:
                    await self._upsert_active_signal(
                        t_a,
                        t_b,
                        z_score=z_score,
                        status="VETOED_TIMEOUT",
                        confidence=0.0,
                        hedge_ratio=float(pair.get("hedge_ratio", 1.0))
                    )
                    logger.warning(
                        "ORCHESTRATOR [%s/%s] timed out after %.1f s. "
                        "Vetoing signal to protect scan loop.",
                        t_a,
                        t_b,
                        float(settings.ORCHESTRATOR_TIMEOUT_SECONDS),
                    )
                    diagnostic["reason"] = "orchestrator_timeout"
                    decision_recorder.record(
                        stage="orchestrator",
                        outcome="anomaly",
                        reason="orchestrator_timeout",
                        inputs={"timeout_s": float(settings.ORCHESTRATOR_TIMEOUT_SECONDS)},
                        signal_id=signal_id,
                    )
                    return diagnostic
                await audit_service.log_thought_process(signal_id, decision_state)
                logger.info(f"ORCHESTRATOR [{t_a}/{t_b}] confidence={decision_state['final_confidence']:.3f} verdict={decision_state['final_verdict']}")
                final_confidence = float(decision_state["final_confidence"])
                hedge_ratio = resolve_hedge_ratio(pair, kalman_beta=float(state_vec[1]))
                pair["hedge_ratio"] = hedge_ratio
                pair["dynamic_beta"] = hedge_ratio
                final_verdict = str(decision_state.get("final_verdict") or "")
                orchestrator_vetoed = "VETO" in final_verdict.upper()

                if orchestrator_vetoed or final_confidence <= settings.MONITOR_MIN_AI_CONFIDENCE:
                    await self._upsert_active_signal(
                        t_a,
                        t_b,
                        z_score=z_score,
                        status="VETOED",
                        confidence=final_confidence,
                        hedge_ratio=hedge_ratio,
                    )
                    if orchestrator_vetoed:
                        logger.info(f"ORCHESTRATOR [{t_a}/{t_b}] VETOED: {final_verdict}")
                    else:
                        logger.info(f"ORCHESTRATOR [{t_a}/{t_b}] VETOED: Confidence {final_confidence:.3f} too low.")
                    diagnostic["verdict"] = "VETOED"
                    diagnostic["confidence"] = final_confidence
                    diagnostic["reason"] = "orchestrator_veto" if orchestrator_vetoed else "confidence_below_threshold"
                    decision_recorder.record(
                        stage="orchestrator",
                        outcome="veto",
                        reason=diagnostic["reason"],
                        inputs={
                            "confidence": final_confidence,
                            "verdict": final_verdict[:200],
                        },
                        signal_id=signal_id,
                    )
                    return diagnostic

                # Calculate expected profit/loss from the same gross pair
                # notional that execution will use.
                effective_sizing_base = sizing_base if sizing_base > 0 else settings.PAPER_TRADING_STARTING_CASH
                try:
                    kelly_inputs = await persistence_service.get_kelly_inputs_from_ledger()
                except Exception as kelly_exc:
                    logger.warning(
                        "Kelly ledger inputs unavailable (%s); using DEFAULT_WIN_*",
                        kelly_exc,
                    )
                    kelly_inputs = {
                        "win_prob": float(settings.DEFAULT_WIN_PROBABILITY),
                        "win_loss_ratio": float(settings.DEFAULT_WIN_LOSS_RATIO),
                        "source": "defaults_error",
                    }
                risk_res = risk_service.validate_trade(
                    ticker=f"{t_a}_{t_b}",
                    total_portfolio_cash=effective_sizing_base,
                    amount_fiat=effective_sizing_base,
                    win_prob=float(kelly_inputs["win_prob"]),
                    win_loss_ratio=float(kelly_inputs["win_loss_ratio"]),
                )
                desired_notional = cap_pair_notional(
                    float(risk_res["final_amount"]),
                    effective_sizing_base,
                    min_trade_value=settings.MIN_TRADE_VALUE,
                    max_gross_notional=settings.MAX_PAIR_GROSS_NOTIONAL_USD,
                )
                if settings.TARGET_CASH_PER_LEG > 0:
                    desired_notional = min(desired_notional, settings.TARGET_CASH_PER_LEG * 2.0)

                if desired_notional <= 0:
                    await self._upsert_active_signal(
                        t_a,
                        t_b,
                        z_score=z_score,
                        status="VETOED_SIZE",
                        confidence=final_confidence,
                        hedge_ratio=hedge_ratio,
                    )
                    diagnostic["verdict"] = "VETOED"
                    diagnostic["confidence"] = final_confidence
                    diagnostic["reason"] = "sizing_below_minimum"
                    decision_recorder.record(
                        stage="risk",
                        outcome="veto",
                        reason="sizing_below_minimum",
                        inputs={"desired_notional": desired_notional},
                        signal_id=signal_id,
                    )
                    return diagnostic

                direction = "Short-Long" if z_score > 0 else "Long-Short"
                legs = build_pair_legs(
                    price_a=price_a,
                    price_b=price_b,
                    hedge_ratio=hedge_ratio,
                    gross_notional=desired_notional,
                    direction=direction,
                )
                est_friction_pct = resolve_profit_guard_friction_pct(
                    fee_friction_pct=float(
                        risk_res["fee_status"].get("total_friction_percent", 0.0) or 0.0
                    ),
                    pair_estimated_cost_pct=float(pair.get("estimated_cost_pct") or 0.0),
                    gross_notional=float(legs.gross_notional),
                    flat_order_friction_usd=float(settings.FLAT_ORDER_FRICTION_USD),
                )
                preview = estimate_pair_profit(
                    quantity_a=legs.quantity_a,
                    gross_notional=legs.gross_notional,
                    spread=spread,
                    z_score=z_score,
                    innovation_variance=innovation_var,
                    friction_pct=est_friction_pct,
                    take_profit_zscore=settings.TAKE_PROFIT_ZSCORE,
                    stop_loss_zscore=settings.STOP_LOSS_ZSCORE,
                )
                profit_guard_details = {
                    "profit_guard_net_profit": preview.net_profit,
                    "profit_guard_gross_profit": preview.gross_profit,
                    "profit_guard_friction_usd": preview.friction_usd,
                    "profit_guard_profit_margin_pct": preview.profit_margin_pct,
                    "profit_guard_expected_loss": preview.expected_loss,
                    "profit_guard_loss_margin_pct": preview.loss_margin_pct,
                    "profit_guard_spread_capture": preview.spread_capture,
                    "profit_guard_stop_spread_move": preview.stop_spread_move,
                    "profit_guard_friction_pct": est_friction_pct,
                    "profit_guard_gross_notional": legs.gross_notional,
                    "profit_guard_quantity_a": legs.quantity_a,
                    "profit_guard_quantity_b": legs.quantity_b,
                    "profit_guard_notional_a": legs.notional_a,
                    "profit_guard_notional_b": legs.notional_b,
                    "profit_guard_side_a": legs.side_a,
                    "profit_guard_side_b": legs.side_b,
                    "profit_guard_direction": direction,
                    "profit_guard_z_score": z_score,
                    "profit_guard_spread": spread,
                    "profit_guard_innovation_variance": innovation_var,
                    "profit_guard_take_profit_zscore": settings.TAKE_PROFIT_ZSCORE,
                    "profit_guard_stop_loss_zscore": settings.STOP_LOSS_ZSCORE,
                }

                if preview.net_profit <= 0:
                    logger.info(f"PROFIT GUARD [{t_a}/{t_b}]: Net profit ${preview.net_profit:.2f} is non-positive. Vetoing.")
                    await self._upsert_active_signal(t_a, t_b, z_score=z_score, status="VETOED_UNPROFITABLE", confidence=final_confidence, hedge_ratio=hedge_ratio)
                    diagnostic["verdict"] = "VETOED"
                    diagnostic["confidence"] = final_confidence
                    diagnostic["reason"] = "unprofitable"
                    diagnostic.update(profit_guard_details)
                    decision_recorder.record(
                        stage="profit_guard",
                        outcome="veto",
                        reason="unprofitable",
                        inputs={
                            "net_profit": preview.net_profit,
                            "friction_pct": est_friction_pct,
                        },
                        signal_id=signal_id,
                    )
                    return diagnostic

                trade_summary = (
                    f"*Opportunity Found: {t_a} / {t_b}*\n\n"
                    f"*Gross Pair Notional*: ${legs.gross_notional:.2f} "
                    f"(${legs.notional_a:.2f} {legs.side_a} {t_a} / ${legs.notional_b:.2f} {legs.side_b} {t_b})\n"
                    f"*Expected Net Profit*: ${preview.net_profit:.2f} ({preview.profit_margin_pct:.2f}%) "
                    f"[Gross: ${preview.gross_profit:.2f}]\n"
                    f"*Max Loss Risk*: ${preview.expected_loss:.2f} ({preview.loss_margin_pct:.2f}%)\n"
                    f"*Est. Friction*: ${preview.friction_usd:.2f} ({est_friction_pct:.2%})\n\n"
                    f"*Stats*: Z-Score {z_score:.2f} | Hedge {hedge_ratio:.3f} | Conf {decision_state['final_confidence']:.1%}\n"
                    f"*Sizing*: Kelly {risk_res['kelly_fraction']:.2%} of base (${float(risk_res['final_amount']):.2f} gross pair notional)."
                )

                if final_confidence > settings.MONITOR_MIN_AI_CONFIDENCE:
                    # Gate before Telegram/dashboard approval — avoid spam when already open.
                    if await self._has_active_pair_or_pending_order(t_a, t_b, notify=False):
                        await self._upsert_active_signal(
                            t_a,
                            t_b,
                            z_score=z_score,
                            status="ALREADY_OPEN",
                            confidence=final_confidence,
                            hedge_ratio=hedge_ratio,
                        )
                        diagnostic["verdict"] = "SKIPPED"
                        diagnostic["confidence"] = final_confidence
                        diagnostic["reason"] = "already_open_or_pending"
                        decision_recorder.record(
                            stage="approval_gate",
                            outcome="skip",
                            reason="already_open_or_pending",
                            signal_id=signal_id,
                        )
                        return diagnostic

                    # F-015: claim pair/leg slot BEFORE approval wait so concurrent
                    # approvals cannot both clear an empty ledger and double-open.
                    from src.services.open_slot_reservation import open_slot_reservation_service

                    try:
                        open_for_claim = await persistence_service.get_open_signals()
                    except Exception:
                        open_for_claim = []
                    claim = await open_slot_reservation_service.claim(
                        signal_id=str(signal_id),
                        ticker_a=t_a,
                        ticker_b=t_b,
                        open_signals=open_for_claim,
                        canonicalize=self._canonical_position_symbol,
                        metadata={"z_score": float(z_score), "gross_notional": float(legs.gross_notional)},
                    )
                    if not claim.get("ok"):
                        diagnostic["verdict"] = "SKIPPED"
                        diagnostic["confidence"] = final_confidence
                        diagnostic["reason"] = f"slot_reservation:{claim.get('reason')}"
                        decision_recorder.record(
                            stage="slot_reservation",
                            outcome="skip",
                            reason=str(claim.get("reason")),
                            signal_id=signal_id,
                        )
                        return diagnostic

                    await self._upsert_active_signal(
                        t_a,
                        t_b,
                        z_score=z_score,
                        status="APPROVED",
                        confidence=final_confidence,
                        hedge_ratio=hedge_ratio,
                    )
                    approved = False
                    execution_result = None
                    direction = None
                    try:
                        approved = await notification_service.request_approval(
                            trade_summary,
                            trade_value=float(legs.gross_notional),
                            force_manual=True,
                        )
                        if approved:
                            direction = "Short-Long" if z_score > 0 else "Long-Short"
                            execution_result = await self.execute_trade(
                                pair,
                                direction,
                                price_a,
                                price_b,
                                signal_id,
                                entry_context={
                                    "z_score": z_score,
                                    "entry_zscore": entry_zscore,
                                    "confidence": final_confidence,
                                    "orchestrator_verdict": decision_state.get("final_verdict"),
                                },
                            )
                            if execution_result:
                                for field in SPREAD_GUARD_DETAIL_FIELDS:
                                    if field in execution_result:
                                        diagnostic[field] = execution_result[field]
                            if execution_result and execution_result.get("executed"):
                                await self._upsert_active_signal(
                                    t_a,
                                    t_b,
                                    z_score=z_score,
                                    status="EXECUTED",
                                    confidence=final_confidence,
                                    hedge_ratio=hedge_ratio,
                                )
                                diagnostic["verdict"] = "EXECUTED"
                                diagnostic["reason"] = execution_result.get("reason", "executed")
                                decision_recorder.record(
                                    stage="execute",
                                    outcome="execute",
                                    reason=diagnostic["reason"],
                                    inputs={"direction": direction},
                                    signal_id=signal_id,
                                )
                            else:
                                await self._upsert_active_signal(
                                    t_a,
                                    t_b,
                                    z_score=z_score,
                                    status="EXECUTION_BLOCKED",
                                    confidence=final_confidence,
                                    hedge_ratio=hedge_ratio,
                                )
                                diagnostic["verdict"] = "EXECUTION_BLOCKED"
                                diagnostic["reason"] = (
                                    execution_result.get("reason", "execution_blocked")
                                    if execution_result
                                    else "execution_blocked"
                                )
                                decision_recorder.record(
                                    stage="execute",
                                    outcome="anomaly",
                                    reason=diagnostic["reason"],
                                    signal_id=signal_id,
                                )
                        else:
                            await self._upsert_active_signal(
                                t_a,
                                t_b,
                                z_score=z_score,
                                status="REJECTED",
                                confidence=final_confidence,
                                hedge_ratio=hedge_ratio,
                            )
                            diagnostic["verdict"] = "REJECTED"
                            diagnostic["reason"] = "approval_denied"
                            decision_recorder.record(
                                stage="approval_gate",
                                outcome="reject",
                                reason="approval_denied",
                                signal_id=signal_id,
                            )
                    finally:
                        await open_slot_reservation_service.release(
                            str(signal_id),
                            reason=(
                                "approved_executed"
                                if (approved and execution_result and execution_result.get("executed"))
                                else "approval_denied_or_timeout"
                                if not approved
                                else "execution_blocked"
                            ),
                        )
                    try:
                        from src.services.shadow_live_divergence import (
                            shadow_live_divergence_monitor,
                        )

                        shadow_live_divergence_monitor.record_live(
                            pair_id=pair.get("id") or f"{t_a}_{t_b}",
                            decision=str(diagnostic.get("verdict") or "UNKNOWN"),
                            confidence=float(final_confidence)
                            if final_confidence is not None
                            else None,
                            signal_id=str(signal_id),
                            inputs={"z_score": float(z_score)},
                        )
                    except Exception:  # noqa: BLE001
                        pass

                diagnostic["confidence"] = final_confidence
            elif beyond_stop:
                # Past the stop-loss band — un-enterable. Surface it without an AI call.
                await self._remove_active_signal(t_a, t_b)
                diagnostic["z_score"] = float(z_score)
                diagnostic["entry_zscore"] = float(entry_zscore)
                diagnostic["asset_class"] = "crypto" if is_crypto else "equity"
                diagnostic["near_miss"] = False
                skip("beyond_stop_threshold", stage="zscore_gate", z_score=float(z_score))
            else:
                # Cleanup inactive signals
                await self._remove_active_signal(t_a, t_b)
                near_miss = abs(float(z_score)) >= float(entry_zscore) * 0.8
                diagnostic["z_score"] = float(z_score)
                diagnostic["entry_zscore"] = float(entry_zscore)
                diagnostic["asset_class"] = "crypto" if is_crypto else "equity"
                diagnostic["near_miss"] = near_miss
                skip(
                    "below_entry_threshold",
                    stage="zscore_gate",
                    z_score=float(z_score),
                    near_miss=near_miss,
                )

            return diagnostic

        except Exception as e:
            logger.error(f"Error processing pair {pair.get('ticker_a')}: {e}")
            diagnostic["reason"] = "exception"
            decision_recorder.record(
                stage="process_pair",
                outcome="anomaly",
                reason="exception",
                inputs={"error_type": type(e).__name__},
            )
            return diagnostic

    async def execute_trade(self, pair, direction, price_a, price_b, signal_id, entry_context: dict | None = None):
        """Executes a trade and logs to PostgreSQL."""
        def execution_result(executed: bool, reason: str, **details) -> dict:
            result = {"executed": executed, "reason": reason}
            result.update(details)
            return result

        entry_context = entry_context or {}
        t_a, t_b = pair['ticker_a'], pair['ticker_b']

        # F-002: daily / drawdown capital halt — block new opens only.
        try:
            from src.services.capital_halt_service import enforce_capital_halt_or_raise_state
            from src.services.performance_service import performance_service as _perf

            halt = await enforce_capital_halt_or_raise_state(
                persistence_service=persistence_service,
                performance_service=_perf,
                notification_service=notification_service,
            )
            if halt.get("halt"):
                logger.critical(
                    "CAPITAL HALT: refusing open %s/%s (%s)",
                    t_a,
                    t_b,
                    halt.get("reason"),
                )
                return execution_result(
                    False,
                    "capital_halt",
                    halt_reason=halt.get("reason"),
                    halt_details=halt.get("details"),
                )
        except Exception as halt_exc:
            logger.error("CAPITAL HALT check failed open-fail-closed: %s", halt_exc)
            return execution_result(False, "capital_halt_check_failed")

        # Phase-4: LIVE readiness checklist (paper/auto-approve lanes skip).
        try:
            from src.services.live_readiness import enforce_live_readiness_or_block

            readiness = await enforce_live_readiness_or_block(
                brokerage=self.brokerage,
                persistence_service=persistence_service,
            )
            if not readiness.get("ready"):
                logger.critical(
                    "LIVE READINESS: refusing open %s/%s failed=%s",
                    t_a,
                    t_b,
                    readiness.get("failed") or readiness.get("reason"),
                )
                return execution_result(
                    False,
                    "live_readiness_failed",
                    readiness=readiness,
                )
        except Exception as ready_exc:
            logger.error("LIVE readiness check failed open-fail-closed: %s", ready_exc)
            if not settings.should_auto_approve_trades and settings.LIVE_CAPITAL_DANGER:
                return execution_result(False, "live_readiness_check_failed")

        # Phase-5: limited-LIVE operational kill criteria.
        try:
            from src.services.limited_live_kill import evaluate_limited_live_kill

            kill = await evaluate_limited_live_kill(persistence_service=persistence_service)
            if kill.get("kill") and settings.LIVE_CAPITAL_DANGER and not settings.PAPER_TRADING:
                logger.critical(
                    "LIMITED LIVE KILL: refusing open %s/%s (%s)",
                    t_a,
                    t_b,
                    kill.get("reason"),
                )
                try:
                    await persistence_service.set_system_state(
                        "operational_status", "PAUSED_REQUIRES_MANUAL_REVIEW"
                    )
                except Exception:  # noqa: BLE001
                    pass
                return execution_result(
                    False,
                    "limited_live_kill",
                    kill_reason=kill.get("reason"),
                    kill_details=kill.get("details"),
                )
        except Exception as kill_exc:
            logger.warning("limited live kill check failed (continuing): %s", kill_exc)

        if await self._has_active_pair_or_pending_order(t_a, t_b):
            return execution_result(False, "active_pair_or_pending_order")

        # Sprint D.2: Bid-Ask Slippage Protection
        bid_a, ask_a = await data_service.get_bid_ask(t_a)
        bid_b, ask_b = await data_service.get_bid_ask(t_b)

        try:
            bid_a = float(bid_a)
            ask_a = float(ask_a)
            bid_b = float(bid_b)
            ask_b = float(ask_b)
            # Crossed quotes (ask < bid) previously produced a negative leg spread
            # and failed open under the combined threshold — reject them.
            valid_bid_ask = is_executable_bid_ask(bid_a, ask_a) and is_executable_bid_ask(
                bid_b, ask_b
            )
        except (TypeError, ValueError):
            valid_bid_ask = False

        if not valid_bid_ask:
            logger.warning(
                f"SPREAD GUARD: Missing or invalid Bid/Ask for {t_a}/{t_b}. "
                f"Rejecting trade. bid_a={bid_a} ask_a={ask_a} bid_b={bid_b} ask_b={ask_b}"
            )
            return execution_result(
                False,
                "invalid_bid_ask",
                bid_a=bid_a,
                ask_a=ask_a,
                bid_b=bid_b,
                ask_b=ask_b,
            )

        spread_a = (ask_a - bid_a) / bid_a
        spread_b = (ask_b - bid_b) / bid_b
        # Bug L-02: Proportional spread calculation
        total_spread = (1 + spread_a) * (1 + spread_b) - 1
        if total_spread > settings.SPREAD_GUARD_MAX_PCT:
            logger.warning(
                f"SPREAD GUARD: Rejecting {t_a}/{t_b}. Total Spread: {total_spread*100:.3f}% > "
                f"{settings.SPREAD_GUARD_MAX_PCT*100:.3f}% max threshold."
            )
            return execution_result(
                False,
                "spread_guard",
                bid_a=bid_a,
                ask_a=ask_a,
                bid_b=bid_b,
                ask_b=ask_b,
                spread_a_pct=spread_a * 100.0,
                spread_b_pct=spread_b * 100.0,
                total_spread_pct=total_spread * 100.0,
                max_spread_pct=settings.SPREAD_GUARD_MAX_PCT * 100.0,
            )

        # Approval / queue lag can leave scan-time mids stale. Size and submit from
        # the same executable quotes that just passed the spread guard.
        price_a = (bid_a + ask_a) / 2.0
        price_b = (bid_b + ask_b) / 2.0

        venue = self.brokerage.get_venue(t_a)
        crypto_pair = is_crypto_pair(t_a, t_b)

        # Crypto: re-check Alpaca source + quote age at execute (process_pair guard
        # may be minutes old after Telegram/dashboard approval).
        if crypto_pair:
            alpaca_crypto_sources = {"alpaca_crypto_snapshot", "alpaca_crypto_quote_mid"}
            try:
                await data_service.get_latest_price_async([t_a, t_b])
            except Exception as refresh_exc:
                logger.warning(
                    "EXECUTE PRICE REFRESH failed for %s/%s: %s",
                    t_a,
                    t_b,
                    refresh_exc,
                )
                return execution_result(False, "execute_price_refresh_failed")
            price_sources = getattr(data_service, "last_price_sources", {}) or {}
            source_a = price_sources.get(t_a)
            source_b = price_sources.get(t_b)
            if source_a not in alpaca_crypto_sources or source_b not in alpaca_crypto_sources:
                logger.warning(
                    "EXECUTE FRESHNESS [%s/%s]: crypto sources not both Alpaca "
                    "(%s=%s, %s=%s). Blocking submit.",
                    t_a,
                    t_b,
                    t_a,
                    source_a,
                    t_b,
                    source_b,
                )
                return execution_result(
                    False,
                    "execute_price_freshness_unknown",
                    source_a=source_a,
                    source_b=source_b,
                )
            price_timestamps = getattr(data_service, "last_price_timestamps", {}) or {}
            now_utc = datetime.now(timezone.utc)
            max_age = crypto_price_max_age_seconds(settings.SCAN_INTERVAL_SECONDS)
            for ticker, source in ((t_a, source_a), (t_b, source_b)):
                parsed_ts = parse_price_timestamp(price_timestamps.get(ticker))
                if parsed_ts is None:
                    logger.warning(
                        "EXECUTE FRESHNESS [%s/%s]: missing timestamp for %s (%s).",
                        t_a,
                        t_b,
                        ticker,
                        source,
                    )
                    return execution_result(
                        False,
                        "execute_price_timestamp_missing",
                        ticker=ticker,
                        source=source,
                    )
                age_seconds = (now_utc - parsed_ts).total_seconds()
                if age_seconds > max_age:
                    logger.warning(
                        "EXECUTE STALENESS [%s/%s]: %s %s age %.1fs > max %.1fs.",
                        t_a,
                        t_b,
                        ticker,
                        source,
                        age_seconds,
                        max_age,
                    )
                    return execution_result(
                        False,
                        "stale_execute_price",
                        ticker=ticker,
                        age_seconds=age_seconds,
                        max_age_seconds=max_age,
                    )
        venue_budget_cap = settings.ALPACA_BUDGET_USD

        total_cash = None
        total_equity = None
        buying_power = None
        sizing_base = 0.0
        available_for_exec = 0.0
        pending_value = 0.0
        budget_source = "unknown"

        if settings.PAPER_TRADING:
            total_cash = (
                venue_budget_cap
                if venue_budget_cap and venue_budget_cap > 0
                else settings.PAPER_TRADING_STARTING_CASH
            )
            budget_source = "paper_starting_cash"
            sizing_base = total_cash
            available_for_exec = total_cash
        else:
            try:
                maybe_cash = self.brokerage.get_account_cash()
                maybe_equity = self.brokerage.get_account_equity()
                maybe_bp = self.brokerage.get_account_buying_power()

                total_cash = await maybe_cash if inspect.isawaitable(maybe_cash) else maybe_cash
                total_equity = await maybe_equity if inspect.isawaitable(maybe_equity) else maybe_equity
                buying_power = await maybe_bp if inspect.isawaitable(maybe_bp) else maybe_bp
            except Exception as e:
                message = (
                    f"{venue} account balance read failed for {t_a}/{t_b}: {e}. "
                    "Execution blocked because account state is unknown."
                )
                logger.critical(message)
                await notification_service.send_message(message)
                return execution_result(False, "account_state_unknown")

            asset_class = "crypto" if crypto_pair else "equity"
            budget_source = f"{venue.lower()}_{asset_class}_cash"

            if total_cash is not None:
                try:
                    maybe_pending = self.brokerage.get_pending_orders_value()
                    pending_value_raw = (
                        await maybe_pending if inspect.isawaitable(maybe_pending) else maybe_pending
                    )
                    pending_value = max(0.0, float(pending_value_raw))
                except Exception as e:
                    message = (
                        f"{venue} pending-orders budget read failed for {t_a}/{t_b}: {e}. "
                        "Execution blocked because pending exposure is unknown."
                    )
                    logger.critical(message)
                    await notification_service.send_message(message)
                    return execution_result(False, "pending_exposure_unknown")

            # Use equity as the basis for sizing calculations if available
            sizing_base = total_equity if total_equity and total_equity > 0 else total_cash
            # Foreign inventory must not inflate Kelly / allocation / sector bases
            # when IGNORE_UNMANAGED_POSITIONS keeps scanning despite broker-only MV.
            if getattr(settings, "IGNORE_UNMANAGED_POSITIONS", False):
                try:
                    unmanaged_mv = await self._unmanaged_market_value()
                    sizing_base = max(0.0, float(sizing_base or 0.0) - float(unmanaged_mv or 0.0))
                except Exception as um_exc:
                    message = (
                        f"{venue} unmanaged market-value probe failed for {t_a}/{t_b}: {um_exc}. "
                        "Execution blocked because managed sizing base is unknown."
                    )
                    logger.critical(message)
                    await notification_service.send_message(message)
                    return execution_result(False, "unmanaged_mv_unknown")
            # Use buying power as the hard limit for execution
            available_for_exec = buying_power if buying_power is not None else total_cash

            # Feature 038: For crypto pairs, leverage is not available on Alpaca.
            # Hard-cap the available amount to actual cash to prevent "Insufficient Balance" errors
            # when buying power (which includes stock leverage) exceeds cash.
            if crypto_pair and available_for_exec is not None and total_cash is not None:
                available_for_exec = min(available_for_exec, total_cash)

        # If balance probes are unavailable, allow operator-defined cap-only mode.
        if total_cash is None:
            venue_budget_info = budget_service.get_venue_budget_info(venue)
            total_cash = venue_budget_info["total"] if venue_budget_info["total"] > 0 else 0.0
            sizing_base = total_cash
            available_for_exec = total_cash
            budget_source = "venue_cap_only" if total_cash > 0 else "unavailable"

        # Integrate BudgetService for tracking across sessions
        actual_available = max(0.0, float(available_for_exec) - pending_value)
        effective_cash = budget_service.get_effective_cash(venue, actual_available)
        budget_info = budget_service.get_venue_budget_info(venue)

        # Sizing base also needs to be adjusted by pending value to be conservative
        sizing_base = max(0.0, float(sizing_base) - pending_value)

        if effective_cash <= 0:
            logger.warning(
                "Venue budget exhausted/unavailable for %s (%s/%s). "
                "source=%s total=%.2f pending=%.2f used=%.2f/%.2f. "
                "Replenish budget or account balance.",
                venue, t_a, t_b, budget_source, float(total_cash), pending_value,
                budget_info["used"], budget_info["total"]
            )
            return execution_result(False, "budget_exhausted")

        # Risk sizing is applied inside RiskService (Kelly + allocation cap).
        # Pass the sizing_base (equity) so sizing is calculated according to total wallet.
        try:
            kelly_inputs = await persistence_service.get_kelly_inputs_from_ledger()
        except Exception as kelly_exc:
            logger.warning(
                "Kelly ledger inputs unavailable during execute (%s); using DEFAULT_WIN_*",
                kelly_exc,
            )
            kelly_inputs = {
                "win_prob": float(settings.DEFAULT_WIN_PROBABILITY),
                "win_loss_ratio": float(settings.DEFAULT_WIN_LOSS_RATIO),
                "source": "defaults_error",
            }
        risk_res = risk_service.validate_trade(
            ticker=f"{t_a}_{t_b}",
            total_portfolio_cash=sizing_base,
            amount_fiat=sizing_base,
            win_prob=float(kelly_inputs["win_prob"]),
            win_loss_ratio=float(kelly_inputs["win_loss_ratio"]),
        )

        if not risk_res["is_acceptable"]:
            reason = risk_res.get('rejection_reason', 'Insufficient Kelly Fraction')
            logger.warning(f"Live execute rejected by RiskService: {reason}")
            await notification_service.send_message(
                f"Execution rejected before broker for {t_a}/{t_b}: {reason}"
            )
            return execution_result(False, "risk_rejected")

        desired_notional = cap_pair_notional(
            float(risk_res["final_amount"]),
            effective_cash,
            min_trade_value=settings.MIN_TRADE_VALUE,
            max_gross_notional=settings.MAX_PAIR_GROSS_NOTIONAL_USD,
        )
        if settings.TARGET_CASH_PER_LEG > 0:
            desired_notional = min(desired_notional, settings.TARGET_CASH_PER_LEG * 2.0)

        if desired_notional <= 0:
            logger.info("Sized pair notional is below MIN_TRADE_VALUE. Skipping trade.")
            return execution_result(False, "below_min_trade_value")

        pair_id = pair.get("id") or f"{t_a}_{t_b}"
        kalman_filter = arbitrage_service.filters.get(pair_id)
        kalman_beta = float(kalman_filter.state[1]) if kalman_filter is not None else None
        hedge_ratio = resolve_hedge_ratio(pair, kalman_beta=kalman_beta)
        legs = build_pair_legs(
            price_a=price_a,
            price_b=price_b,
            hedge_ratio=hedge_ratio,
            gross_notional=desired_notional,
            direction=direction,
        )

        # Spot crypto (and any long-only venue path) cannot invent short inventory.
        # Scale gross down to what sellable qty can support before placing Leg A.
        inventory_scaled = await self._scale_legs_to_sellable_inventory(
            legs,
            ticker_a=t_a,
            ticker_b=t_b,
            price_a=price_a,
            price_b=price_b,
            hedge_ratio=hedge_ratio,
            direction=direction,
            crypto_pair=crypto_pair,
        )
        if inventory_scaled is None:
            logger.warning(
                "INVENTORY GUARD: Rejecting %s/%s %s — sell leg exceeds sellable holdings "
                "and cannot be scaled above MIN_TRADE_VALUE.",
                t_a, t_b, direction,
            )
            return execution_result(False, "insufficient_sell_inventory")
        legs = inventory_scaled

        size_a = legs.quantity_a
        size_b = legs.quantity_b
        target_cash_a = legs.notional_a
        target_cash_b = legs.notional_b

        logger.info(
            "RISK APPROVED SIZE: Gross=$%.2f, LegA=$%.2f, LegB=$%.2f for %s/%s (Hedge: %.4f, Kelly: %.4f, Base: $%.2f, MaxCap: $%.2f, CashCap: $%.2f)",
            legs.gross_notional, target_cash_a, target_cash_b, t_a, t_b, hedge_ratio, risk_res["kelly_fraction"], sizing_base, risk_res["max_allowed_fiat"], effective_cash
        )

        # Feature 008 - Sector Cluster Guard + book overcrowding gates.
        # Evaluate BEFORE the trade is placed. Open signals are loaded once and
        # reused for lane / slot / shared-leg / gross-book checks.
        pair_sector = resolve_pair_sector(pair["id"], t_a, t_b, settings.PAIR_SECTORS)
        current_portfolio = await shadow_service.get_active_portfolio_with_sectors()
        new_trade_size = target_cash_a + target_cash_b  # sum of both legs

        from src.services.portfolio_book_guards import (
            check_portfolio_gross_notional,
            check_projected_sector_exposure,
            find_shared_leg_conflict,
            gross_notional_from_signals,
            check_max_open_pairs,
        )

        sector_check = check_projected_sector_exposure(
            current_portfolio,
            pair_sector=pair_sector,
            new_trade_size=new_trade_size,
            sizing_base=sizing_base,
            max_sector_exposure=settings.MAX_SECTOR_EXPOSURE,
        )
        if not sector_check["allowed"]:
            logger.warning(
                "CLUSTER GUARD: Rejecting %s/%s. %s",
                t_a,
                t_b,
                sector_check["reason"],
            )
            return execution_result(False, "sector_exposure_guard")

        if risk_service.is_sector_frozen(sector_check["sector"]):
            logger.warning(
                "SECTOR FREEZE: Rejecting %s/%s — sector '%s' is frozen.",
                t_a,
                t_b,
                sector_check["sector"],
            )
            return execution_result(False, "sector_frozen")

        # Capture market regime for journal — logged after broker execution
        regime_info = await market_regime_service.classify_current_regime(t_a)
        if not regime_info:
            logger.warning("Regime classification unavailable for %s; defaulting to STABLE", t_a)
            regime_info = {
                "regime": "STABLE",
                "confidence": settings.MARKET_REGIME_FALLBACK_CONFIDENCE,
                "features": {},
            }

        side_a = legs.side_a
        side_b = legs.side_b
        exec_t_a = settings.DEV_EXECUTION_TICKERS.get(t_a, t_a) if settings.DEV_MODE else t_a
        exec_t_b = settings.DEV_EXECUTION_TICKERS.get(t_b, t_b) if settings.DEV_MODE else t_b

        # Mutual exclusion: SHADOW (PAPER_TRADING) XOR broker path (ALPACA_PAPER / LIVE).
        # Refuse opens that would mix shadow and broker ledger exposure in one book.
        opening_shadow = bool(settings.PAPER_TRADING)
        try:
            open_for_lane = await persistence_service.get_open_signals()
        except Exception as exc:
            logger.critical(
                "Execution blocked for %s/%s: could not load open signals for lane guard (%s).",
                t_a, t_b, exc,
            )
            return execution_result(False, "lane_guard_open_signals_unavailable")

        try:
            from src.services.open_slot_reservation import open_slot_reservation_service

            # Exclude *this* signal's reservation from the count/conflict set.
            reserved = [
                s
                for s in await open_slot_reservation_service.active_as_open_signals_async()
                if str(s.get("signal_id")) != str(signal_id)
            ]
            open_for_lane = list(open_for_lane or []) + reserved
        except Exception as exc:  # noqa: BLE001
            if settings.PAPER_TRADING or settings.should_auto_approve_trades:
                logger.warning("execute_trade: reservation merge failed (paper continue): %s", exc)
            else:
                logger.critical("execute_trade: reservation merge failed (fail-closed): %s", exc)
                return execution_result(False, "reservation_store_unavailable")

        slot_check = check_max_open_pairs(len(open_for_lane or []), settings.MAX_OPEN_PAIRS)
        if not slot_check["allowed"]:
            logger.warning(
                "OPEN PAIR CAP: Rejecting %s/%s. %s",
                t_a,
                t_b,
                slot_check["reason"],
            )
            return execution_result(False, "max_open_pairs_guard")

        if settings.BLOCK_SHARED_LEG_OPENS:
            conflict = find_shared_leg_conflict(
                t_a,
                t_b,
                open_for_lane,
                canonicalize=self._canonical_position_symbol,
            )
            if conflict:
                logger.warning(
                    "SHARED LEG GUARD: Rejecting %s/%s — overlap %s with open signal %s.",
                    t_a,
                    t_b,
                    conflict["overlap"],
                    conflict.get("signal_id"),
                )
                return execution_result(False, "shared_leg_guard")

        gross_check = check_portfolio_gross_notional(
            gross_notional_from_signals(open_for_lane),
            legs.gross_notional,
            settings.MAX_PORTFOLIO_GROSS_NOTIONAL_USD,
        )
        if not gross_check["allowed"]:
            logger.warning(
                "BOOK GROSS CAP: Rejecting %s/%s. %s",
                t_a,
                t_b,
                gross_check["reason"],
            )
            return execution_result(False, "portfolio_gross_notional_guard")

        for existing in open_for_lane or []:
            existing_shadow = signal_is_shadow(existing)
            if opening_shadow and not existing_shadow:
                msg = (
                    f"Execution blocked for {t_a}/{t_b}: open broker-lane signal "
                    f"{existing.get('signal_id')} would mix with SHADOW fills "
                    f"(no double-counting / dual ledger)."
                )
                logger.warning(msg)
                await notification_service.send_message(msg)
                return execution_result(False, "mixed_execution_lane_blocked")
            if not opening_shadow and existing_shadow:
                msg = (
                    f"Execution blocked for {t_a}/{t_b}: open SHADOW signal "
                    f"{existing.get('signal_id')} must be closed before broker-lane fills."
                )
                logger.warning(msg)
                await notification_service.send_message(msg)
                return execution_result(False, "mixed_execution_lane_blocked")

        # Feature 037: only paper mode is forced to shadow execution. In live
        # mode, crypto routes through the configured brokerage provider.
        if opening_shadow:
            await persistence_service.log_trade_journal({
                "signal_id": uuid.UUID(signal_id),
                "entry_regime": regime_info["regime"],
                "metrics_at_entry": {
                    "z_score": float(entry_context.get("z_score", risk_res.get("z_score", 0.0)) or 0.0),
                    "entry_zscore": entry_context.get("entry_zscore"),
                    "confidence": entry_context.get("confidence"),
                    "orchestrator_verdict": entry_context.get("orchestrator_verdict"),
                    "win_prob": float(kelly_inputs["win_prob"]),
                    "win_loss_ratio": float(kelly_inputs["win_loss_ratio"]),
                    "kelly_source": kelly_inputs.get("source"),
                    "regime_confidence": regime_info["confidence"],
                    "features": regime_info["features"],
                    "gross_notional": legs.gross_notional,
                    "leg_a_notional": target_cash_a,
                    "leg_b_notional": target_cash_b,
                    "hedge_ratio": hedge_ratio,
                    "kelly_fraction": risk_res.get("kelly_fraction"),
                    "sizing_base": sizing_base,
                    "max_allowed_fiat": risk_res.get("max_allowed_fiat"),
                    "direction": direction,
                    "paper_trade": True,
                    "execution_lane": LANE_SHADOW,
                    "broker_paper_trading": False,
                }
            })
            # Em paper trading, simplesmente simulamos o trade usando o shadow_service.
            # R4 fix (2026-04-19): propagate signal_id so the shadow TradeLedger row
            # can be joined with the AgentReasoning / TradeJournal rows logged for
            # this signal. Previously shadow_service generated its own UUID and
            # decorrelated the paper-trade audit trail.
            mode_tag = "PAPER TRADING"
            logger.info(f"{mode_tag}: Executing shadow trade {direction} for {t_a}/{t_b}")
            await shadow_service.execute_simulated_trade(
                pair['id'], direction, size_a, size_b, price_a, price_b,
                signal_id=signal_id,
            )
            return execution_result(True, "paper_shadow_executed")

        lane_label = settings.execution_lane
        # F-004: freeze lane knobs for this execution; abort if hot-reload flips mid-flight.
        lane_snapshot = {
            "paper_trading": bool(settings.PAPER_TRADING),
            "alpaca_base_url": (settings.ALPACA_BASE_URL or "").strip(),
            "live_capital_danger": bool(settings.LIVE_CAPITAL_DANGER),
            "execution_lane": settings.execution_lane,
        }
        logger.info(
            "%s EXECUTION: Placing broker orders for %s/%s - %s",
            lane_label, exec_t_a, exec_t_b, direction,
        )

        def _lane_drifted() -> bool:
            return (
                bool(settings.PAPER_TRADING) != lane_snapshot["paper_trading"]
                or (settings.ALPACA_BASE_URL or "").strip() != lane_snapshot["alpaca_base_url"]
                or bool(settings.LIVE_CAPITAL_DANGER) != lane_snapshot["live_capital_danger"]
            )

        # T-02: Atomic execution guard - abort if Leg A fails; emergency-close if Leg B fails
        # F-007/F-016: persist ORDER_SUBMITTED with client_order_id BEFORE broker submit.
        # Phase-4: exactly-once intent row (unique signal_id+leg / client_order_id).
        client_order_id_a = f"{signal_id}-A"
        try:
            from src.services.execution_intent_service import execution_intent_service

            intent_a = await execution_intent_service.begin_intent(
                signal_id=signal_id,
                leg="A",
                client_order_id=client_order_id_a,
                metadata={"ticker": t_a, "side": side_a, "qty": size_a},
            )
            if not intent_a.get("ok"):
                logger.critical(
                    "EXACTLY-ONCE: refusing duplicate Leg A submit signal=%s reason=%s",
                    signal_id,
                    intent_a.get("reason"),
                )
                return execution_result(False, f"exactly_once:{intent_a.get('reason')}")
        except Exception as intent_exc:
            logger.critical("EXACTLY-ONCE intent failed open-fail-closed: %s", intent_exc)
            # Broker-paper / shadow can proceed without Postgres intents; real LIVE cannot.
            if not settings.should_auto_approve_trades:
                return execution_result(False, "exactly_once_intent_unavailable")

        await persistence_service.log_trade({
            "order_id": client_order_id_a,
            "signal_id": uuid.UUID(signal_id),
            "ticker": t_a,
            "side": OrderSide.SELL if side_a == "SELL" else OrderSide.BUY,
            "quantity": size_a,
            "price": price_a,
            "status": OrderStatus.ORDER_SUBMITTED,
            "venue": venue,
            "metadata_json": {
                "client_order_id": client_order_id_a,
                "pending_broker_submit": True,
                "submitted_qty": size_a,
                "side": side_a,
                "symbol": t_a,
                "execution_lane": lane_snapshot["execution_lane"],
                "lane_snapshot": lane_snapshot,
            },
        })
        if _lane_drifted():
            await persistence_service.update_signal_status(
                uuid.UUID(signal_id), OrderStatus.NEEDS_MANUAL_RECONCILIATION
            )
            return execution_result(False, "execution_lane_changed_mid_flight")

        # Leg A
        res_a = await self.brokerage.place_value_order(
            exec_t_a,
            target_cash_a,
            side_a,
            price=price_a,
            client_order_id=client_order_id_a,
            intent="open",
        )
        order_id_a = res_a.get("order_id") or res_a.get("orderId") or res_a.get("client_order_id") or client_order_id_a
        try:
            from src.services.execution_intent_service import execution_intent_service

            await execution_intent_service.mark_submitted(
                client_order_id_a, broker_order_id=str(order_id_a)
            )
        except Exception as mark_exc:  # noqa: BLE001
            logger.warning("Could not mark Leg A intent submitted: %s", mark_exc)

        if res_a.get("requires_reconciliation") or res_a.get("status") == "unknown":
            await persistence_service.attach_broker_order_id(
                uuid.UUID(signal_id),
                client_order_id_a,
                broker_order_id=str(order_id_a),
                status=OrderStatus.NEEDS_MANUAL_RECONCILIATION,
                metadata_updates={
                    "broker_order_id": order_id_a,
                    "pending_broker_submit": False,
                    "submitted_qty": size_a,
                    "side": side_a,
                    "symbol": t_a,
                    "status": "unknown",
                    "broker_response": res_a,
                },
            )
            await persistence_service.update_signal_status(uuid.UUID(signal_id), OrderStatus.NEEDS_MANUAL_RECONCILIATION)
            alert = (
                f"Leg A ({exec_t_a}) submission state is UNKNOWN. Leg B NOT placed. "
                f"Reconcile broker by client_order_id/order_id={order_id_a}. signal_id={signal_id}"
            )
            logger.critical(alert)
            await notification_service.send_message(alert)
            return execution_result(False, "leg_a_unknown")

        status_a = OrderStatus.ORDER_SUBMITTED if res_a.get("status") != "error" else OrderStatus.LEG_A_REJECTED

        if status_a == OrderStatus.LEG_A_REJECTED:
            # P-08 (2026-04-26): Surface the broker's actual rejection reason.
            broker_msg = res_a.get("message") or res_a.get("error") or res_a
            logger.error(
                f"ATOMIC ABORT: Leg A ({exec_t_a}) failed before Leg B was placed. "
                f"No position opened. Broker response: {broker_msg}"
            )
            await persistence_service.attach_broker_order_id(
                uuid.UUID(signal_id),
                client_order_id_a,
                broker_order_id=str(order_id_a),
                status=OrderStatus.LEG_A_REJECTED,
                metadata_updates={
                    "pending_broker_submit": False,
                    "broker_response": res_a,
                    "status": "rejected",
                },
            )
            await notification_service.send_message(
                f"Execution aborted: Leg A failed for {exec_t_a}. Broker response: {broker_msg}"
            )
            return execution_result(False, "leg_a_rejected")
        # Promote the pre-submit ORDER_SUBMITTED row (matched by client_order_id).
        await persistence_service.attach_broker_order_id(
            uuid.UUID(signal_id),
            client_order_id_a,
            broker_order_id=str(order_id_a),
            status=OrderStatus.LEG_A_SUBMITTED,
            metadata_updates={
                "broker_order_id": order_id_a,
                "pending_broker_submit": False,
                "submitted_qty": size_a,
                "side": side_a,
                "symbol": t_a,
                "status": "submitted",
                "broker_response": res_a,
            },
        )

        # PATCH 5: Confirm Leg A is filled before placing Leg B.
        # Alpaca submit_order returns 'success' when order is QUEUED, not FILLED.
        # Writing to DB before fill confirmation risks a ghost position (order accepted
        # but then rejected at fill time). Poll up to 30s; treat unfilled as PENDING.
        fill_a = await self._await_order_fill(order_id_a, timeout=30)
        if not fill_a:
            await persistence_service.update_signal_status(uuid.UUID(signal_id), OrderStatus.PARTIAL_EXPOSURE)
            alert = (
                f"Leg A ({exec_t_a}) submitted but NOT confirmed filled within 30s "
                f"[order_id={order_id_a}]. Leg B NOT placed. "
                f"Check broker manually. signal_id={signal_id}"
            )
            logger.critical(alert)
            await notification_service.send_message(alert)
            return execution_result(False, "leg_a_fill_timeout")
        status_raw_a = str(fill_a.get("status", "")).lower()
        filled_qty_a = float(fill_a.get("filled_qty") or 0.0)
        fill_price_a = float(fill_a.get("filled_avg_price") or 0.0)
        expected_qty_a = float(size_a)
        leg_a_fully_filled = is_broker_fill_complete(
            status=status_raw_a,
            filled_qty=filled_qty_a,
            expected_qty=expected_qty_a,
            fill_price=fill_price_a,
            expected_notional=target_cash_a,
        )
        if status_raw_a in ("partially_filled", "partial_fill"):
            status_a = OrderStatus.LEG_A_PARTIAL
        elif status_raw_a in ("rejected", "canceled", "cancelled", "expired"):
            status_a = OrderStatus.LEG_A_REJECTED
        elif leg_a_fully_filled:
            status_a = OrderStatus.LEG_A_FILLED
            if expected_qty_a > 0 and filled_qty_a + 1e-9 < expected_qty_a:
                logger.info(
                    "Leg A (%s) filled with qty variance filled=%.8f expected=%.8f — accepting broker fill",
                    exec_t_a, filled_qty_a, expected_qty_a,
                )
        else:
            status_a = OrderStatus.NEEDS_MANUAL_RECONCILIATION

        if status_a != OrderStatus.LEG_A_FILLED:
            blocked_status = OrderStatus.PARTIAL_EXPOSURE if filled_qty_a > 0 else status_a
            if filled_qty_a > 0:
                await persistence_service.update_trade_fill(
                    uuid.UUID(signal_id),
                    order_id_a,
                    filled_quantity=filled_qty_a,
                    fill_price=fill_price_a,
                    expected_quantity=expected_qty_a,
                    metadata_updates={
                        "filled_qty": filled_qty_a,
                        "filled_avg_price": fill_price_a,
                        "order_status": blocked_status.value,
                        "fill_snapshot": fill_a,
                    },
                )
                close_side_a = "BUY" if side_a == "SELL" else "SELL"
                close_price_a = fill_price_a if fill_price_a > 0 else price_a
                close_notional_a = round(filled_qty_a * close_price_a, 2)
                if close_notional_a > 0:
                    blocked_status = OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION
                    logger.critical(
                        f"PARTIAL EXPOSURE: Leg A ({exec_t_a}) filled {filled_qty_a} "
                        f"of {expected_qty_a}. Placing emergency close before returning."
                    )
                    close_res = await self.brokerage.place_value_order(
                        exec_t_a,
                        close_notional_a,
                        close_side_a,
                        price=close_price_a,
                        client_order_id=f"{signal_id}-A-PARTIAL-CLOSE",
                        intent="close",
                    )
                    close_status = str(close_res.get("status", "")).lower()
                    close_unknown = close_res.get("requires_reconciliation") or close_status == "unknown"
                    close_order_id = (
                        close_res.get("order_id")
                        or close_res.get("orderId")
                        or close_res.get("client_order_id")
                        or f"{signal_id}-A-PARTIAL-CLOSE"
                    )
                    if close_status == "error" or close_unknown:
                        close_reason = "partial_leg_a_close_unknown" if close_unknown else "partial_leg_a_close_failed"
                        orphan_msg = (
                            f"CRITICAL - PARTIAL LEG A CLOSE {'UNKNOWN' if close_unknown else 'FAILED'}\n"
                            f"Signal: {signal_id}\n"
                            f"Ticker: {exec_t_a} ({side_a} leg)\n"
                            f"Filled quantity may still be ORPHANED. Manual intervention required.\n"
                            f"Broker response: {close_res}"
                        )
                        logger.critical(orphan_msg)
                        await notification_service.send_message(orphan_msg)
                        await persistence_service.log_trade({
                            "order_id": f"ORPHAN_{signal_id}",
                            "signal_id": uuid.UUID(signal_id),
                            "ticker": exec_t_a,
                            "side": OrderSide.SELL if side_a == "SELL" else OrderSide.BUY,
                            "quantity": filled_qty_a,
                            "price": close_price_a,
                            "status": OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION,
                            "metadata_json": {
                                "orphaned": True,
                                "reason": close_reason,
                                "broker_response": close_res,
                                "expected_qty": filled_qty_a,
                            },
                        })
                    else:
                        close_fill = await self._await_order_fill(close_order_id, timeout=30)
                        close_status_raw = str((close_fill or {}).get("status", "")).lower()
                        close_filled_qty = float((close_fill or {}).get("filled_qty") or 0.0)
                        close_ok = is_broker_fill_complete(
                            status=close_status_raw,
                            filled_qty=close_filled_qty,
                            expected_qty=filled_qty_a,
                            fill_price=float((close_fill or {}).get("filled_avg_price") or close_price_a),
                            expected_notional=close_notional_a,
                        )
                        if not close_ok:
                            orphan_msg = (
                                f"CRITICAL - PARTIAL LEG A CLOSE UNCONFIRMED\n"
                                f"Signal: {signal_id}\n"
                                f"Ticker: {exec_t_a} ({side_a} leg)\n"
                                f"Filled quantity may still be ORPHANED. Manual intervention required.\n"
                                f"Close order: {close_order_id}\n"
                                f"Close status: {close_status_raw or 'unknown'} filled_qty={close_filled_qty} "
                                f"expected_qty={filled_qty_a}\n"
                                f"Broker response: {close_res}"
                            )
                            logger.critical(orphan_msg)
                            await notification_service.send_message(orphan_msg)
                            await persistence_service.log_trade({
                                "order_id": f"ORPHAN_{signal_id}",
                                "signal_id": uuid.UUID(signal_id),
                                "ticker": exec_t_a,
                                "side": OrderSide.SELL if side_a == "SELL" else OrderSide.BUY,
                                "quantity": filled_qty_a,
                                "price": close_price_a,
                                "status": OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION,
                                "metadata_json": {
                                    "orphaned": True,
                                    "reason": "partial_leg_a_close_unconfirmed",
                                    "broker_response": close_res,
                                    "close_order_id": close_order_id,
                                    "close_fill": close_fill,
                                    "expected_qty": filled_qty_a,
                                },
                            })
                        else:
                            logger.info(
                                "PARTIAL LEG A CLOSE SUCCESS: %s unwind filled "
                                "[order_id=%s filled_qty=%s]. Marking signal CLOSED.",
                                exec_t_a, close_order_id, close_filled_qty,
                            )
                            await persistence_service.close_trade(
                                uuid.UUID(signal_id),
                                exit_prices={exec_t_a: close_price_a},
                                pnl=0.0,
                                exit_reason=ExitReason.MANUAL,
                            )
                            blocked_status = OrderStatus.CLOSED
            await persistence_service.update_signal_status(uuid.UUID(signal_id), blocked_status)
            if blocked_status == OrderStatus.CLOSED:
                logger.info(
                    "Leg A (%s) incomplete fill was unwound and ledger closed. signal_id=%s",
                    exec_t_a, signal_id,
                )
                return execution_result(False, "leg_a_unwound")
            alert = (
                f"Leg A ({exec_t_a}) was not confirmed as a full fill. "
                f"Leg B NOT placed. status={status_raw_a or 'unknown'} "
                f"filled_qty={filled_qty_a} expected_qty={expected_qty_a} "
                f"order_id={order_id_a} signal_id={signal_id}"
            )
            logger.critical(alert)
            await notification_service.send_message(alert)
            return execution_result(False, "leg_a_not_fully_filled")

        # Small delay between legs to avoid broker-side burst throttling.
        await asyncio.sleep(1.0)

        # Leg B — exactly-once intent before submit
        client_order_id_b = f"{signal_id}-B"
        intent_b_ok = True
        try:
            from src.services.execution_intent_service import execution_intent_service

            intent_b = await execution_intent_service.begin_intent(
                signal_id=signal_id,
                leg="B",
                client_order_id=client_order_id_b,
                metadata={"ticker": t_b, "side": side_b, "qty": size_b},
            )
            if not intent_b.get("ok"):
                intent_b_ok = False
                logger.critical(
                    "EXACTLY-ONCE: duplicate Leg B intent signal=%s reason=%s",
                    signal_id,
                    intent_b.get("reason"),
                )
                if not settings.should_auto_approve_trades:
                    res_b = {
                        "status": "error",
                        "message": f"exactly_once:{intent_b.get('reason')}",
                    }
                    order_id_b = client_order_id_b
                else:
                    # Paper/broker-paper: treat as already-intent'd and continue place.
                    intent_b_ok = True
        except Exception as intent_b_exc:
            logger.critical("Leg B intent unavailable: %s", intent_b_exc)
            if not settings.should_auto_approve_trades:
                res_b = {"status": "error", "message": str(intent_b_exc)}
                order_id_b = client_order_id_b
                intent_b_ok = False
            else:
                intent_b_ok = True

        if intent_b_ok:
            res_b = await self.brokerage.place_value_order(
                exec_t_b,
                target_cash_b,
                side_b,
                price=price_b,
                client_order_id=client_order_id_b,
                intent="open",
            )
            order_id_b = (
                res_b.get("order_id")
                or res_b.get("orderId")
                or res_b.get("client_order_id")
                or client_order_id_b
            )
            try:
                from src.services.execution_intent_service import execution_intent_service

                await execution_intent_service.mark_submitted(
                    client_order_id_b, broker_order_id=str(order_id_b)
                )
            except Exception as mark_exc:  # noqa: BLE001
                logger.warning("Could not mark Leg B intent submitted: %s", mark_exc)

        if res_b.get("requires_reconciliation") or res_b.get("status") == "unknown":
            await persistence_service.log_trade({
                "order_id": order_id_b,
                "signal_id": uuid.UUID(signal_id),
                "ticker": t_b,
                "side": OrderSide.BUY if side_b == "BUY" else OrderSide.SELL,
                "quantity": size_b,
                "price": price_b,
                "status": OrderStatus.NEEDS_MANUAL_RECONCILIATION,
                "venue": venue,
                "metadata_json": {
                    "broker_order_id": order_id_b,
                    "submitted_qty": size_b,
                    "side": side_b,
                    "symbol": t_b,
                    "status": "unknown",
                    "broker_response": res_b,
                }
            })
            await persistence_service.update_signal_status(uuid.UUID(signal_id), OrderStatus.NEEDS_MANUAL_RECONCILIATION)
            alert = (
                f"Leg B ({exec_t_b}) submission state is UNKNOWN. No retry or emergency close attempted. "
                f"Reconcile broker by client_order_id/order_id={order_id_b}. signal_id={signal_id}"
            )
            logger.critical(alert)
            await notification_service.send_message(alert)
            return execution_result(False, "leg_b_unknown")

        status_b = OrderStatus.LEG_B_SUBMITTED if res_b.get("status") != "error" else OrderStatus.LEG_B_REJECTED

        if status_b == OrderStatus.LEG_B_REJECTED:
            await persistence_service.update_signal_status(uuid.UUID(signal_id), OrderStatus.LEG_A_FILLED)
            order_id_b = res_b.get("order_id") or res_b.get("orderId") or str(uuid.uuid4())

        await persistence_service.log_trade({
            "order_id": order_id_b,
            "signal_id": uuid.UUID(signal_id),
            "ticker": t_b,
            "side": OrderSide.BUY if side_b == "BUY" else OrderSide.SELL,
            "quantity": size_b,
            "price": price_b,
            "status": (
                OrderStatus.LEG_B_REJECTED
                if status_b == OrderStatus.LEG_B_REJECTED
                else OrderStatus.LEG_B_SUBMITTED
            ),
            "venue": venue,
            "metadata_json": {
                "broker_order_id": order_id_b,
                "submitted_qty": size_b,
                "side": side_b,
                "symbol": t_b,
                "status": "rejected" if status_b == OrderStatus.LEG_B_REJECTED else "submitted",
                "broker_response": res_b,
            }
        })

        async def emergency_close_leg_a_after_leg_b_failure(broker_msg_b):
            await persistence_service.update_signal_status(uuid.UUID(signal_id), OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION)
            logger.critical(
                f"ATOMIC FAILURE: Leg A ({exec_t_a}) succeeded but Leg B ({exec_t_b}) failed. "
                f"Broker response: {broker_msg_b}. "
                f"Placing emergency close on Leg A to prevent orphaned directional exposure."
            )
            close_side_a = "BUY" if side_a == "SELL" else "SELL"
            # Close the actual filled exposure, not the pre-trade plan notional.
            # Planned mid-price size can under-close when the broker overfills Leg A.
            close_price_a = fill_price_a if fill_price_a > 0 else price_a
            expected_close_qty = filled_qty_a if filled_qty_a > 0 else size_a
            close_notional_a = round(float(expected_close_qty) * float(close_price_a), 2)
            if close_notional_a <= 0:
                close_notional_a = round(float(target_cash_a), 2)
            close_res = await self.brokerage.place_value_order(
                exec_t_a,
                close_notional_a,
                close_side_a,
                price=close_price_a,
                client_order_id=f"{signal_id}-A-EMERGENCY-CLOSE",
                intent="close",
            )
            close_status = str(close_res.get("status", "")).lower()
            close_unknown = close_res.get("requires_reconciliation") or close_status == "unknown"
            close_order_id = (
                close_res.get("order_id")
                or close_res.get("orderId")
                or close_res.get("client_order_id")
                or f"{signal_id}-A-EMERGENCY-CLOSE"
            )
            if close_status == "error" or close_unknown:
                close_reason = "emergency_close_unknown" if close_unknown else "emergency_close_failed"
                orphan_msg = (
                    f"CRITICAL - EMERGENCY CLOSE {'UNKNOWN' if close_unknown else 'FAILED'}\n"
                    f"Signal: {signal_id}\n"
                    f"Ticker: {exec_t_a} ({side_a} leg)\n"
                    f"The position may still be ORPHANED. Manual intervention required.\n"
                    f"Broker response: {close_res}"
                )
                logger.critical(orphan_msg)
                await notification_service.send_message(orphan_msg)
                await persistence_service.log_trade({
                    "order_id": f"ORPHAN_{signal_id}",
                    "signal_id": uuid.UUID(signal_id),
                    "ticker": exec_t_a,
                    "side": OrderSide.SELL if side_a == "SELL" else OrderSide.BUY,
                    "quantity": expected_close_qty,
                    "price": close_price_a,
                    "status": OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION,
                    "metadata_json": {
                        "orphaned": True,
                        "reason": close_reason,
                        "broker_response": close_res,
                        "expected_qty": expected_close_qty,
                        "close_notional": close_notional_a,
                    },
                })
            else:
                close_fill = await self._await_order_fill(close_order_id, timeout=30)
                close_status_raw = str((close_fill or {}).get("status", "")).lower()
                close_filled_qty = float((close_fill or {}).get("filled_qty") or 0.0)
                close_ok = is_broker_fill_complete(
                    status=close_status_raw,
                    filled_qty=close_filled_qty,
                    expected_qty=expected_close_qty,
                    fill_price=float((close_fill or {}).get("filled_avg_price") or close_price_a),
                    expected_notional=close_notional_a,
                )
                if not close_ok:
                    orphan_msg = (
                        f"CRITICAL - EMERGENCY CLOSE UNCONFIRMED\n"
                        f"Signal: {signal_id}\n"
                        f"Ticker: {exec_t_a} ({side_a} leg)\n"
                        f"The position may still be ORPHANED. Manual intervention required.\n"
                        f"Close order: {close_order_id}\n"
                        f"Close status: {close_status_raw or 'unknown'} filled_qty={close_filled_qty} "
                        f"expected_qty={expected_close_qty}\n"
                        f"Broker response: {close_res}"
                    )
                    logger.critical(orphan_msg)
                    await notification_service.send_message(orphan_msg)
                    await persistence_service.log_trade({
                        "order_id": f"ORPHAN_{signal_id}",
                        "signal_id": uuid.UUID(signal_id),
                        "ticker": exec_t_a,
                        "side": OrderSide.SELL if side_a == "SELL" else OrderSide.BUY,
                        "quantity": expected_close_qty,
                        "price": close_price_a,
                        "status": OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION,
                        "metadata_json": {
                            "orphaned": True,
                            "reason": "emergency_close_unconfirmed",
                            "broker_response": close_res,
                            "close_order_id": close_order_id,
                            "close_fill": close_fill,
                            "expected_qty": expected_close_qty,
                            "close_notional": close_notional_a,
                        },
                    })
                else:
                    logger.info(
                        f"EMERGENCY CLOSE SUCCESS: Orphaned {exec_t_a} position closed "
                        f"[order_id={close_order_id}]. Marking signal CLOSED."
                    )
                    await persistence_service.close_trade(
                        uuid.UUID(signal_id),
                        exit_prices={exec_t_a: close_price_a},
                        pnl=0.0,
                        exit_reason=ExitReason.MANUAL,
                    )

        if status_b == OrderStatus.LEG_B_REJECTED:
            broker_msg_b = res_b.get("message") or res_b.get("error") or res_b
            await emergency_close_leg_a_after_leg_b_failure(broker_msg_b)
            return execution_result(False, "leg_b_rejected")
        fill_b = await self._await_order_fill(order_id_b, timeout=30)
        if not fill_b:
            await persistence_service.update_trade_fill(
                uuid.UUID(signal_id),
                order_id_a,
                filled_quantity=filled_qty_a,
                fill_price=fill_price_a,
                status=OrderStatus.NEEDS_MANUAL_RECONCILIATION,
                expected_quantity=expected_qty_a,
                metadata_updates={
                    "filled_qty": filled_qty_a,
                    "filled_avg_price": fill_price_a,
                    "order_status": status_a.value,
                    "pair_status": OrderStatus.NEEDS_MANUAL_RECONCILIATION.value,
                    "fill_snapshot": fill_a,
                },
            )
            await persistence_service.update_signal_status(
                uuid.UUID(signal_id),
                OrderStatus.NEEDS_MANUAL_RECONCILIATION,
            )
            alert = (
                f"Leg B ({exec_t_b}) not terminal within 30s. "
                f"Signal marked NEEDS_MANUAL_RECONCILIATION; Leg B fill quantity is unknown "
                f"and ledger was not advanced from requested size. "
                f"order_id={order_id_b} signal_id={signal_id}"
            )
            logger.critical(alert)
            await notification_service.send_message(alert)
            return execution_result(False, "leg_b_fill_timeout")

        status_raw_b = str(fill_b.get("status", "")).lower()
        filled_qty_b = float(fill_b.get("filled_qty") or 0.0)
        fill_price_b = float(fill_b.get("filled_avg_price") or 0.0)
        expected_qty_b = float(size_b)
        leg_b_fully_filled = is_broker_fill_complete(
            status=status_raw_b,
            filled_qty=filled_qty_b,
            expected_qty=expected_qty_b,
            fill_price=fill_price_b,
            expected_notional=target_cash_b,
        )
        if status_raw_b in ("partially_filled", "partial_fill"):
            status_b = OrderStatus.LEG_B_PARTIAL
        elif status_raw_b in ("rejected", "canceled", "cancelled", "expired"):
            status_b = OrderStatus.LEG_B_REJECTED
        elif leg_b_fully_filled:
            status_b = OrderStatus.LEG_B_FILLED
            if expected_qty_b > 0 and filled_qty_b + 1e-9 < expected_qty_b:
                logger.info(
                    "Leg B (%s) filled with qty variance filled=%.8f expected=%.8f — accepting broker fill",
                    exec_t_b, filled_qty_b, expected_qty_b,
                )
        else:
            status_b = OrderStatus.NEEDS_MANUAL_RECONCILIATION

        if status_b == OrderStatus.LEG_B_REJECTED:
            broker_msg_b = fill_b.get("message") or fill_b.get("error") or fill_b or res_b
            await emergency_close_leg_a_after_leg_b_failure(broker_msg_b)
            return execution_result(False, "leg_b_rejected_after_submit")

        if status_b != OrderStatus.LEG_B_FILLED:
            # Incomplete / shortfall Leg B: persist actual fills (never ghost the plan size)
            # and flatten both legs to avoid leaving hedged imbalance as OPEN_PAIR.
            await persistence_service.update_trade_fill(
                uuid.UUID(signal_id),
                order_id_a,
                filled_quantity=filled_qty_a,
                fill_price=fill_price_a,
                status=OrderStatus.PARTIAL_EXPOSURE,
                expected_quantity=expected_qty_a,
                metadata_updates={
                    "filled_qty": filled_qty_a,
                    "filled_avg_price": fill_price_a,
                    "order_status": status_a.value,
                    "pair_status": OrderStatus.PARTIAL_EXPOSURE.value,
                    "fill_snapshot": fill_a,
                },
            )
            await persistence_service.update_trade_fill(
                uuid.UUID(signal_id),
                order_id_b,
                filled_quantity=filled_qty_b,
                fill_price=fill_price_b,
                status=OrderStatus.PARTIAL_EXPOSURE,
                expected_quantity=expected_qty_b,
                metadata_updates={
                    "filled_qty": filled_qty_b,
                    "filled_avg_price": fill_price_b,
                    "order_status": status_b.value,
                    "pair_status": OrderStatus.PARTIAL_EXPOSURE.value,
                    "fill_snapshot": fill_b,
                },
            )
            await persistence_service.update_signal_status(
                uuid.UUID(signal_id),
                OrderStatus.PARTIAL_EXPOSURE,
            )
            alert = (
                f"Leg B ({exec_t_b}) was not confirmed as a full fill. "
                f"status={status_raw_b or 'unknown'} "
                f"filled_qty={filled_qty_b} expected_qty={expected_qty_b} "
                f"order_id={order_id_b} signal_id={signal_id}. "
                f"Flattening Leg A and any Leg B fill to clear imbalance."
            )
            logger.critical(alert)
            await notification_service.send_message(alert)

            if filled_qty_b > 0:
                close_side_b = "BUY" if side_b == "SELL" else "SELL"
                close_price_b = fill_price_b if fill_price_b > 0 else price_b
                close_notional_b = round(filled_qty_b * close_price_b, 2)
                if close_notional_b > 0:
                    close_b_res = await self.brokerage.place_value_order(
                        exec_t_b,
                        close_notional_b,
                        close_side_b,
                        price=close_price_b,
                        client_order_id=f"{signal_id}-B-PARTIAL-CLOSE",
                        intent="close",
                    )
                    close_b_status = str(close_b_res.get("status", "")).lower()
                    close_b_unknown = (
                        close_b_res.get("requires_reconciliation") or close_b_status == "unknown"
                    )
                    if close_b_status == "error" or close_b_unknown:
                        await persistence_service.update_signal_status(
                            uuid.UUID(signal_id),
                            OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION,
                        )
                        orphan_msg = (
                            f"CRITICAL - PARTIAL LEG B CLOSE "
                            f"{'UNKNOWN' if close_b_unknown else 'FAILED'}\n"
                            f"Signal: {signal_id}\n"
                            f"Ticker: {exec_t_b}\n"
                            f"Broker response: {close_b_res}"
                        )
                        logger.critical(orphan_msg)
                        await notification_service.send_message(orphan_msg)
                        await emergency_close_leg_a_after_leg_b_failure(close_b_res)
                        return execution_result(False, "leg_b_partial_close_failed")

                    close_b_order_id = (
                        close_b_res.get("order_id")
                        or close_b_res.get("orderId")
                        or close_b_res.get("client_order_id")
                        or f"{signal_id}-B-PARTIAL-CLOSE"
                    )
                    close_b_fill = await self._await_order_fill(close_b_order_id, timeout=30)
                    close_b_status_raw = str((close_b_fill or {}).get("status", "")).lower()
                    close_b_filled_qty = float((close_b_fill or {}).get("filled_qty") or 0.0)
                    close_b_ok = is_broker_fill_complete(
                        status=close_b_status_raw,
                        filled_qty=close_b_filled_qty,
                        expected_qty=filled_qty_b,
                        fill_price=float(
                            (close_b_fill or {}).get("filled_avg_price") or close_price_b
                        ),
                        expected_notional=close_notional_b,
                    )
                    if not close_b_ok:
                        await persistence_service.update_signal_status(
                            uuid.UUID(signal_id),
                            OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION,
                        )
                        orphan_msg = (
                            f"CRITICAL - PARTIAL LEG B CLOSE UNCONFIRMED\n"
                            f"Signal: {signal_id}\n"
                            f"Ticker: {exec_t_b}\n"
                            f"Close order: {close_b_order_id}\n"
                            f"Close status: {close_b_status_raw or 'unknown'} "
                            f"filled_qty={close_b_filled_qty} expected_qty={filled_qty_b}"
                        )
                        logger.critical(orphan_msg)
                        await notification_service.send_message(orphan_msg)
                        await emergency_close_leg_a_after_leg_b_failure(orphan_msg)
                        return execution_result(False, "leg_b_partial_close_unconfirmed")

            await emergency_close_leg_a_after_leg_b_failure(
                f"leg_b_incomplete status={status_raw_b} filled_qty={filled_qty_b}"
            )
            return execution_result(False, "leg_b_not_fully_filled")

        pair_status = OrderStatus.OPEN_PAIR
        visible_status = pair_status

        # M-05: Journal written only after both broker legs have returned successfully
        await persistence_service.log_trade_journal({
            "signal_id": uuid.UUID(signal_id),
            "entry_regime": regime_info["regime"],
            "metrics_at_entry": {
                "z_score": float(entry_context.get("z_score", risk_res.get("z_score", 0.0)) or 0.0),
                "entry_zscore": entry_context.get("entry_zscore"),
                "confidence": entry_context.get("confidence"),
                "orchestrator_verdict": entry_context.get("orchestrator_verdict"),
                "win_prob": float(kelly_inputs["win_prob"]),
                "win_loss_ratio": float(kelly_inputs["win_loss_ratio"]),
                "kelly_source": kelly_inputs.get("source"),
                "regime_confidence": regime_info["confidence"],
                "features": regime_info["features"],
                "paper_trade": False,
                "execution_lane": settings.execution_lane,
                "broker_paper_trading": bool(settings.is_broker_paper_trading),
            }
        })

        await persistence_service.update_trade_fill(
            uuid.UUID(signal_id),
            order_id_a,
            filled_quantity=filled_qty_a if filled_qty_a > 0 else size_a,
            fill_price=fill_price_a if fill_price_a > 0 else price_a,
            status=visible_status,
            expected_quantity=expected_qty_a,
            metadata_updates={
                "filled_qty": filled_qty_a,
                "filled_avg_price": fill_price_a,
                "order_status": status_a.value,
                "pair_status": pair_status.value,
                "fill_snapshot": fill_a,
            },
        )
        await persistence_service.update_trade_fill(
            uuid.UUID(signal_id),
            order_id_b,
            filled_quantity=filled_qty_b if filled_qty_b > 0 else size_b,
            fill_price=fill_price_b if fill_price_b > 0 else price_b,
            status=visible_status,
            expected_quantity=expected_qty_b,
            metadata_updates={
                "filled_qty": filled_qty_b,
                "filled_avg_price": fill_price_b,
                "order_status": status_b.value,
                "pair_status": pair_status.value,
                "fill_snapshot": fill_b,
            },
        )

        logger.info(
            f"TRADE EXECUTED: {t_a}/{t_b} {direction} | Status: "
            f"A={OrderStatus.LEG_A_FILLED.value}, B={OrderStatus.LEG_B_FILLED.value}"
        )
        return execution_result(True, pair_status.value)

    async def _bench_pair_for_health(
        self,
        pair: dict,
        *,
        hedge_ratio: float | None = None,
        reason: str,
    ) -> None:
        """Persist Benched + drop from in-memory Active so the slot can refill."""
        pair_id = str(pair.get("id") or f"{pair.get('ticker_a')}_{pair.get('ticker_b')}")
        ticker_a = pair.get("ticker_a")
        ticker_b = pair.get("ticker_b")
        try:
            hedge = float(hedge_ratio if hedge_ratio is not None else pair.get("hedge_ratio") or 0.0)
        except (TypeError, ValueError):
            hedge = 0.0
        pair["is_cointegrated"] = False
        try:
            await persistence_service.save_trading_pairs([{
                "id": pair_id,
                "ticker_a": ticker_a,
                "ticker_b": ticker_b,
                "hedge_ratio": hedge,
                "is_cointegrated": False,
                "status": "Benched",
            }])
        except Exception as persist_exc:
            logger.warning("Failed to bench %s after %s: %s", pair_id, reason, persist_exc)
            try:
                await persistence_service.update_pair_status(pair_id, "Benched")
            except Exception:
                pass
        # Drop from the live scan list without waiting for a full reload.
        self.active_pairs = [p for p in self.active_pairs if str(p.get("id") or "") != pair_id]
        self.last_cointegration_check.pop(pair_id, None)
        logger.info("BENCHED %s (%s); Active now %d pairs.", pair_id, reason, len(self.active_pairs))

    async def _recheck_cointegration(self, pair: dict):
        """
        Re-validates the ADF cointegration test for a single pair using the
        last 30 days of hourly data.  Called once per calendar day per pair.

        On break (static ADF or rolling stability), the pair is benched so it
        no longer occupies an Active scan slot. Open positions still exit via
        the separate open-signal exit loop. A Telegram/console alert is fired
        on break events.
        """
        t_a, t_b = pair['ticker_a'], pair['ticker_b']
        pair_id = str(pair.get("id") or f"{t_a}_{t_b}")
        async with self._coint_recheck_sem:
            await self._recheck_cointegration_body(pair, pair_id=pair_id, t_a=t_a, t_b=t_b)

    async def _recheck_cointegration_body(self, pair: dict, *, pair_id: str, t_a: str, t_b: str):
        try:
            hist_data = await data_service.get_historical_data_async([t_a, t_b], "30d", "1h")
            if hist_data is None or hist_data.empty:
                return

            hist_data = normalize_history_close_frame(hist_data)
            if hist_data is None or hist_data.empty:
                return
            col_a = resolve_history_column(hist_data.columns, t_a)
            col_b = resolve_history_column(hist_data.columns, t_b)
            if not col_a or not col_b:
                return

            if ArbitrageService.series_has_corporate_action_jump(
                hist_data[col_a],
                hist_data[col_b],
                threshold=settings.CORP_ACTION_PRICE_JUMP_PCT,
            ):
                msg = (
                    f"CORP ACTION JUMP: {t_a}/{t_b} single-bar move exceeds "
                    f"{settings.CORP_ACTION_PRICE_JUMP_PCT:.0%}. "
                    f"Invalidating Kalman and benching pair."
                )
                logger.warning(msg)
                await arbitrage_service.invalidate_pair_state(
                    pair_id, reason="corporate_action_jump"
                )
                await self._bench_pair_for_health(pair, reason="corporate_action_jump")
                await notification_service.send_message(msg)
                return

            is_crypto = is_crypto_pair(t_a, t_b)
            p_thresh = (
                settings.CRYPTO_COINTEGRATION_PVALUE_THRESHOLD
                if is_crypto
                else settings.COINTEGRATION_PVALUE_THRESHOLD
            )
            pass_thresh = 0.2 if is_crypto else settings.COINTEGRATION_ROLLING_PASS_RATE

            is_coint, p_val, hedge = arbitrage_service.check_cointegration(
                hist_data[col_a], hist_data[col_b], pvalue_threshold=p_thresh
            )

            from src.services.pair_discovery_helpers import is_hedge_ratio_sane, max_abs_hedge_limit

            hedge_cap = max_abs_hedge_limit(t_a, t_b)
            if hedge is not None and not is_hedge_ratio_sane(
                hedge,
                max_abs_hedge=hedge_cap,
                min_abs_hedge=settings.PAIR_DISCOVERY_MIN_ABS_HEDGE,
            ):
                msg = (
                    f"HEDGE BREAK: {t_a}/{t_b} hedge_ratio={float(hedge):.3f} outside "
                    f"[{settings.PAIR_DISCOVERY_MIN_ABS_HEDGE:.3f}, "
                    f"{hedge_cap:.1f}] abs. "
                    f"Pair benched to free Active slot."
                )
                logger.warning(msg)
                await self._bench_pair_for_health(pair, hedge_ratio=float(hedge), reason="extreme_hedge")
                await notification_service.send_message(msg)
                return

            # Spec 037: rolling-window stability. If the pair was statically
            # cointegrated but rolling-window unstable, bench it. The
            # daily re-check is the right place to apply this because it
            # already runs once per pair per day with a fresh history pull.
            if is_coint and settings.COINTEGRATION_ROLLING_ENABLED:
                stability = ArbitrageService.check_rolling_cointegration(
                    hist_data[col_a],
                    hist_data[col_b],
                    window=settings.COINTEGRATION_ROLLING_WINDOW,
                    step=settings.COINTEGRATION_ROLLING_STEP,
                    min_pass_rate=pass_thresh,
                    pvalue_threshold=p_thresh,
                )
                pair["coint_stability"] = stability
                if not stability["stable"]:
                    is_coint = False
                    logger.info(
                        "ROLLING COINT FAIL on re-check %s/%s: pass_rate=%.2f median_p=%.3f",
                        t_a,
                        t_b,
                        stability["pass_rate"],
                        stability["median_pvalue"],
                    )

            previously_coint = pair.get('is_cointegrated', True)

            if not is_coint:
                if previously_coint:
                    msg = (
                        f"COINTEGRATION BREAK: {t_a}/{t_b} - "
                        f"ADF p-value={p_val:.4f} (thresh={p_thresh:.3f}). "
                        f"Pair benched to free Active scan slot."
                    )
                    logger.warning(msg)
                    await notification_service.send_message(msg)
                else:
                    logger.debug(
                        f"[{t_a}/{t_b}] Still non-cointegrated (p={p_val:.4f}). "
                        f"Benching Active slot."
                    )
                await self._bench_pair_for_health(
                    pair,
                    hedge_ratio=float(hedge) if hedge is not None else None,
                    reason="cointegration_break",
                )
            else:
                pair['is_cointegrated'] = True
                if hedge is not None:
                    try:
                        pair["hedge_ratio"] = float(hedge)
                    except (TypeError, ValueError):
                        pass
                if not previously_coint:
                    # Soft restore in-memory only; promotion back to Active goes
                    # through elite rotation / operator promote so quality gates apply.
                    msg = (
                        f"COINTEGRATION RESTORED: {t_a}/{t_b} - "
                        f"ADF p-value={p_val:.4f}. Eligible for re-promotion."
                    )
                    logger.info(msg)
                    await notification_service.send_message(msg)
                else:
                    logger.debug(
                        f"[{t_a}/{t_b}] Cointegration confirmed (p={p_val:.4f})."
                    )
                    # Keep DB hedge / coint flag fresh for rotation audits.
                    try:
                        await persistence_service.save_trading_pairs([{
                            "id": pair_id,
                            "ticker_a": t_a,
                            "ticker_b": t_b,
                            "hedge_ratio": float(pair.get("hedge_ratio") or hedge or 0.0),
                            "is_cointegrated": True,
                            "status": "Active",
                        }])
                    except Exception as persist_exc:
                        logger.debug("Cointegration confirm persist failed for %s: %s", pair_id, persist_exc)
        except Exception as e:
            logger.error(f"Error re-checking cointegration for {t_a}/{t_b}: {e}")

    async def _run_startup_auto_reconciliation(self) -> None:
        """Ordered startup repair before fail-fast counting.

        1. CLOSING → NEEDS_MANUAL (avoid duplicate close orders)
        2. Ledger-close signals whose broker close orders are already filled
        3. Restore broker-confirmed filled pair legs to OPEN_PAIR
        4. Close flat orphan/failed rows when broker is flat
        5. Log signal-level reconciliation plans (read-only audit)
        """
        await persistence_service.convert_closing_signals_for_startup()

        try:
            from src.services.ledger_reconcile_service import (
                auto_reconcile_broker_confirmed_closes,
            )

            close_summary = await auto_reconcile_broker_confirmed_closes(
                brokerage=self.brokerage,
                dry_run=False,
            )
            if close_summary.get("closed"):
                logger.info(
                    "Startup auto-reconcile closed %s signal(s) with broker-confirmed close fills "
                    "(examined=%s blocked=%s).",
                    close_summary.get("closed"),
                    close_summary.get("signals_examined"),
                    close_summary.get("blocked"),
                )
        except Exception as exc:
            logger.warning(
                "Startup broker-confirmed close reconcile failed (continuing with fail-fast): %s",
                exc,
            )

        if settings.auto_reconcile_broker_confirmed_pairs:
            try:
                from src.services.ledger_reconcile_service import (
                    auto_reconcile_broker_confirmed_pairs,
                )

                summary = await auto_reconcile_broker_confirmed_pairs(
                    brokerage=self.brokerage,
                    dry_run=False,
                )
                if summary.get("restored"):
                    logger.info(
                        "Startup auto-reconcile restored %s broker-confirmed pair leg(s) "
                        "(signals_examined=%s examined=%s blocked=%s).",
                        summary.get("restored"),
                        summary.get("signals_examined"),
                        summary.get("examined"),
                        summary.get("blocked"),
                    )
            except Exception as exc:
                logger.warning(
                    "Startup broker-confirmed auto-reconcile failed (continuing with fail-fast): %s",
                    exc,
                )

        if settings.auto_reconcile_flat_orphans:
            try:
                from src.services.ledger_reconcile_service import auto_close_flat_orphans

                summary = await auto_close_flat_orphans(brokerage=self.brokerage, dry_run=False)
                if summary.get("closed"):
                    logger.info(
                        "Startup auto-reconcile closed %s flat orphan/failed ledger row(s) "
                        "(examined=%s blocked=%s).",
                        summary.get("closed"),
                        summary.get("examined"),
                        summary.get("blocked"),
                    )
            except Exception as exc:
                logger.warning(
                    "Startup flat-orphan auto-reconcile failed (continuing with fail-fast): %s",
                    exc,
                )

        # Phase-4 R-302: automatic Leg-A orphan flatten (broker as SoT).
        try:
            from src.services.leg_orphan_recovery import recover_leg_a_orphans

            orphan_summary = await recover_leg_a_orphans(
                brokerage=self.brokerage, dry_run=False
            )
            if orphan_summary.get("recovered"):
                logger.warning(
                    "Startup Leg-A orphan recovery closed %s signal(s) "
                    "(examined=%s skipped=%s).",
                    orphan_summary.get("recovered"),
                    orphan_summary.get("examined"),
                    orphan_summary.get("skipped"),
                )
        except Exception as exc:
            logger.warning("Startup Leg-A orphan recovery failed: %s", exc)

        try:
            from datetime import datetime, timezone

            await persistence_service.set_system_state(
                "last_broker_reconcile_at",
                datetime.now(timezone.utc).isoformat(),
            )
            await persistence_service.set_system_state("last_broker_reconcile_ok", "true")
        except Exception as exc:
            logger.warning("Could not stamp last_broker_reconcile_at: %s", exc)

        try:
            from src.services.ledger_reconcile_service import (
                log_signal_reconciliation_plans,
                plan_signal_level_reconciliation,
            )

            planner_result = await plan_signal_level_reconciliation(brokerage=self.brokerage)
            log_signal_reconciliation_plans(planner_result)
        except Exception as exc:
            logger.warning("Signal reconciliation planner failed (continuing with fail-fast): %s", exc)

    async def _fail_fast_on_unresolved_execution_state(self) -> bool:
        try:
            await self._run_startup_auto_reconciliation()
        except Exception as exc:
            logger.warning("Startup auto-reconciliation pipeline failed: %s", exc)

        unresolved_count = await persistence_service.count_startup_reconciliation_rows()
        if unresolved_count <= 0:
            return True

        await persistence_service.set_system_state(
            "operational_status",
            "PAUSED_REQUIRES_MANUAL_REVIEW",
        )
        msg = (
            f"Startup blocked: {unresolved_count} ledger rows require manual reconciliation. "
            "CLOSING rows were not reopened because broker close state is ambiguous. "
            "Resolve broker/ledger state before scanning resumes."
        )
        try:
            rows = await persistence_service.get_startup_reconciliation_rows()
        except Exception as exc:
            logger.warning(f"Could not load startup reconciliation rows: {exc}")
            rows = []
        if rows:
            row_details = []
            for row in rows:
                row_details.append(
                    "id={id} order_id={order_id} signal_id={signal_id} "
                    "ticker={ticker} side={side} quantity={quantity} "
                    "status={status} venue={venue} execution_timestamp={execution_timestamp}".format(
                        **row
                    )
                )
            msg = f"{msg} Unresolved rows: {'; '.join(row_details)}"
        logger.critical(msg)
        await notification_service.send_message(msg)
        await dashboard_service.update("PAUSED_REQUIRES_MANUAL_REVIEW", msg)
        return False

    @staticmethod
    def _canonical_position_symbol(symbol: str) -> str:
        from src.services.portfolio_book_guards import canonical_book_symbol

        return canonical_book_symbol(symbol)

    @staticmethod
    def _broker_position_quantity(position: dict) -> float:
        for key in ("quantity", "qty", "quantityAvailableForTrading"):
            value = position.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return 0.0

    @staticmethod
    def _broker_position_float(position: dict, *keys: str) -> float | None:
        for key in keys:
            value = position.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    def _broker_ledger_audit_line(
        self,
        position: dict,
        raw_symbol: str,
        canonical_symbol: str,
        quantity: float,
        matched_signal_ids: list[str],
        *,
        ignore_unmanaged: bool = False,
    ) -> str:
        available_quantity = self._broker_position_float(
            position,
            "quantityAvailableForTrading",
            "qty_available",
            "available_quantity",
        )
        current_price = self._broker_position_float(position, "currentPrice", "current_price")
        market_value = self._broker_position_float(position, "marketValue", "market_value")
        ledger_match = "yes" if matched_signal_ids else "no"
        signal_ids = ",".join(matched_signal_ids) if matched_signal_ids else "none"
        if matched_signal_ids:
            suggested_action = "VERIFY_LEDGER_MATCH"
        elif ignore_unmanaged:
            # Flag allows scan to continue — never imply overnight auto-flatten.
            suggested_action = "IMPORT_OR_CLOSE_MANUALLY_NO_AUTO_FLATTEN"
        else:
            suggested_action = "IMPORT_OR_CLOSE_MANUALLY_BEFORE_RESTART"
        return (
            f"broker_symbol={raw_symbol} canonical_symbol={canonical_symbol} "
            f"quantity={quantity} available_quantity={available_quantity} "
            f"current_price={current_price} market_value={market_value} "
            f"ledger_match={ledger_match} signal_ids={signal_ids} "
            f"suggested_action={suggested_action}"
        )

    async def _alert_ignored_unmanaged_positions(
        self,
        unmanaged_symbols: list[str],
        audit_lines: list[str],
    ) -> None:
        """Surface ignored foreign broker inventory without pausing or flattening."""
        symbols = ", ".join(sorted(unmanaged_symbols))
        msg = (
            f"RISK ALERT: Broker has unmanaged position(s) outside the bot ledger: {symbols}. "
            "Continuing because IGNORE_UNMANAGED_POSITIONS=True — NOT auto-flattening overnight. "
            "Import into acknowledgements via POST /api/broker/unmanaged/acknowledge "
            "or close manually. "
            "Set IGNORE_UNMANAGED_POSITIONS=false before unattended live execution."
        )
        if audit_lines:
            msg = f"{msg} Broker/ledger reconciliation audit: {'; '.join(audit_lines)}"

        # Live real-money (non paper-api) is critical; broker-paper still warrants error.
        live_real_money = bool(
            settings.LIVE_CAPITAL_DANGER and not settings.is_broker_paper_trading
        )
        if live_real_money:
            logger.critical(msg)
        else:
            logger.error(msg)

        unmanaged_audit = [line for line in audit_lines if "ledger_match=no" in line]
        state_payload = {
            "ignored": True,
            "auto_flatten": False,
            "count": len(unmanaged_symbols),
            "symbols": sorted(unmanaged_symbols),
            "audit": unmanaged_audit,
        }
        await persistence_service.set_system_state(
            "unmanaged_broker_positions",
            json.dumps(state_payload, separators=(",", ":"))[:4000],
        )
        # Do not set operational_status to PAUSED — ignore means continue scanning.
        await notification_service.send_message(msg)
        await dashboard_service.update("UNMANAGED_POSITIONS_IGNORED", msg)

    async def _fail_fast_on_broker_ledger_mismatch(self) -> bool:
        if settings.PAPER_TRADING:
            return True

        try:
            broker_positions = await self.brokerage.get_portfolio()
            open_signals = await persistence_service.get_open_signals()
        except Exception as exc:
            msg = (
                "Startup blocked: broker/ledger reconciliation failed. "
                f"Resolve account and ledger state before scanning resumes. Error: {exc}"
            )
            logger.critical(msg)
            await persistence_service.set_system_state(
                "operational_status",
                "PAUSED_REQUIRES_MANUAL_REVIEW",
            )
            await notification_service.send_message(msg)
            await dashboard_service.update("PAUSED_REQUIRES_MANUAL_REVIEW", msg)
            return False

        ignore_unmanaged = bool(getattr(settings, "IGNORE_UNMANAGED_POSITIONS", True))
        ledger_matches = {}
        for signal in open_signals:
            signal_id = str(signal.get("signal_id") or "unknown")
            for leg in signal.get("legs", []):
                canonical = self._canonical_position_symbol(leg.get("ticker"))
                if canonical:
                    ledger_matches.setdefault(canonical, set()).add(signal_id)

        ledger_symbols = set(ledger_matches)
        unmanaged_symbols = []
        audit_lines = []
        for position in broker_positions or []:
            quantity = self._broker_position_quantity(position)
            if abs(quantity) <= 1e-12:
                continue
            raw_symbol = (
                position.get("ticker")
                or position.get("symbol")
                or position.get("instrumentTicker")
                or position.get("instrument")
            )
            canonical_symbol = self._canonical_position_symbol(raw_symbol)
            matched_signal_ids = sorted(ledger_matches.get(canonical_symbol, set()))
            if canonical_symbol:
                audit_lines.append(
                    self._broker_ledger_audit_line(
                        position,
                        str(raw_symbol),
                        canonical_symbol,
                        quantity,
                        matched_signal_ids,
                        ignore_unmanaged=ignore_unmanaged,
                    )
                )
            if canonical_symbol and canonical_symbol not in ledger_symbols:
                unmanaged_symbols.append(str(raw_symbol))

        if not unmanaged_symbols:
            await persistence_service.set_system_state("unmanaged_broker_positions", "")
            return True

        from src.services.unmanaged_positions_service import (
            ACK_STATE_KEY,
            filter_unacked_symbols,
            parse_acknowledgements,
        )

        raw_ack = await persistence_service.get_system_state(ACK_STATE_KEY, default="")
        acks = parse_acknowledgements(raw_ack)
        unacked_symbols = filter_unacked_symbols(unmanaged_symbols, acks)
        ack_only = sorted(set(unmanaged_symbols) - set(unacked_symbols))
        if ack_only:
            logger.info(
                "Unmanaged broker positions already operator-acknowledged (no OPEN import): %s",
                ", ".join(ack_only),
            )
        unmanaged_symbols = unacked_symbols
        if not unmanaged_symbols:
            await persistence_service.set_system_state(
                "unmanaged_broker_positions",
                json.dumps(
                    {
                        "ignored": True,
                        "auto_flatten": False,
                        "acknowledged_only": True,
                        "count": len(ack_only),
                        "symbols": ack_only,
                    },
                    separators=(",", ":"),
                )[:4000],
            )
            return True

        if ignore_unmanaged:
            await self._alert_ignored_unmanaged_positions(unmanaged_symbols, audit_lines)
            return True

        await persistence_service.set_system_state(
            "operational_status",
            "PAUSED_REQUIRES_MANUAL_REVIEW",
        )
        msg = (
            "Startup blocked: broker/ledger mismatch. Broker has unmanaged "
            f"position(s): {', '.join(sorted(unmanaged_symbols))}. "
            "Resolve broker and ledger state before scanning resumes."
        )
        if audit_lines:
            msg = f"{msg} Broker/ledger reconciliation audit: {'; '.join(audit_lines)}"
        logger.critical(msg)
        await notification_service.send_message(msg)
        await dashboard_service.update("PAUSED_REQUIRES_MANUAL_REVIEW", msg)
        return False

    async def run(self):
        # FR-006: Pre-flight line - operator must know mode/universe/window
        # before a single log line about infra appears.
        """
        Start and run the continuous monitoring loop that initializes services, performs startup health checks, and continuously scans active arbitrage pairs.

        This method performs startup routines (preflight display, database and pair initialization, dashboard and notification listeners), runs health checks for PostgreSQL, Redis, and the brokerage API, resets circuit-breaker state, launches background scouting/rotation, and enters the main Rich Live scan loop. While running it:
        - updates dashboard metrics and progress,
        - evaluates open-position exit conditions,
        - fetches latest market prices,
        - performs per-pair processing (signal generation, Kalman updates, and potential trade execution),
        - schedules daily cointegration re-checks and daily resets,
        - respects dashboard-controlled bot states ("STOPPED", "RESTARTING"),
        and sleeps between scan iterations. On cancellation or termination it disposes database and Redis connections for a graceful shutdown.
        """
        self.log_preflight()

        # Initial Setup
        logger.info("Initializing Databases...")
        try:
            await persistence_service.init_db()
        except Exception as e:
            msg = f"CRITICAL INIT ERROR: Database initialization failed! {e}"
            logger.error(msg)
            await notification_service.send_message(msg)
            return

        # Start dashboard + Telegram BEFORE pair init so /api/approvals and
        # health polling work during the long historical-data warm-up.
        dashboard_service.attach_monitor(self)
        await dashboard_service.start()
        await notification_service.start_listening()

        await self.initialize_pairs()
        if not self.active_pairs:
            logger.warning("Startup loaded zero active pairs. Retrying pair initialization once before entering the scan loop.")
            await self.reload_pairs()

        # Sprint C: Startup Health Checks
        logger.info("Running System Health Checks...")

        # 1. PostgreSQL Check
        try:
            async with persistence_service.engine.connect() as conn:
                pass
        except Exception as e:
            msg = f"CRITICAL INIT ERROR: PostgreSQL connection failed! {e}"
            logger.error(msg)
            await notification_service.send_message(msg)
            return

        # 2. Redis Check
        try:
            await redis_service.client.ping()
        except Exception as e:
            msg = f"CRITICAL INIT ERROR: Redis connection failed! {e}"
            logger.error(msg)
            await notification_service.send_message(msg)
            return

        # 3. Alpaca API check (if not exclusively paper/mocked)
        if not settings.PAPER_TRADING:
            await asyncio.sleep(1)  # Rate limit safety delay
            try:
                # Await async brokerage call
                test_ping = await self.brokerage.get_portfolio()
                if isinstance(test_ping, dict) and test_ping.get("status") == "error":
                    raise Exception(f"Alpaca error: {test_ping.get('message')}")
            except Exception as e:
                msg = f"CRITICAL INIT ERROR: Alpaca API connection failed! {e}"
                logger.error(msg)
                await notification_service.send_message(msg)
                return

        logger.info("All Health Checks Passed (Postgres, Redis, Alpaca). Bot is active.")

        # Sprint J: Signal the user via Telegram that we are entering MISSION MODE
        await notification_service.send_message("System Health: All Checks Passed.\n\nMode: Continuous Scan initiated for " + f"{len(self.active_pairs)}" + " pairs.")

        if not await self._fail_fast_on_unresolved_execution_state():
            # Keep dashboard/approvals/Telegram alive while capital state is reviewed.
            logger.critical(
                "Startup fail-fast blocked the scan loop; holding process alive for dashboard/approvals."
            )
            while True:
                await asyncio.sleep(60)
                try:
                    unresolved = await persistence_service.count_startup_reconciliation_rows()
                except Exception as exc:
                    logger.warning("Paused-mode unresolved recount failed: %s", exc)
                    continue
                if unresolved <= 0:
                    logger.info("Startup reconciliation rows cleared; leaving pause hold.")
                    break
            if not await self._fail_fast_on_broker_ledger_mismatch():
                logger.critical(
                    "Broker/ledger mismatch still blocking scan loop; holding for dashboard/approvals."
                )
                while True:
                    await asyncio.sleep(60)
        elif not await self._fail_fast_on_broker_ledger_mismatch():
            logger.critical(
                "Broker/ledger mismatch blocked the scan loop; holding process alive for dashboard/approvals."
            )
            while True:
                await asyncio.sleep(60)

        # Reset circuit breaker on clean startup so a stale DEGRADED_MODE
        # from a previous crashed session doesn't silently block all signals.
        await persistence_service.set_system_state("operational_status", "NORMAL")
        await persistence_service.set_system_state("consecutive_api_timeouts", "0")
        logger.info("Circuit breaker reset to NORMAL on startup.")

        # Start periodic Scouting & Rotation background task
        if settings.PAIR_DISCOVERY_ENABLED:
            background_task_watchdog.create_task(
                self._auto_scout_and_rotate_loop(),
                name="monitor:auto_scout_and_rotate_loop",
            )
        else:
            logger.info("Pair discovery auto-scout loop not started (PAIR_DISCOVERY_ENABLED=false).")

        # Phase-4: continuous broker reconciliation (broker = source of truth).
        try:
            from src.services.continuous_broker_reconcile import continuous_broker_reconciler

            background_task_watchdog.create_task(
                continuous_broker_reconciler.loop(self),
                name="monitor:continuous_broker_reconcile",
            )
            logger.info(
                "Continuous broker reconciler started (interval=%ss).",
                continuous_broker_reconciler.interval_seconds,
            )
        except Exception as exc:
            logger.warning("Could not start continuous broker reconciler: %s", exc)

        try:
            # Main Scan Loop with Rich Live UI
            progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(bar_width=None),
                TaskProgressColumn(),
                expand=True
            )

            scan_task = progress.add_task("Monitoring...", total=len(self.active_pairs))

            with Live(progress, console=console, refresh_per_second=4, vertical_overflow="visible"):
                while True:
                    try:

                        # Bot Control Check: respect dashboard state (STOPPED, RESTARTING)
                        desired = dashboard_service.dashboard_state.desired_bot_state
                        if desired == "STOPPED":
                            await dashboard_service.update("PAUSED", "Bot is stopped via dashboard.")
                            await asyncio.sleep(5)
                            continue

                        if desired == "RESTARTING":
                            await dashboard_service.update("RESTARTING", "Reloading pairs and resetting state...")
                            await self.reload_pairs()
                            dashboard_service.dashboard_state.desired_bot_state = "RUNNING"
                            await dashboard_service.update("Monitoring", "Bot restarted and active.")
                            # Continue to normal scan immediately after reload

                        from src.services.performance_service import performance_service
                        p_metrics = await performance_service.get_portfolio_metrics()
                        await dashboard_service.update_metrics(p_metrics)

                        # Lifetime closed PnL → total_revenue (via update's pnl arg).
                        # Do not confuse with daily_profit; _poll_metrics owns that field.
                        total_pnl = await persistence_service.get_total_pnl()
                        await dashboard_service.update(
                            stage="Monitoring",
                            details=f"Scanning {len(self.active_pairs)} pairs...",
                            pnl=total_pnl,
                            active_signals=self.active_signals
                        )
                    except Exception as e:
                        logger.error(f"Error pushing metrics to dashboard: {e}")
                        await dashboard_service.update("Monitoring", f"Scanning {len(self.active_pairs)} pairs...")

                    # Exit + scan share one price fetch; concurrency is semaphore-capped
                    # so Mini PC CPU/RAM cannot be saturated by gather storms. Every open
                    # signal and every scannable pair still runs each cycle.
                    open_signals = []
                    try:
                        progress.update(scan_task, description="Loading open positions...")
                        open_signals = await persistence_service.get_open_signals()
                    except Exception as e:
                        logger.error(f"Error loading open signals for exits: {e}")
                        open_signals = []

                    if not self.active_pairs:
                        logger.warning("No active pairs loaded; attempting pair reload before scanning.")
                        await self.reload_pairs()
                        progress.update(scan_task, total=len(self.active_pairs), completed=0)
                        if not self.active_pairs and not open_signals:
                            await dashboard_service.update(
                                "NO_ACTIVE_PAIRS",
                                "No active pairs are loaded. Check pair initialization logs and configured crypto pairs.",
                            )
                            logger.warning("No active pairs available after reload; sleeping before next retry.")
                            await asyncio.sleep(settings.SCAN_INTERVAL_SECONDS)
                            continue

                    scan_pairs, all_tickers = build_scan_pairs(
                        self.active_pairs,
                        is_market_open=self.is_market_open,
                    )
                    exit_tickers = open_signal_tickers(open_signals)
                    price_tickers = list(dict.fromkeys([*all_tickers, *exit_tickers]))

                    latest_prices: dict = {}
                    if price_tickers:
                        progress.update(
                            scan_task,
                            description=f"Fetching prices for {len(price_tickers)} tickers...",
                            completed=0,
                            total=max(len(scan_pairs), 1),
                        )
                        latest_prices = await data_service.get_latest_price_async(price_tickers)

                    if open_signals:
                        progress.update(scan_task, description="Checking open positions...")
                        try:
                            await gather_bounded(
                                (
                                    self._evaluate_exit_conditions(
                                        signal,
                                        latest_prices=latest_prices,
                                    )
                                    for signal in open_signals
                                ),
                                limit=settings.SCAN_EXIT_CONCURRENCY,
                                return_exceptions=True,
                            )
                        except Exception as e:
                            logger.error(f"Error evaluating open signals for exits: {e}")

                    if not scan_pairs:
                        msg = (
                            f"No active pairs are currently scannable "
                            f"({len(self.active_pairs)} loaded). Waiting for an eligible market/session."
                        )
                        logger.warning(msg)
                        await dashboard_service.update("NO_SCANNABLE_PAIRS", msg)
                        progress.update(
                            scan_task,
                            completed=0,
                            total=len(self.active_pairs),
                            description=f"Idle (no scannable pairs; sleeping {settings.SCAN_INTERVAL_SECONDS}s)...",
                        )
                        await asyncio.sleep(settings.SCAN_INTERVAL_SECONDS)
                        continue

                    # Daily Global Reset
                    today = datetime.now().date()
                    if self.current_day != today:
                        logger.info(f"--- [bold yellow]NEW TRADING DAY[/]: {today} ---")
                        self.current_day = today
                        self.bumped_pairs_today = {} # Reset Kalman bumps for the new day


                    # Daily cointegration re-validation (tasks queue behind _coint_recheck_sem)
                    today = datetime.now().date()
                    for pair in self.active_pairs:
                        if self.last_cointegration_check.get(pair['id']) != today:
                            pair_id = pair.get("id") or f"{pair.get('ticker_a')}_{pair.get('ticker_b')}"
                            background_task_watchdog.create_task(
                                self._recheck_cointegration(pair),
                                name=f"monitor:recheck_cointegration:{pair_id}",
                            )
                            self.last_cointegration_check[pair['id']] = today

                    # Fetch sizing base once per iteration to avoid API spam in process_pair
                    current_sizing_base = await self._get_sizing_base()
                    scan_id = decision_recorder.begin_scan()
                    pair_concurrency = max(1, int(settings.SCAN_PAIR_CONCURRENCY))
                    decision_recorder.record(
                        stage="scan",
                        outcome="continue",
                        reason="scan_started",
                        inputs={
                            "pairs": len(scan_pairs),
                            "scan_id": scan_id,
                            "pair_concurrency": pair_concurrency,
                            "exit_concurrency": max(1, int(settings.SCAN_EXIT_CONCURRENCY)),
                        },
                        scan_id=scan_id,
                    )

                    progress.update(
                        scan_task,
                        description=(
                            f"Scanning {len(scan_pairs)} pairs "
                            f"(concurrency={pair_concurrency})..."
                        ),
                        completed=0,
                        total=len(scan_pairs),
                    )
                    raw_results = await gather_bounded(
                        (
                            self.process_pair(
                                pair,
                                latest_prices,
                                sizing_base=current_sizing_base,
                            )
                            for pair in scan_pairs
                        ),
                        limit=pair_concurrency,
                        return_exceptions=True,
                    )
                    for item in raw_results:
                        if isinstance(item, Exception):
                            logger.error("Scan pair task failed: %s", item)
                    results = normalize_scan_results(raw_results)

                    progress.update(scan_task, completed=len(scan_pairs), description="Scan iteration complete")

                    # L-14: Enriched heartbeat
                    active_signal_count, vetoed_count = summarize_scan_iteration(
                        results,
                        settings.MONITOR_MIN_AI_CONFIDENCE,
                    )
                    funnel = summarize_scan_funnel(
                        results,
                        active_pairs=self.active_pairs,
                        scan_pairs=scan_pairs,
                        min_ai_confidence=settings.MONITOR_MIN_AI_CONFIDENCE,
                    )

                    summary_msg = (
                        f"[bold green]Iteration Complete[/] | "
                        f"Scanned: {len(scan_pairs)}/{len(self.active_pairs)} | "
                        f"Signals: {active_signal_count} | "
                        f"Vetoed: {vetoed_count} | "
                        f"Open: {len(open_signals)}"
                    )
                    logger.info(summary_msg)
                    logger.info(
                        "FUNNEL active_eq=%s active_crypto=%s scanned=%s/%s "
                        "near_miss=%s entry_band=%s approved=%s orders=%s skips=%s",
                        funnel.get("active_equity"),
                        funnel.get("active_crypto"),
                        funnel.get("scanned"),
                        funnel.get("active_total"),
                        funnel.get("near_miss"),
                        funnel.get("entry_band_hit"),
                        funnel.get("approved"),
                        funnel.get("order_submitted"),
                        funnel.get("skip_reasons"),
                    )
                    try:
                        self._write_trade_decision_report(
                            scan_pairs=scan_pairs,
                            results=results,
                            latest_prices=latest_prices,
                            latest_price_sources=getattr(data_service, "last_price_sources", {}),
                            latest_price_timestamps=getattr(data_service, "last_price_timestamps", {}),
                            open_signals=open_signals,
                            active_signal_count=active_signal_count,
                            vetoed_count=vetoed_count,
                            sizing_base=current_sizing_base,
                        )
                    except Exception as e:
                        logger.warning("TRADE DECISION REPORT: write failed: %s", e)

                    await self._reload_quarantined_pairs_if_requested()
                    self._maybe_relieve_memory_pressure(reason="scan_iteration")

                    progress.update(scan_task, description=f"Idle (sleeping {settings.SCAN_INTERVAL_SECONDS}s)...")
                    await asyncio.sleep(settings.SCAN_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("Shutdown signal received. Closing connections...")
        finally:
            # Signal uvicorn to shut down cleanly before the event loop cancels
            # the dashboard:uvicorn_server task.  Without this, uvicorn's lifespan
            # handler is hard-cancelled while blocked on receive_queue.get(), which
            # produces a spurious "CancelledError" ERROR log from starlette/uvicorn.
            if dashboard_service.server is not None:
                try:
                    await dashboard_service.server.shutdown()
                except Exception as exc:
                    logger.warning("Dashboard server shutdown warning: %s", exc)
            # Graceful shutdown of database pools
            await persistence_service.engine.dispose()
            await redis_service.client.aclose()
            logger.info("Service shutdown complete.")

    async def _evaluate_exit_conditions(
        self,
        signal: dict,
        latest_prices: dict | None = None,
    ):
        """Monitors open positions for Take Profit or Stop Loss."""
        sig_id = signal["signal_id"]
        legs = signal.get("legs", [])
        if len(legs) != 2: return

        leg_a, leg_b = legs[0], legs[1]
        t_a, t_b = leg_a["ticker"], leg_b["ticker"]

        # Prefer the scan-loop shared snapshot to avoid N concurrent price storms.
        prices = latest_prices if latest_prices is not None else {}
        if t_a not in prices or t_b not in prices:
            prices = await data_service.get_latest_price_async([t_a, t_b])
        if t_a not in prices or t_b not in prices: return

        p_a, p_b = prices[t_a], prices[t_b]

        # PATCH 4: Stale/zero price guard — a price of 0 fed into the kill-switch check
        # produces current_value=0 which always triggers a kill-switch close.
        # If either price is missing or non-positive, skip this cycle rather than
        # make a trade decision on bad data.
        if not (p_a > 0 and p_b > 0):
            logger.warning(
                "Skipping exit evaluation for %s/%s — invalid prices (p_a=%.4f p_b=%.4f). "
                "Will retry next scan cycle.",
                t_a, t_b, p_a, p_b,
            )
            return

        prices_by_ticker = {t_a: float(p_a), t_b: float(p_b)}

        cost_basis = signal["total_cost_basis"]
        _, directional_pnl = calculate_realized_pnl(signal, prices_by_ticker=prices_by_ticker)
        current_value = cost_basis + directional_pnl

        # 1. Financial Kill Switch Check
        if risk_service.check_financial_kill_switch(current_value, cost_basis):
            logger.warning(f"FINANCIAL KILL SWITCH TRIGGERED for {t_a}/{t_b}. Closing position.")
            await self._close_position(signal, p_a, p_b, reason=ExitReason.KILL_SWITCH, prices_by_ticker=prices_by_ticker)
            return

        # 2. Statistical Stop Loss / Take profit
        known_pair_ids = set(arbitrage_service.filters.keys()) | {
            p["id"] for p in self.active_pairs
        }
        pair_id = resolve_kalman_pair_id(t_a, t_b, known_ids=known_pair_ids)
        kf = await arbitrage_service.get_or_create_filter(
            pair_id,
            delta=settings.KALMAN_DELTA,
            r=settings.KALMAN_R,
        )
        if not kf:
            return

        # Prior-state z-score for the latest prices (do not absorb the tick here;
        # process_pair performs the single Kalman update during the scan pass).
        _spread, z_score = kf.calculate_spread_and_zscore(p_a, p_b)

        # Statistical Take Profit (Mean Reversion complete)
        if abs(z_score) <= settings.TAKE_PROFIT_ZSCORE:
            gross_notional = sum(
                abs(float(leg["quantity"]) * prices_by_ticker[leg["ticker"]])
                for leg in legs
            )
            friction_pct = estimate_round_trip_cost_pct(t_a, t_b)
            estimated_friction = gross_notional * friction_pct
            should_close, tp_reason = should_take_profit_exit(
                abs_z_score=abs(float(z_score)),
                take_profit_zscore=settings.TAKE_PROFIT_ZSCORE,
                directional_pnl=float(directional_pnl),
                estimated_friction=float(estimated_friction),
                force_exit_zscore=settings.TAKE_PROFIT_FORCE_EXIT_ZSCORE,
            )
            if not should_close:
                logger.info(
                    "TAKE PROFIT z-threshold met for %s/%s (Z=%.2f) but gross PnL "
                    "($%.2f) would not clear est. round-trip friction ($%.2f); holding "
                    "(%s).",
                    t_a,
                    t_b,
                    z_score,
                    directional_pnl,
                    estimated_friction,
                    tp_reason,
                )
            else:
                logger.info(
                    "TAKE PROFIT reached for %s/%s (Z-Score: %.2f, reason=%s).",
                    t_a,
                    t_b,
                    z_score,
                    tp_reason,
                )
                await self._close_position(signal, p_a, p_b, reason=ExitReason.TAKE_PROFIT, prices_by_ticker=prices_by_ticker)

        # Statistical Stop Loss (Cointegration break)
        elif abs(z_score) >= settings.STOP_LOSS_ZSCORE:
            logger.warning(f"STATISTICAL STOP LOSS triggered for {t_a}/{t_b} (Z-Score: {z_score:.2f}). Cointegration likely lost.")
            await self._close_position(signal, p_a, p_b, reason=ExitReason.STOP_LOSS, prices_by_ticker=prices_by_ticker)

    async def _close_position(
        self,
        signal: dict,
        price_a: float,
        price_b: float,
        reason: ExitReason,
        prices_by_ticker: dict[str, float] | None = None,
    ):
        sig_id_str = str(signal["signal_id"])
        sig_uuid = uuid.UUID(sig_id_str) if isinstance(signal["signal_id"], str) else signal["signal_id"]
        
        async with self._signals_lock:
            if sig_id_str in getattr(self, '_closing_signals', set()):
                logger.info(f"Duplicate close blocked in memory for signal {sig_id_str}.")
                return
            if not hasattr(self, '_closing_signals'):
                self._closing_signals = set()
            self._closing_signals.add(sig_id_str)

        try:
            # Idempotency guard in DB (cross-process): only one worker may transition OPEN->CLOSING.
            transitioned = await persistence_service.mark_signal_closing_if_open(sig_uuid)
            if not transitioned:
                db_status = await persistence_service.get_signal_status(sig_uuid)
                logger.info(f"Duplicate close blocked for signal {sig_id_str}. DB status is {db_status}.")
                return

            logger.info(f"Closing position {sig_id_str} Reason: {reason.value}")
            # PATCH 6: Any unhandled exception in the close path must alert the operator
            # immediately. Silently swallowing close failures leaves positions open and losing.
            close_orders = build_close_orders(
                signal,
                prices_by_ticker=prices_by_ticker or {
                    signal["legs"][0]["ticker"]: float(price_a),
                    signal["legs"][1]["ticker"]: float(price_b),
                },
                dev_mode=settings.DEV_MODE,
                dev_execution_tickers=settings.DEV_EXECUTION_TICKERS,
            )

            # Close via broker only when the *open* was broker-lane (metadata), not merely
            # when PAPER_TRADING is currently false — avoids orphaning Alpaca paper fills
            # after a mode flip or submitting broker closes for SHADOW ledger rows.
            use_broker_close = close_uses_broker(
                signal,
                paper_trading=bool(settings.PAPER_TRADING),
            )
            if use_broker_close:
                sell_orders = [order for order in close_orders if order["side"] == "SELL"]
                if sell_orders and not await self._preflight_live_sell_inventory(sell_orders):
                    # Restore to OPEN so subsequent close attempts are not blocked
                    await persistence_service.update_signal_status(sig_uuid, OrderStatus.OPEN)
                    return

                confirmed_close_fills = []
                for order in close_orders:
                    notional = float(order["quantity"] * order["price"])
                    client_order_id = f"{sig_id_str}-CLOSE-{order['display_ticker']}"
                    res = await self.brokerage.place_value_order(
                        order["ticker"],
                        round(notional, 2),
                        order["side"],
                        price=order["price"],
                        client_order_id=client_order_id,
                        intent="close",
                    )
                    # Dead prior close order (rejected/canceled) keeps the same
                    # client_order_id reserved — retry once with a unique suffix.
                    if res.get("terminal_duplicate"):
                        retry_client_order_id = (
                            f"{client_order_id}-R{uuid.uuid4().hex[:8]}"
                        )
                        logger.warning(
                            "Close client_order_id %s bound to terminal broker order "
                            "(%s); retrying once as %s",
                            client_order_id,
                            res.get("prior_order_status"),
                            retry_client_order_id,
                        )
                        client_order_id = retry_client_order_id
                        res = await self.brokerage.place_value_order(
                            order["ticker"],
                            round(notional, 2),
                            order["side"],
                            price=order["price"],
                            client_order_id=client_order_id,
                            intent="close",
                        )
                    order_id = res.get("order_id") or res.get("orderId") or res.get("client_order_id") or client_order_id

                    if res.get("requires_reconciliation") or res.get("status") == "unknown":
                        msg = (
                            f"Close order state unknown for {sig_id_str}: {order['display_ticker']} "
                            f"{order['side']}. Reconcile broker by order_id/client_order_id={order_id}. "
                            f"Broker response: {res}"
                        )
                        logger.critical(msg)
                        await notification_service.send_message(msg)
                        await persistence_service.update_signal_status(
                            sig_uuid,
                            OrderStatus.NEEDS_MANUAL_RECONCILIATION,
                        )
                        return

                    if res.get("status") == "error":
                        msg = (
                            f"Close aborted for {sig_id_str}: {order['display_ticker']} "
                            f"{order['side']} failed. Broker response: {res}"
                        )
                        logger.error(msg)
                        await notification_service.send_message(msg)
                        close_status = (
                            OrderStatus.NEEDS_MANUAL_RECONCILIATION
                            if confirmed_close_fills
                            else OrderStatus.CLOSE_FAILED
                        )
                        await persistence_service.update_signal_status(sig_uuid, close_status)
                        return

                    close_fill = await self._await_order_fill(order_id, timeout=30)
                    if not close_fill:
                        msg = (
                            f"Close order not confirmed filled for {sig_id_str}: {order['display_ticker']} "
                            f"{order['side']} [order_id={order_id}]. Ledger NOT closed. "
                            f"Manual broker reconciliation required."
                        )
                        logger.critical(msg)
                        await notification_service.send_message(msg)
                        await persistence_service.update_signal_status(
                            sig_uuid,
                            OrderStatus.NEEDS_MANUAL_RECONCILIATION,
                        )
                        return

                    close_status_raw = str(close_fill.get("status", "")).lower()
                    close_filled_qty = float(close_fill.get("filled_qty") or 0.0)
                    expected_close_qty = float(order["quantity"])
                    expected_close_notional = float(order["quantity"] * order["price"])
                    if not is_broker_fill_complete(
                        status=close_status_raw,
                        filled_qty=close_filled_qty,
                        expected_qty=expected_close_qty,
                        fill_price=float(close_fill.get("filled_avg_price") or order["price"] or 0.0),
                        expected_notional=expected_close_notional,
                    ):
                        msg = (
                            f"Close order ended without a full fill for {sig_id_str}: {order['display_ticker']} "
                            f"{order['side']} status={close_status_raw or 'unknown'} "
                            f"filled_qty={close_filled_qty} expected_qty={expected_close_qty} "
                            f"[order_id={order_id}]. Ledger NOT closed."
                        )
                        logger.critical(msg)
                        await notification_service.send_message(msg)
                        await persistence_service.update_signal_status(
                            sig_uuid,
                            OrderStatus.NEEDS_MANUAL_RECONCILIATION,
                        )
                        return

                    confirmed_close_fills.append(close_fill)

                for order in close_orders:
                    try:
                        maybe_remaining = self.brokerage.get_available_quantity(order["ticker"])
                        remaining_qty = await maybe_remaining if inspect.isawaitable(maybe_remaining) else maybe_remaining
                        remaining_qty = float(remaining_qty or 0.0)
                    except Exception as exc:
                        msg = (
                            f"Close position verification failed for {sig_id_str}: could not verify "
                            f"remaining broker quantity for {order['display_ticker']} after close fills ({exc}). "
                            f"Ledger NOT closed. Manual broker reconciliation required."
                        )
                        logger.critical(msg)
                        await notification_service.send_message(msg)
                        await persistence_service.update_signal_status(
                            sig_uuid,
                            OrderStatus.NEEDS_MANUAL_RECONCILIATION,
                        )
                        return

                    if abs(remaining_qty) > 1e-9:
                        if getattr(settings, "IGNORE_UNMANAGED_POSITIONS", True):
                            msg = (
                                f"Close fill confirmed for {sig_id_str}: {order['display_ticker']} "
                                f"{order['side']} but broker still reports {remaining_qty:.6f} remaining; "
                                "continuing ledger close because IGNORE_UNMANAGED_POSITIONS=True. "
                                "Residual NOT auto-flattened — manual broker reconciliation required "
                                "for unmanaged inventory."
                            )
                            logger.error(msg)
                            await notification_service.send_message(msg)
                            continue
                        msg = (
                            f"Close position verification failed for {sig_id_str}: broker still reports "
                            f"{remaining_qty:.6f} remaining {order['display_ticker']} after confirmed close fills. "
                            f"Ledger NOT closed. Manual broker reconciliation required."
                        )
                        logger.critical(msg)
                        await notification_service.send_message(msg)
                        await persistence_service.update_signal_status(
                            sig_uuid,
                            OrderStatus.NEEDS_MANUAL_RECONCILIATION,
                        )
                        return

            # M-04: Compute realized PnL from entry vs exit price per leg.
            # Shadow: adverse-slip exit mids before cost-adjusted PnL so ledger
            # matches open-fill realism (entry fill already embeds open slip).
            leg_a, leg_b = signal["legs"][0], signal["legs"][1]
            pnl_prices = prices_by_ticker or {
                leg_a["ticker"]: float(price_a),
                leg_b["ticker"]: float(price_b),
            }

            # N2 fix: shadow-lane closes log via shadow_service, then a single
            # persistence.close_trade write (shared with broker closes).
            if not use_broker_close:
                direction = "Short-Long" if leg_a["side"] == "SELL" else "Long-Short"
                _shadow_pnl, slipped_a, slipped_b = await shadow_service.close_simulated_trade(
                    pair_id=f"{leg_a['ticker']}_{leg_b['ticker']}",
                    signal_id=sig_uuid,
                    direction=direction,
                    size_a=leg_a["quantity"],
                    size_b=leg_b["quantity"],
                    entry_price_a=leg_a["price"],
                    entry_price_b=leg_b["price"],
                    exit_price_a=price_a,
                    exit_price_b=price_b,
                )
                pnl_prices = {
                    leg_a["ticker"]: float(slipped_a),
                    leg_b["ticker"]: float(slipped_b),
                }

            exit_prices, pnl = calculate_realized_pnl(
                signal,
                prices_by_ticker=pnl_prices,
            )

            await persistence_service.close_trade(sig_uuid, exit_prices, pnl, exit_reason=reason)

        except Exception as exc:
            # Mark as CLOSE_FAILED to avoid looping
            await persistence_service.update_signal_status(sig_uuid, OrderStatus.CLOSE_FAILED)
            # PATCH 6: Close machinery failure — alert operator, never swallow.
            alert = (
                f"CRITICAL — _close_position FAILED\n"
                f"signal_id={sig_id_str} reason={reason.value}\n"
                f"Position may still be OPEN at broker. Manual intervention required.\n"
                f"Error: {exc}"
            )
            logger.critical(alert, exc_info=True)
            await notification_service.send_message(alert)
            raise  # re-raise so the caller's gather sees the failure
        finally:
            async with self._signals_lock:
                if hasattr(self, '_closing_signals'):
                    self._closing_signals.discard(sig_id_str)


if __name__ == "__main__":
    monitor = ArbitrageMonitor()
    asyncio.run(monitor.run())
