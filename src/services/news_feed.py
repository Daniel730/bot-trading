"""Pluggable news ingest for the News Risk veto overlay.

Providers (selected by ``NEWS_RISK_PROVIDER``):
- ``rss`` — fetch configurable RSS/Atom URLs (default; works without paid keys)
- ``file`` — load headlines from a local JSON/NDJSON file (ops/testing)
- ``stub`` — empty feed (explicit no-op)
- ``polygon`` — Polygon ticker news when ``POLYGON_API_KEY`` is usable

Missing/unusable keys or parse errors must not block trading — callers treat
an empty/unavailable feed as inactive no-veto.
"""

from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen

from src.config import settings

logger = logging.getLogger(__name__)

_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


@dataclass(frozen=True)
class NewsHeadline:
    title: str
    summary: str = ""
    published_at: Optional[float] = None  # unix seconds UTC
    source: str = ""
    url: str = ""
    tickers: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        return f"{self.title} {self.summary}".strip()


class NewsFeed(ABC):
    """Fetch recent headlines. Implementations must be side-effect light."""

    name: str = "base"

    @abstractmethod
    async def fetch(self, *, limit: int = 50) -> list[NewsHeadline]:
        raise NotImplementedError


class StubNewsFeed(NewsFeed):
    name = "stub"

    async def fetch(self, *, limit: int = 50) -> list[NewsHeadline]:
        return []


class FileNewsFeed(NewsFeed):
    """Load headlines from JSON list or NDJSON at ``NEWS_RISK_FEED_FILE``."""

    name = "file"

    def __init__(self, path: Optional[str] = None):
        self.path = Path(path or getattr(settings, "NEWS_RISK_FEED_FILE", "") or "")

    async def fetch(self, *, limit: int = 50) -> list[NewsHeadline]:
        if not self.path or not self.path.is_file():
            logger.warning("News feed file missing or unset: %s", self.path)
            return []
        try:
            raw = self.path.read_text(encoding="utf-8").strip()
            if not raw:
                return []
            if raw.startswith("["):
                payload = json.loads(raw)
            else:
                payload = [json.loads(line) for line in raw.splitlines() if line.strip()]
            out: list[NewsHeadline] = []
            for item in payload[:limit]:
                if not isinstance(item, dict):
                    continue
                tickers = item.get("tickers") or []
                if isinstance(tickers, str):
                    tickers = [t.strip() for t in tickers.split(",") if t.strip()]
                published = item.get("published_at")
                if isinstance(published, str):
                    published = _parse_datetime(published)
                out.append(
                    NewsHeadline(
                        title=str(item.get("title") or ""),
                        summary=str(item.get("summary") or item.get("description") or ""),
                        published_at=float(published) if published else None,
                        source=str(item.get("source") or "file"),
                        url=str(item.get("url") or ""),
                        tickers=tuple(str(t).upper() for t in tickers),
                    )
                )
            return [h for h in out if h.title]
        except Exception as exc:
            logger.warning("Failed to parse news feed file %s: %s", self.path, exc)
            return []


class RssNewsFeed(NewsFeed):
    """Fetch and parse RSS/Atom from comma-separated ``NEWS_RISK_FEED_URLS``."""

    name = "rss"

    def __init__(self, urls: Optional[list[str]] = None):
        if urls is None:
            urls = _split_urls(getattr(settings, "NEWS_RISK_FEED_URLS", "") or "")
        self.urls = urls

    async def fetch(self, *, limit: int = 50) -> list[NewsHeadline]:
        if not self.urls:
            logger.debug("NEWS_RISK_FEED_URLS empty — RSS feed inactive")
            return []
        headlines: list[NewsHeadline] = []
        for url in self.urls:
            try:
                headlines.extend(_fetch_rss_url(url, limit=limit))
            except Exception as exc:
                logger.warning("RSS fetch/parse failed for %s: %s", url, exc)
        headlines.sort(key=lambda h: h.published_at or 0.0, reverse=True)
        return headlines[:limit]


