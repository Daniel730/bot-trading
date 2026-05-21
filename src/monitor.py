import asyncio
import json
import logging
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
from src.services.persistence_service import ExitReason
from src.services.dashboard_service import dashboard_service, dashboard_state
from src.services.background_task_watchdog import background_task_watchdog
from src.services.trade_math import build_pair_legs, cap_pair_notional, estimate_pair_profit
import uuid
import pytz
import inspect
from src.monitor_helpers import is_crypto_pair, resolve_pair_sector, compute_entry_zscore
from src.monitor_scan_helpers import (
    build_candidate_pairs,
    build_scan_pairs,
    summarize_scan_iteration,
    build_close_orders,
    calculate_realized_pnl,
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
        console=console,
        rich_tracebacks=True,
        markup=True,
        show_time=True,
        show_path=True
    )
    rich_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(rich_handler)
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
CRYPTO_SNAPSHOT_STALE_REPEAT_LIMIT = 5

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
        self._crypto_snapshot_pair_prices: dict[str, tuple[tuple[float, float], int]] = {}
        # In-memory lock set for closing positions to prevent duplicate broker orders
        self._closing_signals: set = set()
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

    async def _has_active_pair_or_pending_order(self, ticker_a: str, ticker_b: str) -> bool:
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
            await notification_service.send_message(msg)
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
            "Runtime mode resolved: execution_mode=%s broker_paper_trading=%s "
            "alpaca_endpoint_class=%s paper_trading=%s live_capital_danger=%s",
            runtime["execution_mode"],
            runtime["broker_paper_trading"],
            runtime["alpaca_endpoint_class"],
            runtime["paper_trading"],
            runtime["live_capital_danger"],
        )

        table = Table(title="Bot Pre-flight Configuration", show_header=False, box=None)
        table.add_row("Mode", f"[bold cyan]{mode}[/]")
        table.add_row("Execution Mode", f"[bold cyan]{runtime['execution_mode']}[/]")
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
        logger.info(f"VALIDATING L2 ENTROPY BASELINES FOR {len(pairs)} PAIRS (LIVE_CAPITAL_DANGER=True)...")

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
        )

        # US1: Verify entropy baselines ONLY for actual live broker endpoints.
        if settings.LIVE_CAPITAL_DANGER:
            runtime = dashboard_state.runtime_info()
            if runtime.get("broker_paper_trading"):
                logger.info(
                    "Skipping L2 entropy baseline startup check in %s mode; "
                    "baseline enforcement remains required for actual live endpoints.",
                    runtime.get("execution_mode", "UNKNOWN"),
                )
            else:
                await self.verify_entropy_baselines(pairs_to_init)
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

                # Normalise: if yfinance returned a MultiIndex DataFrame, flatten to
                # a simple ticker→price DataFrame so column matching is consistent.
                if isinstance(hist_data.columns, pd.MultiIndex):
                    # Level 0 is the price field (Close/Open/…), level 1 is ticker.
                    # Drop down to just the Close slice if available.
                    if "Close" in hist_data.columns.get_level_values(0):
                        hist_data = hist_data["Close"]
                    else:
                        # Keep the last level (tickers) as column names.
                        hist_data.columns = hist_data.columns.get_level_values(-1)

                # Case-insensitive substring match so 'BTC-USD' matches 'BTC-USD' column.
                col_a = next(
                    (c for c in hist_data.columns
                     if ticker_a.upper() in str(c).upper()),
                    None,
                )
                col_b = next(
                    (c for c in hist_data.columns
                     if ticker_b.upper() in str(c).upper()),
                    None,
                )

                if not col_a or not col_b:
                    logger.warning(
                        f"SKIP {ticker_a}/{ticker_b}: Columns not found in data. "
                        f"Found: {hist_data.columns.tolist()}"
                    )
                    continue

                is_crypto = is_crypto_pair(ticker_a, ticker_b)
                p_thresh = 0.25 if is_crypto else settings.COINTEGRATION_PVALUE_THRESHOLD
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
                            "→ pair admitted but trading suspended until stability returns.",
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

                pair_id = f"{ticker_a}_{ticker_b}"

                if pair_id in self.kalman_quarantined_pairs:
                    arbitrage_service.filters.pop(pair_id, None)
                    arbitrage_service.filter_fingerprints.pop(pair_id, None)
                    try:
                        await redis_service.client.delete(f"kalman:{pair_id}")
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
        Implements the Elite Squad rotation logic.
        Swaps the worst performing active pairs with the best candidates.
        """
        logger.info("ELITE SQUAD: Checking for potential pair rotation...")

        # 1. Get current active pairs
        active_pairs = await persistence_service.get_active_trading_pairs()
        if not active_pairs: return

        # 2. Get top candidates from scouting
        top_candidates = await persistence_service.get_top_candidates(limit=10)
        if not top_candidates:
            logger.info("ELITE SQUAD: No candidates available for rotation.")
            return

        # 3. Find worst performing or broken active pair
        # Simple heuristic: prioritize pairs that are no longer cointegrated.
        worst_active = sorted(active_pairs, key=lambda p: p.get('is_cointegrated', True))[0]

        # Get the best candidate that isn't already active
        active_ids = {p['id'] for p in active_pairs}
        eligible_candidates = [c for c in top_candidates if c['pair_id'] not in active_ids]

        if not eligible_candidates:
            logger.info("ELITE SQUAD: All top candidates are already active.")
            return

        best_candidate = eligible_candidates[0]

        # 4. Rotation Logic: Rotate if active is broken OR candidate Sortino is significantly high
        should_rotate = (
            not worst_active.get("is_cointegrated")
            or best_candidate["sortino"] > settings.ELITE_ROTATION_SORTINO_THRESHOLD
        )

        if should_rotate:
            logger.info(f"ELITE SQUAD: Rotating {worst_active['id']} out for {best_candidate['pair_id']}.")

            # Update DB
            await persistence_service.update_pair_status(worst_active['id'], "Benched")

            # Promote candidate to Active
            ticker_a, ticker_b = best_candidate['pair_id'].split('_')
            await persistence_service.save_trading_pairs([{
                "ticker_a": ticker_a,
                "ticker_b": ticker_b,
                "status": "Active",
                "is_cointegrated": True
            }])

            # Reload in-memory state
            await self.reload_pairs()
        else:
            logger.info("ELITE SQUAD: No rotation needed at this time.")

    async def _auto_scout_and_rotate_loop(self):
        """
        Background task that periodically runs the discovery engine (Scouting)
        and promotes the best pairs (Rotation).
        """
        # Wait 20 minutes after startup before the first scout cycle.
        # The 60s original value caused run_discovery() to saturate yfinance
        # immediately after boot, rate-limiting the first reload and dropping
        # all active pairs to 0.  20 min gives the scan loop time to warm up
        # Kalman filters before any heavy portfolio_manager downloads begin.
        initial_delay = max(1200, settings.SCOUT_INTERVAL_HOURS * 1800)
        logger.info(
            "AUTO-SCOUT: first cycle in %.0f minutes.",
            initial_delay / 60,
        )
        await asyncio.sleep(initial_delay)

        while True:
            try:
                logger.info("AUTO-UPDATE: Starting periodic Scouting & Rotation cycle...")

                # 1. Scouting: Find new candidates
                from src.agents.portfolio_manager_agent import portfolio_manager
                await portfolio_manager.run_discovery()

                # 2. Rotation: Promote best candidates
                await self._rotate_elite_pairs()

                logger.info(f"AUTO-UPDATE: Cycle complete. Next run in {settings.SCOUT_INTERVAL_HOURS} hours.")
                await asyncio.sleep(settings.SCOUT_INTERVAL_HOURS * 3600)
            except Exception as e:
                logger.error(f"Error in auto-scout loop: {e}")
                await asyncio.sleep(3600) # Retry in 1 hour



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
                from src.services.arbitrage_service import arbitrage_service
                for pid in removed:
                    arbitrage_service.filters.pop(pid, None)
                logger.info(f"reload_pairs: dropped {len(removed)} pairs ({sorted(removed)})")
            logger.info(
                f"reload_pairs complete: {len(new_ids)} active pairs "
                f"(+{len(new_ids - old_ids)} new, -{len(removed)} removed)"
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
            "KALMAN QUARANTINE: rebuilding quarantined pair state after scan: %s",
            quarantined,
        )
        await self.reload_pairs()
        return True

    async def _get_sizing_base(self) -> float:
        """Helper to fetch the current account equity/cash for sizing calculations."""
        if settings.PAPER_TRADING:
            venue_budget_cap = settings.ALPACA_BUDGET_USD
            return venue_budget_cap if venue_budget_cap > 0 else settings.PAPER_TRADING_STARTING_CASH

        try:
            maybe_equity = self.brokerage.get_account_equity()
            equity = await maybe_equity if inspect.isawaitable(maybe_equity) else maybe_equity
            return float(equity or 0.0)
        except Exception as e:
            logger.warning(f"Failed to fetch sizing base from brokerage: {e}. Falling back to default.")
            return settings.PAPER_TRADING_STARTING_CASH

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

            def skip(reason: str) -> dict:
                diagnostic["reason"] = reason
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
                    return skip("price_sanity_invalid")

                price_sources = getattr(data_service, "last_price_sources", {})
                source_a = price_sources.get(t_a)
                source_b = price_sources.get(t_b)
                alpaca_crypto_sources = {"alpaca_crypto_snapshot", "alpaca_crypto_quote_mid"}
                if source_a in alpaca_crypto_sources and source_b in alpaca_crypto_sources:
                    price_timestamps = getattr(data_service, "last_price_timestamps", {})

                    def freshness_marker(ticker: str, price: float, source: str):
                        if source == "alpaca_crypto_quote_mid":
                            timestamp = price_timestamps.get(ticker)
                            return ("quote_mid", timestamp) if timestamp else None
                        return ("snapshot", float(price))

                    pair_marker = (
                        freshness_marker(t_a, price_a, source_a),
                        freshness_marker(t_b, price_b, source_b),
                    )
                    if pair_marker[0] is None or pair_marker[1] is None:
                        logger.warning(
                            "PRICE STALENESS [%s/%s]: Alpaca crypto quote mid missing "
                            "timestamp metadata. Blocking before Kalman update.",
                            t_a,
                            t_b,
                        )
                        return skip("stale_price_snapshot")

                    previous_marker, repeat_count = self._crypto_snapshot_pair_prices.get(
                        pair["id"],
                        ((None, None), 0),
                    )
                    repeat_count = repeat_count + 1 if previous_marker == pair_marker else 0
                    self._crypto_snapshot_pair_prices[pair["id"]] = (pair_marker, repeat_count)
                    if repeat_count >= CRYPTO_SNAPSHOT_STALE_REPEAT_LIMIT:
                        stale_subject = (
                            "Alpaca crypto quote mid timestamps"
                            if "alpaca_crypto_quote_mid" in {source_a, source_b}
                            else "Alpaca crypto snapshot prices"
                        )
                        logger.warning(
                            "PRICE STALENESS [%s/%s]: %s repeated "
                            "unchanged at %s for %s consecutive scan(s). Blocking before Kalman update.",
                            t_a,
                            t_b,
                            stale_subject,
                            pair_marker,
                            repeat_count,
                        )
                        return skip("stale_price_snapshot")
                else:
                    self._crypto_snapshot_pair_prices.pop(pair["id"], None)

            # Feature 007: Kalman Filter Update
            kf = await arbitrage_service.get_or_create_filter(pair['id'])
            if kf is None:
                logger.warning("Kalman filter unavailable for pair %s — skipping tick.", pair['id'])
                return skip("kalman_unavailable")

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
                arbitrage_service.filters.pop(pair['id'], None)
                arbitrage_service.filter_fingerprints.pop(pair['id'], None)
                try:
                    await redis_service.client.delete(f"kalman:{pair['id']}")
                except Exception as exc:
                    logger.warning(
                        "KALMAN GUARD [%s/%s]: failed to delete Redis state for quarantine: %s",
                        t_a,
                        t_b,
                        exc,
                    )
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
                if not already_quarantined:
                    self._kalman_quarantine_reload_requested = True
                    logger.warning(
                        "KALMAN QUARANTINE [%s/%s]: queued historical rebuild after this scan.",
                        t_a,
                        t_b,
                    )
                return skip("kalman_state_invalid")

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

            if abs(z_score) > entry_zscore:
                signal_id = str(uuid.uuid4())
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
                    return diagnostic
                await audit_service.log_thought_process(signal_id, decision_state)
                logger.info(f"ORCHESTRATOR [{t_a}/{t_b}] confidence={decision_state['final_confidence']:.3f} verdict={decision_state['final_verdict']}")
                final_confidence = float(decision_state["final_confidence"])
                hedge_ratio = float(pair.get("hedge_ratio", 1.0))

                if final_confidence <= settings.MONITOR_MIN_AI_CONFIDENCE:
                    await self._upsert_active_signal(
                        t_a,
                        t_b,
                        z_score=z_score,
                        status="VETOED",
                        confidence=final_confidence,
                        hedge_ratio=hedge_ratio,
                    )
                    logger.info(f"ORCHESTRATOR [{t_a}/{t_b}] VETOED: Confidence {final_confidence:.3f} too low.")
                    diagnostic["verdict"] = "VETOED"
                    diagnostic["confidence"] = final_confidence
                    diagnostic["reason"] = "confidence_below_threshold"
                    return diagnostic

                # Calculate expected profit/loss from the same gross pair
                # notional that execution will use.
                effective_sizing_base = sizing_base if sizing_base > 0 else settings.PAPER_TRADING_STARTING_CASH
                risk_res = risk_service.validate_trade(
                    ticker=f"{t_a}_{t_b}",
                    total_portfolio_cash=effective_sizing_base,
                    amount_fiat=effective_sizing_base,
                    win_prob=settings.DEFAULT_WIN_PROBABILITY,
                    win_loss_ratio=settings.DEFAULT_WIN_LOSS_RATIO
                )
                desired_notional = cap_pair_notional(
                    float(risk_res["final_amount"]),
                    effective_sizing_base,
                    min_trade_value=settings.MIN_TRADE_VALUE,
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
                    return diagnostic

                direction = "Short-Long" if z_score > 0 else "Long-Short"
                legs = build_pair_legs(
                    price_a=price_a,
                    price_b=price_b,
                    hedge_ratio=hedge_ratio,
                    gross_notional=desired_notional,
                    direction=direction,
                )
                est_friction_pct = max(
                    float(risk_res["fee_status"].get("total_friction_percent", 0.0)),
                    float(pair.get("estimated_cost_pct") or 0.0),
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
                    await self._upsert_active_signal(
                        t_a,
                        t_b,
                        z_score=z_score,
                        status="APPROVED",
                        confidence=final_confidence,
                        hedge_ratio=hedge_ratio,
                    )
                    approved = await notification_service.request_approval(trade_summary)
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

                diagnostic["confidence"] = final_confidence
            else:
                # Cleanup inactive signals
                await self._remove_active_signal(t_a, t_b)
                skip("below_entry_threshold")

            return diagnostic

        except Exception as e:
            logger.error(f"Error processing pair {pair.get('ticker_a')}: {e}")
            diagnostic["reason"] = "exception"
            return diagnostic

    async def execute_trade(self, pair, direction, price_a, price_b, signal_id, entry_context: dict | None = None):
        """Executes a trade and logs to PostgreSQL."""
        def execution_result(executed: bool, reason: str, **details) -> dict:
            result = {"executed": executed, "reason": reason}
            result.update(details)
            return result

        entry_context = entry_context or {}
        t_a, t_b = pair['ticker_a'], pair['ticker_b']
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
            valid_bid_ask = bid_a > 0 and ask_a > 0 and bid_b > 0 and ask_b > 0
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

        venue = self.brokerage.get_venue(t_a)
        crypto_pair = is_crypto_pair(t_a, t_b)
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
        risk_res = risk_service.validate_trade(
            ticker=f"{t_a}_{t_b}",
            total_portfolio_cash=sizing_base,
            amount_fiat=sizing_base,
            win_prob=settings.DEFAULT_WIN_PROBABILITY,
            win_loss_ratio=settings.DEFAULT_WIN_LOSS_RATIO
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
        )
        if settings.TARGET_CASH_PER_LEG > 0:
            desired_notional = min(desired_notional, settings.TARGET_CASH_PER_LEG * 2.0)

        if desired_notional <= 0:
            logger.info("Sized pair notional is below MIN_TRADE_VALUE. Skipping trade.")
            return execution_result(False, "below_min_trade_value")

        hedge_ratio = float(pair.get("hedge_ratio", 1.0))
        legs = build_pair_legs(
            price_a=price_a,
            price_b=price_b,
            hedge_ratio=hedge_ratio,
            gross_notional=desired_notional,
            direction=direction,
        )
        size_a = legs.quantity_a
        size_b = legs.quantity_b
        target_cash_a = legs.notional_a
        target_cash_b = legs.notional_b

        logger.info(
            "RISK APPROVED SIZE: Gross=$%.2f, LegA=$%.2f, LegB=$%.2f for %s/%s (Hedge: %.4f, Kelly: %.4f, Base: $%.2f, MaxCap: $%.2f)",
            legs.gross_notional, target_cash_a, target_cash_b, t_a, t_b, hedge_ratio, risk_res["kelly_fraction"], sizing_base, risk_res["max_allowed_fiat"]
        )

        # Feature 008 - Sector Cluster Guard (prospective, race-condition-safe).
        # Both legs are counted as new exposure (target_cash each) so the check
        # is evaluated BEFORE the trade is placed, not after.  This prevents two
        # signals in the same scan window from independently passing the 30 % cap
        # and then together pushing the sector to 60 %.
        pair_sector = resolve_pair_sector(pair["id"], t_a, t_b, settings.PAIR_SECTORS)
        current_portfolio = await shadow_service.get_active_portfolio_with_sectors()
        total_size = sum(p['size'] for p in current_portfolio)
        sector_size = sum(p['size'] for p in current_portfolio if p['sector'] == pair_sector)
        new_trade_size = target_cash_a + target_cash_b  # sum of both legs

        # Feature 008 Fix: prevent "Empty Portfolio Trap" where the first trade
        # is always 100% exposure. We use the larger of actual total size or
        # a theoretical 'full portfolio' base (e.g. 5x target leg cash).
        denominador = max(total_size + new_trade_size, sizing_base)
        projected_exposure = (sector_size + new_trade_size) / denominador

        if projected_exposure > settings.MAX_SECTOR_EXPOSURE:
            logger.warning(
                f"CLUSTER GUARD: Rejecting {t_a}/{t_b}. Adding this trade would push "
                f"'{pair_sector}' exposure to {projected_exposure:.1%} (base: ${denominador:.2f}), "
                f"exceeding the {settings.MAX_SECTOR_EXPOSURE:.0%} cap."
            )
            return execution_result(False, "sector_exposure_guard")

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

        # Feature 037: only paper mode is forced to shadow execution. In live
        # mode, crypto routes through the configured brokerage provider.
        if settings.PAPER_TRADING:
            await persistence_service.log_trade_journal({
                "signal_id": uuid.UUID(signal_id),
                "entry_regime": regime_info["regime"],
                "metrics_at_entry": {
                    "z_score": float(entry_context.get("z_score", risk_res.get("z_score", 0.0)) or 0.0),
                    "entry_zscore": entry_context.get("entry_zscore"),
                    "confidence": entry_context.get("confidence"),
                    "orchestrator_verdict": entry_context.get("orchestrator_verdict"),
                    "win_prob": settings.DEFAULT_WIN_PROBABILITY,
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

        logger.info(f"LIVE EXECUTION: Placing orders for {exec_t_a}/{exec_t_b} - {direction}")

        # T-02: Atomic execution guard - abort if Leg A fails; emergency-close if Leg B fails
        # Leg A
        res_a = await self.brokerage.place_value_order(
            exec_t_a,
            target_cash_a,
            side_a,
            price=price_a,
            client_order_id=f"{signal_id}-A",
        )
        order_id_a = res_a.get("order_id") or res_a.get("orderId") or res_a.get("client_order_id") or str(uuid.uuid4())

        if res_a.get("requires_reconciliation") or res_a.get("status") == "unknown":
            await persistence_service.log_trade({
                "order_id": order_id_a,
                "signal_id": uuid.UUID(signal_id),
                "ticker": t_a,
                "side": OrderSide.SELL if side_a == "SELL" else OrderSide.BUY,
                "quantity": size_a,
                "price": price_a,
                "status": OrderStatus.NEEDS_MANUAL_RECONCILIATION,
                "venue": venue,
                "metadata_json": {
                    "broker_order_id": order_id_a,
                    "submitted_qty": size_a,
                    "side": side_a,
                    "symbol": t_a,
                    "status": "unknown",
                    "broker_response": res_a,
                }
            })
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
            await notification_service.send_message(
                f"Execution aborted: Leg A failed for {exec_t_a}. Broker response: {broker_msg}"
            )
            return execution_result(False, "leg_a_rejected")
        await persistence_service.log_trade({
            "order_id": order_id_a,
            "signal_id": uuid.UUID(signal_id),
            "ticker": t_a,
            "side": OrderSide.SELL if side_a == "SELL" else OrderSide.BUY,
            "quantity": size_a,
            "price": price_a,
            "status": OrderStatus.LEG_A_SUBMITTED,
            "venue": venue,
            "metadata_json": {
                "broker_order_id": order_id_a,
                "submitted_qty": size_a,
                "side": side_a,
                "symbol": t_a,
                "status": "submitted",
                "broker_response": res_a,
            }
        })

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
        leg_a_fully_filled = filled_qty_a + 1e-9 >= expected_qty_a
        if status_raw_a in ("partially_filled", "partial_fill"):
            status_a = OrderStatus.LEG_A_PARTIAL
        elif status_raw_a in ("rejected", "canceled", "cancelled", "expired"):
            status_a = OrderStatus.LEG_A_REJECTED
        elif status_raw_a == "filled" and filled_qty_a > 0 and leg_a_fully_filled:
            status_a = OrderStatus.LEG_A_FILLED
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
                        close_qty_short = close_filled_qty + 1e-9 < filled_qty_a
                        if close_status_raw != "filled" or close_filled_qty <= 0 or close_qty_short:
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
            await persistence_service.update_signal_status(uuid.UUID(signal_id), blocked_status)
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

        # Leg B
        res_b = await self.brokerage.place_value_order(
            exec_t_b,
            target_cash_b,
            side_b,
            price=price_b,
            client_order_id=f"{signal_id}-B",
        )
        order_id_b = res_b.get("order_id") or res_b.get("orderId") or res_b.get("client_order_id") or str(uuid.uuid4())

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
          status_b = OrderStatus.ORDER_SUBMITTED if res_b.get("status") != "error" else OrderStatus.LEG_B_REJECTED
          order_id_b = res_b.get("order_id") or res_b.get("orderId") or str(uuid.uuid4())

        await persistence_service.log_trade({
            "order_id": order_id_b,
            "signal_id": uuid.UUID(signal_id),
            "ticker": t_b,
            "side": OrderSide.BUY if side_b == "BUY" else OrderSide.SELL,
            "quantity": size_b,
            "price": price_b,
            "status": OrderStatus.LEG_B_SUBMITTED,
            "venue": venue,
            "metadata_json": {
                "broker_order_id": order_id_b,
                "submitted_qty": size_b,
                "side": side_b,
                "symbol": t_b,
                "status": "submitted",
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
            close_res = await self.brokerage.place_value_order(
                exec_t_a,
                target_cash_a,
                close_side_a,
                price=price_a,
                client_order_id=f"{signal_id}-A-EMERGENCY-CLOSE",
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
                    "quantity": size_a,
                    "price": price_a,
                    "status": OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION,
                    "metadata_json": {
                        "orphaned": True,
                        "reason": close_reason,
                        "broker_response": close_res,
                    },
                })
            else:
                close_fill = await self._await_order_fill(close_order_id, timeout=30)
                close_status_raw = str((close_fill or {}).get("status", "")).lower()
                close_filled_qty = float((close_fill or {}).get("filled_qty") or 0.0)
                expected_close_qty = filled_qty_a if filled_qty_a > 0 else size_a
                close_qty_short = close_filled_qty + 1e-9 < expected_close_qty
                if close_status_raw != "filled" or close_filled_qty <= 0 or close_qty_short:
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
                        "quantity": size_a,
                        "price": price_a,
                        "status": OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION,
                        "metadata_json": {
                            "orphaned": True,
                            "reason": "emergency_close_unconfirmed",
                            "broker_response": close_res,
                            "close_order_id": close_order_id,
                            "close_fill": close_fill,
                            "expected_qty": expected_close_qty,
                        },
                    })
                else:
                    logger.info(
                        f"EMERGENCY CLOSE SUCCESS: Orphaned {exec_t_a} position closed "
                        f"[order_id={close_order_id}]."
                    )

        if status_b == OrderStatus.LEG_B_REJECTED:
            broker_msg_b = res_b.get("message") or res_b.get("error") or res_b
            await emergency_close_leg_a_after_leg_b_failure(broker_msg_b)
            return execution_result(False, "leg_b_rejected")
        fill_b = await self._await_order_fill(order_id_b, timeout=30)
        if not fill_b:
            status_b = OrderStatus.LEG_B_SUBMITTED
            await notification_service.send_message(
                f"Leg B ({exec_t_b}) not terminal within 30s; signal {signal_id} requires follow-up."
            )
        else:
            status_raw_b = str(fill_b.get('status', '')).lower()
            if status_raw_b in ("partially_filled", "partial_fill"):
                status_b = OrderStatus.LEG_B_PARTIAL
            elif status_raw_b in ("rejected", "canceled", "cancelled", "expired"):
                status_b = OrderStatus.LEG_B_REJECTED
            else:
                status_b = OrderStatus.LEG_B_FILLED
        filled_qty_b = float((fill_b or {}).get("filled_qty") or 0.0)
        fill_price_b = float((fill_b or {}).get("filled_avg_price") or 0.0)
        if status_b == OrderStatus.LEG_B_REJECTED:
            broker_msg_b = (fill_b or {}).get("message") or (fill_b or {}).get("error") or fill_b or res_b
            await emergency_close_leg_a_after_leg_b_failure(broker_msg_b)
            return execution_result(False, "leg_b_rejected_after_submit")
        leg_b_partial_fill = status_b == OrderStatus.LEG_B_PARTIAL
        if leg_b_partial_fill:
            await persistence_service.update_signal_status(uuid.UUID(signal_id), OrderStatus.PARTIAL_EXPOSURE)
            alert = (
                f"Leg B ({exec_t_b}) partially filled. "
                f"Signal remains PARTIAL_EXPOSURE and requires manual reconciliation. "
                f"status={str((fill_b or {}).get('status', '')).lower() or 'unknown'} "
                f"filled_qty={filled_qty_b} expected_qty={float(size_b)} "
                f"order_id={order_id_b} signal_id={signal_id}"
            )
            logger.critical(alert)
            await notification_service.send_message(alert)
        pair_status = (
            OrderStatus.OPEN_PAIR
            if status_a == OrderStatus.LEG_A_FILLED and status_b == OrderStatus.LEG_B_FILLED
            else OrderStatus.PARTIAL_EXPOSURE
        )
        visible_status = pair_status

        # M-05: Journal written only after both broker legs have returned successfully
        if not leg_b_partial_fill:
            await persistence_service.log_trade_journal({
                "signal_id": uuid.UUID(signal_id),
                "entry_regime": regime_info["regime"],
                "metrics_at_entry": {
                    "z_score": risk_res.get("z_score", 0.0),
                    "win_prob": settings.DEFAULT_WIN_PROBABILITY,
                    "regime_confidence": regime_info["confidence"],
                    "features": regime_info["features"]
                }
            })

        # Log Leg A
        await persistence_service.log_trade({
            "order_id": order_id_a,
            "signal_id": uuid.UUID(signal_id),
            "ticker": t_a,
            "side": OrderSide.SELL if side_a == "SELL" else OrderSide.BUY,
            "quantity": filled_qty_a or size_a,
            "price": fill_price_a or price_a,
            "status": visible_status,
            "venue": venue,
            "metadata_json": {
                "broker_order_id": order_id_a,
                "submitted_qty": size_a,
                "side": side_a,
                "symbol": exec_t_a,
                "order_status": status_a.value,
                "pair_status": pair_status.value,
                "broker_response": res_a,
                "fill_snapshot": fill_a,
            }
        })

        # Log Leg B
        await persistence_service.log_trade({
            "order_id": order_id_b,
            "signal_id": uuid.UUID(signal_id),
            "ticker": t_b,
            "side": OrderSide.BUY if side_b == "BUY" else OrderSide.SELL,
            "quantity": filled_qty_b or size_b,
            "price": fill_price_b or price_b,
            "status": visible_status,
            "venue": venue,
            "metadata_json": {
                "broker_order_id": order_id_b,
                "submitted_qty": size_b,
                "side": side_b,
                "symbol": exec_t_b,
                "order_status": status_b.value,
                "pair_status": pair_status.value,
                "broker_response": res_b,
                "fill_snapshot": fill_b,
            }
        })

        logger.info(f"TRADE EXECUTED: {t_a}/{t_b} {direction} | Status: A={OrderStatus.LEG_A_FILLED.value}, B={OrderStatus.LEG_B_FILLED.value}")
        return execution_result(pair_status == OrderStatus.OPEN_PAIR, pair_status.value)

    async def _recheck_cointegration(self, pair: dict):
        """
        Re-validates the ADF cointegration test for a single pair using the
        last 30 days of hourly data.  Called once per calendar day per pair.

        If the p-value rises above 0.10 the pair is marked is_cointegrated=False
        and trading is suspended until the next re-check restores it.
        A Telegram/console alert is fired on both break and restore events.
        """
        t_a, t_b = pair['ticker_a'], pair['ticker_b']
        try:
            hist_data = await data_service.get_historical_data_async([t_a, t_b], "30d", "1h")
            if hist_data is None or hist_data.empty:
                return

            col_a = next((c for c in hist_data.columns if t_a in c), None)
            col_b = next((c for c in hist_data.columns if t_b in c), None)
            if not col_a or not col_b:
                return

            is_crypto = is_crypto_pair(t_a, t_b)
            p_thresh = 0.25 if is_crypto else settings.COINTEGRATION_PVALUE_THRESHOLD
            pass_thresh = 0.2 if is_crypto else settings.COINTEGRATION_ROLLING_PASS_RATE

            is_coint, p_val, _ = arbitrage_service.check_cointegration(
                hist_data[col_a], hist_data[col_b], pvalue_threshold=p_thresh
            )

            # Spec 037: rolling-window stability. If the pair was statically
            # cointegrated but rolling-window unstable, suspend it. The
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
                pair['is_cointegrated'] = False
                if previously_coint:
                    # Only alert on a real break (True -> False transition).
                    # If the pair was already non-cointegrated at startup, stay quiet.
                    msg = (
                        f"COINTEGRATION BREAK: {t_a}/{t_b} - "
                        f"ADF p-value={p_val:.4f} > 0.05. "
                        f"Pair suspended until cointegration is restored."
                    )
                    logger.warning(msg)
                    await notification_service.send_message(msg)
                else:
                    logger.debug(
                        f"[{t_a}/{t_b}] Still non-cointegrated (p={p_val:.4f}). "
                        f"Staying suspended."
                    )
            else:
                pair['is_cointegrated'] = True
                if not previously_coint:
                    # Alert only on a real restore (False -> True transition).
                    msg = (
                        f"COINTEGRATION RESTORED: {t_a}/{t_b} - "
                        f"ADF p-value={p_val:.4f}. Pair re-activated."
                    )
                    logger.info(msg)
                    await notification_service.send_message(msg)
                else:
                    logger.debug(
                        f"[{t_a}/{t_b}] Cointegration confirmed (p={p_val:.4f})."
                    )
        except Exception as e:
            logger.error(f"Error re-checking cointegration for {t_a}/{t_b}: {e}")

    async def _fail_fast_on_unresolved_execution_state(self) -> bool:
        unresolved_count = await persistence_service.mark_startup_unsafe_signals_needs_reconciliation()
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
        return str(symbol or "").upper().replace("/", "").replace("-", "")

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

        ledger_symbols = {
            self._canonical_position_symbol(leg.get("ticker"))
            for signal in open_signals
            for leg in signal.get("legs", [])
            if leg.get("ticker")
        }
        unmanaged_symbols = []
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
            if canonical_symbol and canonical_symbol not in ledger_symbols:
                unmanaged_symbols.append(str(raw_symbol))

        if not unmanaged_symbols:
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
        await self.initialize_pairs()
        if not self.active_pairs:
            logger.warning("Startup loaded zero active pairs. Retrying pair initialization once before entering the scan loop.")
            await self.reload_pairs()
        # Make this monitor instance discoverable by dashboard endpoints
        # (so /api/pairs can hot-reload, etc).
        dashboard_service.attach_monitor(self)
        await dashboard_service.start()

        # Sprint J: Start Telegram Listener (Async)
        await notification_service.start_listening()

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
            return
        if not await self._fail_fast_on_broker_ledger_mismatch():
            return

        # Reset circuit breaker on clean startup so a stale DEGRADED_MODE
        # from a previous crashed session doesn't silently block all signals.
        await persistence_service.set_system_state("operational_status", "NORMAL")
        await persistence_service.set_system_state("consecutive_api_timeouts", "0")
        logger.info("Circuit breaker reset to NORMAL on startup.")

        # Start periodic Scouting & Rotation background task
        background_task_watchdog.create_task(
            self._auto_scout_and_rotate_loop(),
            name="monitor:auto_scout_and_rotate_loop",
        )

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

                        pnl = await persistence_service.get_total_pnl()
                        await dashboard_service.update(
                            stage="Monitoring",
                            details=f"Scanning {len(self.active_pairs)} pairs...",
                            pnl=pnl,
                            active_signals=self.active_signals
                        )
                    except Exception as e:
                        logger.error(f"Error pushing metrics to dashboard: {e}")
                        await dashboard_service.update("Monitoring", f"Scanning {len(self.active_pairs)} pairs...")

                    # Exit Strategy Loop - M-06: run all exit evaluations concurrently
                    open_signals = []
                    try:
                        progress.update(scan_task, description="Checking open positions...")
                        open_signals = await persistence_service.get_open_signals()
                        if open_signals:
                            await asyncio.gather(
                                *[self._evaluate_exit_conditions(signal) for signal in open_signals],
                                return_exceptions=True  # one signal failing doesn't block the rest
                            )
                    except Exception as e:
                        logger.error(f"Error evaluating open signals for exits: {e}")

                    if not self.active_pairs:
                        logger.warning("No active pairs loaded; attempting pair reload before scanning.")
                        await self.reload_pairs()
                        progress.update(scan_task, total=len(self.active_pairs), completed=0)
                        if not self.active_pairs:
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

                    progress.update(scan_task, description=f"Fetching prices for {len(all_tickers)} tickers...", completed=0, total=len(scan_pairs))
                    latest_prices = (
                        await data_service.get_latest_price_async(list(dict.fromkeys(all_tickers)))
                        if all_tickers
                        else {}
                    )

                    # Daily Global Reset
                    today = datetime.now().date()
                    if self.current_day != today:
                        logger.info(f"--- [bold yellow]NEW TRADING DAY[/]: {today} ---")
                        self.current_day = today
                        self.bumped_pairs_today = {} # Reset Kalman bumps for the new day


                    # Daily cointegration re-validation
                    today = datetime.now().date()
                    for pair in self.active_pairs:
                        if self.last_cointegration_check.get(pair['id']) != today:
                            pair_id = pair.get("id") or f"{pair.get('ticker_a')}_{pair.get('ticker_b')}"
                            background_task_watchdog.create_task(
                                self._recheck_cointegration(pair),
                                name=f"monitor:recheck_cointegration:{pair_id}",
                            )
                            self.last_cointegration_check[pair['id']] = today

                    results = []
                    # Fetch sizing base once per iteration to avoid API spam in process_pair
                    current_sizing_base = await self._get_sizing_base()

                    for i, pair in enumerate(scan_pairs):
                        progress.update(scan_task, description=f"Scanning [magenta]{pair['ticker_a']}/{pair['ticker_b']}[/]", completed=i)
                        res = await self.process_pair(pair, latest_prices, sizing_base=current_sizing_base)
                        results.append(res)
                        # Small delay between pairs to spread out API load
                        if i < len(scan_pairs) - 1:
                            # Use a sub-task for the delay so it's visible? Or just update description.
                            progress.update(scan_task, description=f"Waiting 2s... ([dim]{pair['ticker_a']}/{pair['ticker_b']} done[/])")
                            await asyncio.sleep(2.0)

                    progress.update(scan_task, completed=len(scan_pairs), description="Scan iteration complete")

                    # L-14: Enriched heartbeat
                    active_signal_count, vetoed_count = summarize_scan_iteration(
                        results,
                        settings.MONITOR_MIN_AI_CONFIDENCE,
                    )

                    summary_msg = (
                        f"[bold green]Iteration Complete[/] | "
                        f"Scanned: {len(scan_pairs)}/{len(self.active_pairs)} | "
                        f"Signals: {active_signal_count} | "
                        f"Vetoed: {vetoed_count} | "
                        f"Open: {len(open_signals)}"
                    )
                    logger.info(summary_msg)
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

    async def _evaluate_exit_conditions(self, signal: dict):
        """Monitors open positions for Take Profit or Stop Loss."""
        sig_id = signal["signal_id"]
        legs = signal.get("legs", [])
        if len(legs) != 2: return

        leg_a, leg_b = legs[0], legs[1]
        t_a, t_b = leg_a["ticker"], leg_b["ticker"]

        # Get real-time prices
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
        pair_id = f"{t_a}_{t_b}"
        kf = await arbitrage_service.get_or_create_filter(pair_id)
        if not kf: return

        # Calculate current dynamic z-score based on latest price
        spread, z_score = kf.calculate_spread_and_zscore(p_a, p_b)

        # Statistical Take Profit (Mean Reversion complete)
        if abs(z_score) <= settings.TAKE_PROFIT_ZSCORE:
            logger.info(f"TAKE PROFIT reached for {t_a}/{t_b} (Z-Score: {z_score:.2f}).")
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

            if not settings.PAPER_TRADING:
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
                    if (
                        close_status_raw != "filled"
                        or close_filled_qty <= 0
                        or close_filled_qty + 1e-9 < expected_close_qty
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

            # M-04: Compute realized PnL from entry vs exit price per leg
            leg_a, leg_b = signal["legs"][0], signal["legs"][1]
            exit_prices, pnl = calculate_realized_pnl(
                signal,
                prices_by_ticker=prices_by_ticker or {
                    leg_a["ticker"]: float(price_a),
                    leg_b["ticker"]: float(price_b),
                },
            )

            # N2 fix: in paper mode, route through shadow_service so the shadow ledger
            # gets a proper close log with directional PnL breakdown.
            # shadow_service.close_simulated_trade does NOT call persistence - we handle
            # DB writes once here for both live and paper paths to preserve exit_reason.
            if settings.PAPER_TRADING:
                direction = "Short-Long" if leg_a["side"] == "SELL" else "Long-Short"
                await shadow_service.close_simulated_trade(
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
