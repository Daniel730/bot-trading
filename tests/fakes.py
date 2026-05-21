from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Iterable


class FakeBroker:
    def __init__(
        self,
        *,
        cash: float = 10_000.0,
        equity: float | None = None,
        buying_power: float | None = None,
        portfolio: list[dict[str, Any]] | None = None,
        pending_orders: list[dict[str, Any]] | None = None,
        venue: str = "ALPACA",
    ):
        self.cash = cash
        self.equity = cash if equity is None else equity
        self.buying_power = cash if buying_power is None else buying_power
        self.portfolio = list(portfolio or [])
        self.pending_orders = list(pending_orders or [])
        self.venue = venue
        self.default_available_quantity = 1_000_000.0
        self.placed_orders: list[dict[str, Any]] = []
        self.executed_orders: list[dict[str, Any]] = []

    def get_venue(self) -> str:
        return self.venue

    def _format_ticker(self, ticker: str) -> str:
        return str(ticker).replace("-", "")

    async def get_account_cash(self) -> float:
        return self.cash

    async def get_account_equity(self) -> float:
        return self.equity

    async def get_account_buying_power(self) -> float:
        return self.buying_power

    async def get_portfolio(self) -> list[dict[str, Any]]:
        return list(self.portfolio)

    async def get_pending_orders(self) -> list[dict[str, Any]]:
        return list(self.pending_orders)

    async def get_pending_orders_value(self) -> float:
        value = 0.0
        for order in self.pending_orders:
            value += float(order.get("notional") or order.get("value") or 0.0)
        return value

    async def get_available_quantity(self, ticker: str) -> float:
        canonical = self._format_ticker(ticker)
        for position in self.portfolio:
            position_ticker = self._format_ticker(position.get("ticker", ""))
            if position_ticker == canonical:
                return float(position.get("available_quantity", position.get("quantity", 0.0)))
        return self.default_available_quantity

    async def place_value_order(
        self,
        ticker: str,
        amount: float,
        side: str,
        price: float | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        order_id = client_order_id or f"fake-order-{len(self.placed_orders) + 1}"
        order = {
            "ticker": ticker,
            "amount": amount,
            "side": side,
            "price": price,
            "client_order_id": client_order_id,
            "order_id": order_id,
        }
        self.placed_orders.append(order)
        return {"status": "success", "order_id": order_id, "filled_qty": 1.0}

    async def execute_order(self, ticker: str, amount: float, side: str) -> dict[str, Any]:
        self.executed_orders.append({"ticker": ticker, "amount": amount, "side": side})
        return {"status": "success", "order_id": f"fake-exec-{len(self.executed_orders)}"}


class FakeMarketData:
    def __init__(self):
        self.latest_prices: dict[str, float] = {}
        self.bid_ask: dict[str, tuple[float, float]] = {}
        self.historical_data: dict[tuple[tuple[str, ...], str, str], Any] = {}
        self.last_price_sources: dict[str, str] = {}
        self.last_price_timestamps: dict[str, Any] = {}

    async def get_bid_ask(self, ticker: str) -> tuple[float, float]:
        return self.bid_ask.get(ticker, (99.5, 100.5))

    async def get_latest_price_async(self, tickers: Iterable[str]) -> dict[str, float | None]:
        return {ticker: self.latest_prices.get(ticker) for ticker in tickers}

    async def get_historical_data_async(
        self,
        tickers: Iterable[str],
        period: str = "1y",
        interval: str = "1d",
    ) -> Any:
        key = (tuple(tickers), period, interval)
        return self.historical_data.get(key)


class FakeRedisClient:
    def __init__(self, owner: "FakeRedis"):
        self.owner = owner

    async def ping(self):
        return True

    async def aclose(self):
        return None

    async def get(self, key: str):
        return self.owner.raw_values.get(key)

    async def set(self, key: str, value: Any, **kwargs):
        self.owner.raw_values[key] = value
        return True

    async def delete(self, key: str):
        self.owner.raw_values.pop(key, None)
        self.owner.json_values.pop(key, None)
        self.owner.locks.discard(key)
        return 1


class FakeRedis:
    def __init__(self):
        self.client = FakeRedisClient(self)
        self.raw_values: dict[str, Any] = {}
        self.json_values: dict[str, Any] = {}
        self.prices: dict[str, float] = {}
        self.kalman_states: dict[str, dict[str, Any]] = {}
        self.fundamental_scores: dict[str, dict[str, Any]] = {}
        self.locks: set[str] = set()
        self.latency_metrics: list[dict[str, Any]] = []
        self.published: list[tuple[str, Any]] = []

    async def set_price(self, ticker: str, price: float):
        self.prices[ticker] = price

    async def get_price(self, ticker: str) -> float | None:
        return self.prices.get(ticker)

    async def set_json(self, key: str, value: Any, ex: int | None = None):
        self.json_values[key] = value

    async def set_json_nx(self, key: str, value: Any, ex: int | None = None) -> bool:
        if key in self.locks:
            return False
        self.locks.add(key)
        self.json_values[key] = value
        return True

    async def get_json(self, key: str) -> Any:
        return self.json_values.get(key)

    async def delete(self, key: str) -> int:
        self.raw_values.pop(key, None)
        self.json_values.pop(key, None)
        self.locks.discard(key)
        return 1

    async def publish(self, channel: str, message: Any):
        self.published.append((channel, message))

    async def save_kalman_state(self, ticker_pair: str, *args, **kwargs):
        self.kalman_states[ticker_pair] = {"args": args, **kwargs}

    async def get_kalman_state(self, ticker_pair: str) -> dict[str, Any] | None:
        return self.kalman_states.get(ticker_pair)

    async def get_fundamental_score(self, ticker: str) -> dict[str, Any] | None:
        return self.fundamental_scores.get(ticker)

    async def set_fundamental_score(self, ticker: str, score_data: dict[str, Any]):
        self.fundamental_scores[ticker] = score_data

    async def set_nx(self, key: str, value: Any, expire: int = 60) -> bool:
        if key in self.locks:
            return False
        self.locks.add(key)
        self.raw_values[key] = value
        return True

    async def push_latency_metrics(self, metrics: dict[str, Any]):
        self.latency_metrics.insert(0, metrics)

    async def get_recent_latency(self, count: int = 100) -> list[dict[str, Any]]:
        return self.latency_metrics[:count]


class _FakeConnection(AbstractContextManager):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, *args, **kwargs):
        return None