class PolygonNewsFeed(NewsFeed):
    """Polygon reference news when a usable API key is configured."""

    name = "polygon"

    async def fetch(self, *, limit: int = 50) -> list[NewsHeadline]:
        api_key = (getattr(settings, "POLYGON_API_KEY", "") or "").strip()
        if not api_key or api_key.lower().startswith("your_"):
            logger.info("Polygon news skipped: POLYGON_API_KEY missing/placeholder")
            return []
        try:
            from polygon import RESTClient

            client = RESTClient(api_key=api_key)
            items = list(client.list_ticker_news(limit=min(limit, 50)))
            out: list[NewsHeadline] = []
            for item in items:
                title = getattr(item, "title", None) or ""
                summary = getattr(item, "description", None) or ""
                published = getattr(item, "published_utc", None)
                ts = _parse_datetime(published) if published else None
                tickers = tuple(
                    str(t).upper() for t in (getattr(item, "tickers", None) or [])
                )
                out.append(
                    NewsHeadline(
                        title=str(title),
                        summary=str(summary),
                        published_at=ts,
                        source="polygon",
                        url=str(getattr(item, "article_url", None) or ""),
                        tickers=tickers,
                    )
                )
            return [h for h in out if h.title][:limit]
        except Exception as exc:
            logger.warning("Polygon news fetch failed: %s", exc)
            return []


def build_news_feed(provider: Optional[str] = None) -> NewsFeed:
    name = (provider or getattr(settings, "NEWS_RISK_PROVIDER", "rss") or "rss").strip().lower()
    if name == "stub":
        return StubNewsFeed()
    if name == "file":
        return FileNewsFeed()
    if name == "polygon":
        return PolygonNewsFeed()
    if name == "rss":
        return RssNewsFeed()
    logger.warning("Unknown NEWS_RISK_PROVIDER=%s; using stub", name)
    return StubNewsFeed()


def _split_urls(raw: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,;\s]+", raw) if part.strip()]


def _parse_datetime(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return parsedate_to_datetime(text).timestamp()
    except (TypeError, ValueError, IndexError, OverflowError):
        pass
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _fetch_rss_url(url: str, *, limit: int) -> list[NewsHeadline]:
    req = Request(
        url,
        headers={"User-Agent": "AlphaArbitrageNewsRisk/1.0 (+https://github.com/local)"},
    )
    with urlopen(req, timeout=8) as resp:
        body = resp.read()
    root = ET.fromstring(body)
    root_tag = _local(root.tag).lower()
    items: list[NewsHeadline] = []

    if root_tag == "feed" or root.find("atom:entry", _ATOM_NS) is not None:
        entries = root.findall("atom:entry", _ATOM_NS) or [
            el for el in root if _local(el.tag).lower() == "entry"
        ]
        for entry in entries[:limit]:
            title = _child_text(entry, "title")
            summary = _child_text(entry, "summary") or _child_text(entry, "content")
            published = _parse_datetime(
                _child_text(entry, "published") or _child_text(entry, "updated")
            )
            link = ""
            for link_el in entry:
                if _local(link_el.tag).lower() == "link":
                    link = link_el.attrib.get("href") or (link_el.text or "")
                    if link:
                        break
            if title:
                items.append(
                    NewsHeadline(
                        title=title,
                        summary=summary,
                        published_at=published,
                        source=url,
                        url=link,
                    )
                )
        return items

    channel = root.find("channel")
    item_nodes = channel.findall("item") if channel is not None else root.findall(".//item")
    for item in item_nodes[:limit]:
        title = _child_text(item, "title")
        summary = _child_text(item, "description")
        published = _parse_datetime(_child_text(item, "pubDate"))
        link = _child_text(item, "link")
        if title:
            items.append(
                NewsHeadline(
                    title=title,
                    summary=summary,
                    published_at=published,
                    source=url,
                    url=link,
                )
            )
    return items


def _child_text(parent: ET.Element, name: str) -> str:
    for child in parent:
        if _local(child.tag).lower() == name.lower():
            return (child.text or "").strip()
    # namespaced fallback
    for child in parent:
        if _local(child.tag).lower() == name.lower():
            return (child.text or "").strip()
    return ""
