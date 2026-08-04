"""News Risk agent — veto-only overlay for pair entries.

Maps recent headlines onto the active universe and can veto (or shrink
confidence) when material shock language hits either leg. This is NOT
directional news trading / alpha prediction.

Fail semantics (documented for operators):
- ``NEWS_RISK_ENABLED=false`` (default) → inactive, no veto, trading continues.
- Missing feed URLs / API key / empty provider → inactive, no veto (do not
  block the book when news ingest is unavailable).
- Parse / network errors → active=False, veto=False, warning in reasoning.
- Veto applies only when ``active=True`` AND ``veto=True`` (high materiality,
  ticker-relevant, within TTL).
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

from src.config import settings
from src.services.news_feed import NewsFeed, NewsHeadline, build_news_feed
from src.services.redis_service import redis_service

logger = logging.getLogger(__name__)

# Common company-name → ticker aliases for the curated US universe.
# Exact ticker tokens (word-boundary) are always matched in addition.
TICKER_ALIASES: dict[str, str] = {
    "coca-cola": "KO",
    "coca cola": "KO",
    "coke": "KO",
    "pepsi": "PEP",
    "pepsico": "PEP",
    "mastercard": "MA",
    "visa": "V",
    "exxon": "XOM",
    "exxonmobil": "XOM",
    "exxon mobil": "XOM",
    "chevron": "CVX",
    "jpmorgan": "JPM",
    "jp morgan": "JPM",
    "jp morgan chase": "JPM",
    "bank of america": "BAC",
    "walmart": "WMT",
    "target": "TGT",
    "alphabet": "GOOGL",
    "google": "GOOGL",
    "microsoft": "MSFT",
    "apple": "AAPL",
    "delta air": "DAL",
    "delta airlines": "DAL",
    "united airlines": "UAL",
    "ups": "UPS",
    "fedex": "FDX",
    "home depot": "HD",
    "lowe's": "LOW",
    "lowes": "LOW",
    "general motors": "GM",
    "ford": "F",
    "intel": "INTC",
    "amd": "AMD",
    "advanced micro devices": "AMD",
    "paypal": "PYPL",
    "affirm": "AFRM",
    "procter & gamble": "PG",
    "procter and gamble": "PG",
    "colgate": "CL",
    "at&t": "T",
    "verizon": "VZ",
    "nvidia": "NVDA",
    "tesla": "TSLA",
    "rivian": "RIVN",
    "coinbase": "COIN",
    "microstrategy": "MSTR",
    "strategy": "MSTR",
    "meta": "META",
    "facebook": "META",
    "snap": "SNAP",
    "snapchat": "SNAP",
    "netflix": "NFLX",
    "disney": "DIS",
    "uber": "UBER",
    "lyft": "LYFT",
    "starbucks": "SBUX",
    "mcdonald": "MCD",
    "mcdonald's": "MCD",
    "amazon": "AMZN",
    "shopify": "SHOP",
    "palantir": "PLTR",
    "berkshire": "BRK-B",
    "costco": "COST",
    "nike": "NKE",
    "pfizer": "PFE",
    "merck": "MRK",
    "johnson & johnson": "JNJ",
    "abbvie": "ABBV",
    "bitcoin": "BTC-USD",
    "ethereum": "ETH-USD",
}

# Keyword severity: materiality in [0, 1]. High-severity terms alone can veto.
SEVERITY_KEYWORDS: dict[str, float] = {
    "bankruptcy": 1.0,
    "chapter 11": 1.0,
    "chapter 7": 1.0,
    "fraud": 0.95,
    "sec charges": 0.95,
    "criminal charges": 0.95,
    "indictment": 0.95,
    "going concern": 0.9,
    "delisting": 0.9,
    "halted": 0.85,
    "trading halt": 0.85,
    "suspended trading": 0.85,
    "accounting scandal": 0.95,
    "restatement": 0.8,
    "downgrade": 0.55,
    "misses estimates": 0.6,
    "missed estimates": 0.6,
    "earnings miss": 0.65,
    "profit warning": 0.75,
    "guidance cut": 0.7,
    "cuts guidance": 0.7,
    "slashes guidance": 0.75,
    "lawsuit": 0.55,
    "class action": 0.65,
    "antitrust": 0.6,
    "probe": 0.55,
    "investigation": 0.55,
    "subpoena": 0.7,
    "recall": 0.6,
    "cyberattack": 0.7,
    "data breach": 0.65,
    "ransomware": 0.7,
    "ceo resigns": 0.7,
    "ceo steps down": 0.7,
    "cfo resigns": 0.65,
    "merger collapsed": 0.8,
    "deal collapses": 0.8,
    "acquisition blocked": 0.75,
    "fda rejection": 0.85,
    "clinical trial failure": 0.85,
    "defaults on": 0.9,
    "debt default": 0.9,
    "liquidity crisis": 0.85,
    "mass layoff": 0.5,
    "restructuring": 0.45,
    # Positive shocks can also break mean-reversion assumptions.
    "takeover bid": 0.8,
    "buyout": 0.75,
    "acquisition of": 0.7,
    "acquires": 0.65,
    "all-cash offer": 0.8,
    "tender offer": 0.75,
    "beats estimates by": 0.55,
    "surge after": 0.5,
    "soars on": 0.55,
    "plunges": 0.7,
    "crashes": 0.75,
    "tumbles": 0.6,
}

_REDIS_HEADLINES_KEY = "news:risk:headlines"


def map_headline_tickers(text: str, *, aliases: Optional[dict[str, str]] = None) -> set[str]:
    """Return tickers mentioned via alias phrases or exact ticker tokens."""
    alias_map = aliases if aliases is not None else TICKER_ALIASES
    lowered = (text or "").lower()
    found: set[str] = set()
    # Longer aliases first so "bank of america" wins over partials.
    for alias, ticker in sorted(alias_map.items(), key=lambda kv: len(kv[0]), reverse=True):
        if alias in lowered:
            found.add(ticker.upper())
    # Exact ticker tokens from curated universe + common crypto.
    for ticker in _universe_tickers():
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(ticker)}(?![A-Za-z0-9])", text or "", re.I):
            found.add(ticker.upper())
    return found


def score_headline_materiality(text: str) -> tuple[float, list[str]]:
    """Heuristic polarity/materiality score in [0, 1] from keyword severity."""
    lowered = (text or "").lower()
    hits: list[str] = []
    score = 0.0
    for phrase, weight in SEVERITY_KEYWORDS.items():
        if phrase in lowered:
            hits.append(phrase)
            score = max(score, float(weight))
    return score, hits


def _universe_tickers() -> set[str]:
    tickers: set[str] = set()
    for pair in list(getattr(settings, "ARBITRAGE_PAIRS", []) or []) + list(
        getattr(settings, "CRYPTO_TEST_PAIRS", []) or []
    ):
        if not isinstance(pair, dict):
            continue
        for key in ("ticker_a", "ticker_b"):
            t = str(pair.get(key) or "").strip().upper()
            if t:
                tickers.add(t)
    # Always include alias targets so mapping works even if pairs overridden empty.
    tickers.update(t.upper() for t in TICKER_ALIASES.values())
    return tickers


def _news_effects_apply(verdict: dict | None) -> bool:
    if not isinstance(verdict, dict):
        return False
    if verdict.get("status") == "inactive" or verdict.get("active") is False:
        return False
    return verdict.get("active") is True


class NewsRiskAgent:
    """Veto-only news risk overlay (opt-in via ``NEWS_RISK_ENABLED``)."""

    def __init__(self, feed: Optional[NewsFeed] = None):
        self._feed = feed

    @property
    def feed(self) -> NewsFeed:
        if self._feed is None:
            self._feed = build_news_feed()
        return self._feed

    def inactive(self, reasoning: str, *, warning: Optional[str] = None) -> dict:
        payload = {
            "active": False,
            "status": "inactive",
            "veto": False,
            "confidence_multiplier": 1.0,
            "materiality": 0.0,
            "matched_tickers": [],
            "matched_headlines": [],
            "warning": warning,
            "reasoning": reasoning,
            "enabled_flag": bool(getattr(settings, "NEWS_RISK_ENABLED", False)),
        }
        return payload

    def status(self) -> dict:
        return {
            "active": bool(getattr(settings, "NEWS_RISK_ENABLED", False)),
            "enabled_flag": bool(getattr(settings, "NEWS_RISK_ENABLED", False)),
            "provider": getattr(settings, "NEWS_RISK_PROVIDER", "rss"),
            "ttl_seconds": int(getattr(settings, "NEWS_RISK_TTL_SECONDS", 7200)),
            "veto_score": float(getattr(settings, "NEWS_RISK_VETO_SCORE", 0.75)),
            "llm_enabled": bool(getattr(settings, "NEWS_RISK_LLM_ENABLED", False)),
        }

    async def _load_headlines(self) -> tuple[list[NewsHeadline], Optional[str]]:
        """Return headlines and optional warning. Prefer Redis cache."""
        cache_ttl = int(getattr(settings, "NEWS_RISK_CACHE_SECONDS", 300) or 300)
        try:
            cached = await redis_service.get_json(_REDIS_HEADLINES_KEY)
            if isinstance(cached, list) and cached:
                return [_headline_from_cache(item) for item in cached if item], None
        except Exception as exc:
            logger.debug("News Redis cache read failed: %s", exc)

        try:
            headlines = await self.feed.fetch(
                limit=int(getattr(settings, "NEWS_RISK_MAX_HEADLINES", 50) or 50)
            )
        except Exception as exc:
            logger.warning("News feed fetch failed: %s", exc)
            return [], f"feed error: {exc}"

        serializable = [_headline_to_cache(h) for h in headlines]
        try:
            if serializable:
                await redis_service.set_json(
                    _REDIS_HEADLINES_KEY, serializable, ex=max(30, cache_ttl)
                )
        except Exception as exc:
            logger.debug("News Redis cache write failed: %s", exc)
        return headlines, None

    async def evaluate(self, signal_context: dict) -> dict:
        if not bool(getattr(settings, "NEWS_RISK_ENABLED", False)):
            return self.inactive(
                "News risk overlay disabled (NEWS_RISK_ENABLED=false). No veto."
            )

        ticker_a = str((signal_context or {}).get("ticker_a") or "").upper()
        ticker_b = str((signal_context or {}).get("ticker_b") or "").upper()
        if not ticker_a or not ticker_b:
            return self.inactive("News risk skipped: missing ticker_a/ticker_b.")

        headlines, warning = await self._load_headlines()
        if not headlines:
            # Feed unavailable / empty → do not block trading.
            return self.inactive(
                "News feed unavailable or empty; inactive no-veto (trading continues).",
                warning=warning or "empty_or_unavailable_feed",
            )

        ttl = int(getattr(settings, "NEWS_RISK_TTL_SECONDS", 7200) or 7200)
        veto_threshold = float(getattr(settings, "NEWS_RISK_VETO_SCORE", 0.75) or 0.75)
        shrink_threshold = float(
            getattr(settings, "NEWS_RISK_SHRINK_SCORE", 0.55) or 0.55
        )
        shrink_multiplier = float(
            getattr(settings, "NEWS_RISK_CONFIDENCE_MULTIPLIER", 0.85) or 0.85
        )
        now = time.time()
        use_llm = bool(getattr(settings, "NEWS_RISK_LLM_ENABLED", False))

        best_materiality = 0.0
        best_hits: list[str] = []
        matched_tickers: set[str] = set()
        matched_headlines: list[dict] = []

        for headline in headlines:
            published = headline.published_at
            if published is not None and (now - float(published)) > ttl:
                continue
            # Unknown publish time: still consider (fresh cache window covers it).

            text = headline.text
            tickers = set(t.upper() for t in headline.tickers) | map_headline_tickers(text)
            relevant = {ticker_a, ticker_b} & tickers
            if not relevant:
                continue

            materiality, hits = score_headline_materiality(text)
            if use_llm and materiality < veto_threshold:
                # Optional LLM path reserved; default false — heuristic only for MVP.
                materiality = max(materiality, await self._optional_llm_score(text))

            if materiality <= 0.0:
                continue

            matched_tickers |= relevant
            matched_headlines.append(
                {
                    "title": headline.title[:200],
                    "tickers": sorted(relevant),
                    "materiality": materiality,
                    "hits": hits,
                    "published_at": published,
                }
            )
            if materiality > best_materiality:
                best_materiality = materiality
                best_hits = hits

        if not matched_headlines:
            return {
                "active": True,
                "status": "active",
                "veto": False,
                "confidence_multiplier": 1.0,
                "materiality": 0.0,
                "matched_tickers": [],
                "matched_headlines": [],
                "warning": warning,
                "reasoning": (
                    f"News risk active: no material headlines for {ticker_a}/{ticker_b} "
                    f"within TTL={ttl}s."
                ),
                "enabled_flag": True,
            }

        veto = best_materiality >= veto_threshold
        multiplier = 1.0
        if not veto and best_materiality >= shrink_threshold:
            multiplier = max(0.0, min(1.0, shrink_multiplier))

        reasoning = (
            f"NEWS RISK: materiality={best_materiality:.2f} "
            f"(threshold={veto_threshold:.2f}) hits={best_hits or ['n/a']} "
            f"tickers={sorted(matched_tickers)}"
        )
        if veto:
            reasoning = f"VETO: {reasoning}"

        return {
            "active": True,
            "status": "active",
            "veto": veto,
            "confidence_multiplier": multiplier if not veto else 0.0,
            "materiality": best_materiality,
            "matched_tickers": sorted(matched_tickers),
            "matched_headlines": matched_headlines[:5],
            "warning": warning,
            "reasoning": reasoning,
            "enabled_flag": True,
        }

    async def _optional_llm_score(self, text: str) -> float:
        """Reserved LLM scoring path. Disabled unless NEWS_RISK_LLM_ENABLED.

        MVP returns 0.0 so heuristic keywords remain the only scoring path when
        the flag is flipped without a wired model client.
        """
        if not bool(getattr(settings, "NEWS_RISK_LLM_ENABLED", False)):
            return 0.0
        logger.debug("NEWS_RISK_LLM_ENABLED set but LLM scorer not wired; heuristic only")
        return 0.0


def _headline_to_cache(h: NewsHeadline) -> dict:
    return {
        "title": h.title,
        "summary": h.summary,
        "published_at": h.published_at,
        "source": h.source,
        "url": h.url,
        "tickers": list(h.tickers),
    }


def _headline_from_cache(item: dict) -> NewsHeadline:
    return NewsHeadline(
        title=str(item.get("title") or ""),
        summary=str(item.get("summary") or ""),
        published_at=float(item["published_at"]) if item.get("published_at") is not None else None,
        source=str(item.get("source") or ""),
        url=str(item.get("url") or ""),
        tickers=tuple(str(t).upper() for t in (item.get("tickers") or [])),
    )


news_risk_agent = NewsRiskAgent()

# Re-export for orchestrator tests.
news_effects_apply = _news_effects_apply