class _FakeEngine:
    def connect(self):
        return _FakeConnection()

    async def dispose(self):
        return None


class FakePersistence:
    def __init__(self):
        self.engine = _FakeEngine()
        self.system_state: dict[str, Any] = {}
        self.open_signals: list[dict[str, Any]] = []
        self.active_trading_pairs: list[dict[str, Any]] = []
        self.trade_logs: list[dict[str, Any]] = []
        self.journal_logs: list[dict[str, Any]] = []
        self.status_updates: list[tuple[Any, Any]] = []

    async def init_db(self):
        return None

    async def get_open_signals(self):
        return list(self.open_signals)

    async def get_active_trading_pairs(self):
        return list(self.active_trading_pairs)

    async def set_system_state(self, key: str, value: Any):
        self.system_state[key] = value

    async def get_system_state(self, key: str, default: Any = None):
        return self.system_state.get(key, default)

    async def log_trade(self, payload: dict[str, Any]):
        self.trade_logs.append(payload)

    async def log_trade_journal(self, payload: dict[str, Any]):
        self.journal_logs.append(payload)

    async def update_signal_status(self, signal_id: Any, status: Any):
        self.status_updates.append((signal_id, status))

    async def close_trade(self, *args, **kwargs):
        return None

    async def mark_signal_closing_if_open(self, *args, **kwargs) -> bool:
        return True

    async def get_signal_status(self, *args, **kwargs):
        return None

    async def get_total_pnl(self) -> float:
        return 0.0

    async def mark_startup_unsafe_signals_needs_reconciliation(self) -> int:
        return 0

    async def get_startup_reconciliation_rows(self) -> list[dict[str, Any]]:
        return []

    async def get_agent_metrics(self, *args, **kwargs):
        return (1, 1)

    async def update_agent_metrics(self, *args, **kwargs):
        return None
