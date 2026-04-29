import asyncio
import json
import logging
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from src.config import settings
from src.services.redis_service import redis_service

logger = logging.getLogger(__name__)

STABLECOINS = {"USDT", "USDC", "DAI", "FDUSD", "TUSD", "USDE", "BUSD"}
UNKNOWN_OWNER_TYPES = {"", "unknown", "unknown_wallet", "wallet"}
SUMMARY_SYMBOL_STABLECOIN = "STABLECOIN"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class WhaleEvent:
    symbol: str
    chain: str
    timestamp: str
    value_usd: float
    tx_type: str
    from_owner_type: str
    to_owner_type: str
    exchange_inflow: bool
    exchange_outflow: bool
    stablecoin: bool
    tx_hash: str
    source: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WhaleWatcherService:
    """
    Normalizes whale events and maintains rolling Redis summaries.

    Provider connectors should call record_event() from a background worker.
    The orchestrator reads only the cached summary keys via WhaleWatcherAgent.
    """

    event_key_prefix = "whale:events:"
    summary_key_prefix = "whale:summary:"

    def normalize_symbol(self, value: str) -> str:
        symbol = (value or "").upper().strip()
        if symbol.endswith("-USD"):
            symbol = symbol[:-4]
        if symbol in {"WETH", "ETH2"}:
            return "ETH"
        if symbol == "WBTC":
            return "BTC"
        return symbol

    def is_crypto_ticker(self, value: str) -> bool:
        symbol = (value or "").upper().strip()
        return symbol.endswith("-USD") or self.normalize_symbol(symbol) in settings.CRYPTO_TOKEN_MAPPING

    def parse_timestamp(self, value: Any = None) -> datetime:
        if value is None:
            return datetime.now(timezone.utc)
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        if isinstance(value, str):
            normalized = value.strip()
            if normalized.endswith("Z"):
                normalized = normalized[:-1] + "+00:00"
            try:
                parsed = datetime.fromisoformat(normalized)
                return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                logger.debug("WhaleWatcherService: could not parse timestamp %r, using now", value)
        return datetime.now(timezone.utc)

    def normalize_event(self, payload: dict[str, Any]) -> WhaleEvent:
        raw_symbol = payload.get("symbol") or payload.get("asset") or payload.get("ticker") or ""
        symbol = self.normalize_symbol(str(raw_symbol))
        timestamp = self.parse_timestamp(payload.get("timestamp") or payload.get("time"))
        from_owner = str(payload.get("from_owner_type") or payload.get("from_type") or "unknown").lower()
        to_owner = str(payload.get("to_owner_type") or payload.get("to_type") or "unknown").lower()
        tx_type = str(payload.get("tx_type") or payload.get("type") or "transfer").lower()
        exchange_inflow = bool(payload.get("exchange_inflow", to_owner == "exchange" and from_owner != "exchange"))
        exchange_outflow = bool(payload.get("exchange_outflow", from_owner == "exchange" and to_owner != "exchange"))
        stablecoin = bool(payload.get("stablecoin", symbol in STABLECOINS))
        confidence = _clamp(float(payload.get("confidence", 1.0)), 0.0, 1.0)

        if from_owner in UNKNOWN_OWNER_TYPES and to_owner in UNKNOWN_OWNER_TYPES:
            confidence = min(confidence, 0.5)

        return WhaleEvent(
            symbol=symbol,
            chain=str(payload.get("chain") or "").lower(),
            timestamp=timestamp.isoformat(),
            value_usd=max(0.0, float(payload.get("value_usd") or payload.get("amount_usd") or 0.0)),
            tx_type=tx_type,
            from_owner_type=from_owner,
            to_owner_type=to_owner,
            exchange_inflow=exchange_inflow,
            exchange_outflow=exchange_outflow,
            stablecoin=stablecoin,
            tx_hash=str(payload.get("tx_hash") or payload.get("hash") or ""),
            source=str(payload.get("source") or "unknown"),
            confidence=confidence,
        )

    def empty_summary(self, symbol: str) -> dict[str, Any]:
        return {
            "symbol": self.normalize_symbol(symbol),
            "window_seconds": settings.WHALE_WATCHER_ROLLING_WINDOW_SECONDS,
            "event_count": 0,
            "exchange_event_count": 0,
            "exchange_inflow_count": 0,
            "exchange_outflow_count": 0,
            "total_value_usd": 0.0,
            "exchange_inflow_value_usd": 0.0,
            "exchange_outflow_value_usd": 0.0,
            "stablecoin_liquidity_value_usd": 0.0,
            "max_event_value_usd": 0.0,
            "max_exchange_inflow_value_usd": 0.0,
            "max_exchange_outflow_value_usd": 0.0,
            "whale_exchange_inflow_score": 0.0,
            "whale_exchange_outflow_score": 0.0,
            "stablecoin_liquidity_score": 0.0,
            "single_leg_pressure_score": 0.0,
            "noise_penalty": 0.0,
            "last_event_ts": None,
            "recent_events": [],
        }

    def _event_weight(self, event: dict[str, Any], now: datetime) -> float:
        min_value = max(1.0, float(settings.WHALE_WATCHER_MIN_VALUE_USD))
        extreme_value = max(min_value, float(settings.WHALE_WATCHER_EXTREME_VALUE_USD))
        value = float(event.get("value_usd") or 0.0)
        if value < min_value:
            return 0.0

        event_ts = self.parse_timestamp(event.get("timestamp"))
        age_seconds = max(0.0, (now - event_ts).total_seconds())
        window_seconds = max(1.0, float(settings.WHALE_WATCHER_ROLLING_WINDOW_SECONDS))
        if age_seconds > window_seconds:
            return 0.0

        if extreme_value <= min_value:
            magnitude = 1.0
        else:
            magnitude = math.log10(value / min_value + 1.0) / math.log10(extreme_value / min_value + 1.0)

        recency = 1.0 - (age_seconds / window_seconds)
        confidence = _clamp(float(event.get("confidence") or 0.0), 0.0, 1.0)
        return _clamp(magnitude, 0.0, 1.0) * _clamp(recency, 0.0, 1.0) * confidence

    def summarize_events(
        self,
        symbol: str,
        events: Iterable[dict[str, Any]],
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        now = now or datetime.now(timezone.utc)
        summary = self.empty_summary(symbol)
        scored_events: list[tuple[float, dict[str, Any]]] = []
        inflow_weight = 0.0
        outflow_weight = 0.0
        stablecoin_weight = 0.0
        noise_weight = 0.0

        for event in events:
            weight = self._event_weight(event, now)
            if weight <= 0:
                continue

            event_ts = self.parse_timestamp(event.get("timestamp"))
            value_usd = float(event.get("value_usd") or 0.0)
            from_owner = str(event.get("from_owner_type") or "unknown").lower()
            to_owner = str(event.get("to_owner_type") or "unknown").lower()
            tx_type = str(event.get("tx_type") or "transfer").lower()
            exchange_inflow = bool(event.get("exchange_inflow"))
            exchange_outflow = bool(event.get("exchange_outflow"))
            stablecoin = bool(event.get("stablecoin"))

            summary["event_count"] += 1
            summary["total_value_usd"] += value_usd
            summary["max_event_value_usd"] = max(summary["max_event_value_usd"], value_usd)
            summary["last_event_ts"] = max(
                summary["last_event_ts"] or event_ts.isoformat(),
                event_ts.isoformat(),
            )

            if exchange_inflow:
                inflow_weight += weight
                summary["exchange_event_count"] += 1
                summary["exchange_inflow_count"] += 1
                summary["exchange_inflow_value_usd"] += value_usd
                summary["max_exchange_inflow_value_usd"] = max(summary["max_exchange_inflow_value_usd"], value_usd)
            elif exchange_outflow:
                outflow_weight += weight
                summary["exchange_event_count"] += 1
                summary["exchange_outflow_count"] += 1
                summary["exchange_outflow_value_usd"] += value_usd
                summary["max_exchange_outflow_value_usd"] = max(summary["max_exchange_outflow_value_usd"], value_usd)

            if stablecoin and tx_type in {"mint", "issuance", "transfer"} and not exchange_outflow:
                stablecoin_weight += weight
                summary["stablecoin_liquidity_value_usd"] += value_usd

            if (
                from_owner in UNKNOWN_OWNER_TYPES
                and to_owner in UNKNOWN_OWNER_TYPES
                and not exchange_inflow
                and not exchange_outflow
            ):
                noise_weight += weight

            scored_events.append((weight, event))

        summary["whale_exchange_inflow_score"] = _clamp(inflow_weight, 0.0, 1.0)
        summary["whale_exchange_outflow_score"] = _clamp(outflow_weight, 0.0, 1.0)
        summary["stablecoin_liquidity_score"] = _clamp(stablecoin_weight, 0.0, 1.0)
        summary["noise_penalty"] = _clamp(noise_weight, 0.0, 1.0)
        summary["single_leg_pressure_score"] = _clamp(
            summary["whale_exchange_outflow_score"]
            - summary["whale_exchange_inflow_score"]
            + (0.25 * summary["stablecoin_liquidity_score"])
            - (0.25 * summary["noise_penalty"]),
            -1.0,
            1.0,
        )
        summary["recent_events"] = [
            event for _, event in sorted(scored_events, key=lambda item: item[0], reverse=True)[:5]
        ]
        return summary

    async def record_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        event = self.normalize_event(payload)
        event_dict = event.to_dict()
        symbols = [event.symbol]
        if event.stablecoin:
            symbols.append(SUMMARY_SYMBOL_STABLECOIN)

        for symbol in symbols:
            key = self._events_key(symbol)
            await redis_service.client.lpush(key, json.dumps(event_dict))
            await redis_service.client.ltrim(key, 0, settings.WHALE_WATCHER_MAX_EVENTS_PER_SYMBOL - 1)
            await redis_service.client.expire(key, settings.WHALE_WATCHER_CACHE_TTL_SECONDS)

        summary = await self.refresh_summary(event.symbol)
        if event.stablecoin:
            await self.refresh_summary(SUMMARY_SYMBOL_STABLECOIN)
        return summary

    async def refresh_summary(self, symbol: str) -> dict[str, Any]:
        normalized = self.normalize_symbol(symbol)
        raw_events = await redis_service.client.lrange(
            self._events_key(normalized),
            0,
            settings.WHALE_WATCHER_MAX_EVENTS_PER_SYMBOL - 1,
        )
        events = []
        for raw_event in raw_events:
            try:
                events.append(json.loads(raw_event))
            except (TypeError, json.JSONDecodeError):
                logger.debug("WhaleWatcherService: skipped malformed cached event for %s", normalized)

        summary = self.summarize_events(normalized, events)
        await redis_service.set_json(
            self._summary_key(normalized),
            summary,
            ex=settings.WHALE_WATCHER_CACHE_TTL_SECONDS,
        )
        return summary

    async def get_cached_summary(self, symbol: str) -> dict[str, Any]:
        normalized = self.normalize_symbol(symbol)
        summary = await redis_service.get_json(self._summary_key(normalized))
        return summary if isinstance(summary, dict) else self.empty_summary(normalized)

    async def get_pair_context(self, ticker_a: str, ticker_b: str) -> dict[str, Any]:
        return await self.get_cached_pair_context(ticker_a, ticker_b)

    async def get_cached_pair_context(self, ticker_a: str, ticker_b: str) -> dict[str, Any]:
        symbol_a = self.normalize_symbol(ticker_a)
        symbol_b = self.normalize_symbol(ticker_b)
        summary_a, summary_b, stablecoin_summary = await asyncio.gather(
            self.get_cached_summary(symbol_a),
            self.get_cached_summary(symbol_b),
            self.get_cached_summary(SUMMARY_SYMBOL_STABLECOIN),
        )
        return {
            "ticker_a": ticker_a,
            "ticker_b": ticker_b,
            "summary_a": summary_a,
            "summary_b": summary_b,
            "stablecoin_summary": stablecoin_summary,
        }

    def _events_key(self, symbol: str) -> str:
        return f"{self.event_key_prefix}{self.normalize_symbol(symbol)}"

    def _summary_key(self, symbol: str) -> str:
        return f"{self.summary_key_prefix}{self.normalize_symbol(symbol)}"


whale_watcher_service = WhaleWatcherService()
