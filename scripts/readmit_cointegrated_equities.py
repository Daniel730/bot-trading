#!/usr/bin/env python3
"""Re-admit cointegrated equity pairs into Active slots (ops / paper activity).

Runs inside the bot container (or with PYTHONPATH + DB env). Does NOT soft-admit:
pairs must pass static ADF + rolling cointegration at the current settings thresholds.
Respects denylist, hedge sanity, and shared-leg occupancy.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("readmit_equities")


async def _list_pairs_by_status(status: str | None = None) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from src.services.persistence_service import TradingPair, persistence_service

    async with persistence_service.AsyncSessionLocal() as session:
        stmt = select(TradingPair)
        if status is not None:
            stmt = stmt.where(TradingPair.status == status)
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "id": p.id,
                "ticker_a": p.ticker_a,
                "ticker_b": p.ticker_b,
                "hedge_ratio": float(p.hedge_ratio or 0.0),
                "is_cointegrated": bool(p.is_cointegrated),
                "status": p.status,
            }
            for p in rows
        ]


async def _evaluate_equity(
    ticker_a: str,
    ticker_b: str,
    *,
    hist_cache: dict[str, Any],
) -> dict[str, Any] | None:
    from src.config import settings
    from src.monitor_helpers import is_crypto_pair
    from src.services.arbitrage_service import ArbitrageService
    from src.services.data_service import data_service
    from src.services.pair_discovery_helpers import is_hedge_ratio_sane, max_abs_hedge_limit
    from src.services.pair_eligibility_service import evaluate_pair

    if is_crypto_pair(ticker_a, ticker_b):
        return None

    eligibility = await evaluate_pair(ticker_a, ticker_b)
    if not eligibility.admit:
        return {"ok": False, "reason": f"eligibility:{eligibility.reason}"}

    needed = [t for t in (ticker_a, ticker_b) if t not in hist_cache]
    if needed:
        try:
            batch = await asyncio.to_thread(
                data_service.get_historical_data,
                needed,
                period="30d",
                interval="1h",
            )
            if batch is not None and not getattr(batch, "empty", True):
                for col in batch.columns:
                    hist_cache[str(col)] = batch[col]
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "reason": f"history_error:{type(exc).__name__}"}

    if ticker_a not in hist_cache or ticker_b not in hist_cache:
        return {"ok": False, "reason": "missing_history"}

    series_a = hist_cache[ticker_a].dropna()
    series_b = hist_cache[ticker_b].dropna()
    if len(series_a) < 40 or len(series_b) < 40:
        return {"ok": False, "reason": "short_history"}

    p_thresh = float(settings.COINTEGRATION_PVALUE_THRESHOLD)
    pass_thresh = float(settings.COINTEGRATION_ROLLING_PASS_RATE)
    arb = ArbitrageService()
    is_coint, p_val, hedge = arb.check_cointegration(
        series_a, series_b, pvalue_threshold=p_thresh
    )
    if not is_coint:
        return {"ok": False, "reason": f"static_adf_p={p_val:.4f}", "p_value": float(p_val)}

    if settings.COINTEGRATION_ROLLING_ENABLED:
        stability = ArbitrageService.check_rolling_cointegration(
            series_a,
            series_b,
            window=settings.COINTEGRATION_ROLLING_WINDOW,
            step=settings.COINTEGRATION_ROLLING_STEP,
            min_pass_rate=pass_thresh,
            pvalue_threshold=p_thresh,
        )
        if not stability.get("stable"):
            return {
                "ok": False,
                "reason": (
                    f"rolling_pass={stability.get('pass_rate', 0):.2f}"
                    f"<={pass_thresh:.2f}"
                ),
                "p_value": float(p_val),
                "pass_rate": float(stability.get("pass_rate") or 0.0),
            }

    hedge_f = float(hedge)
    if not is_hedge_ratio_sane(hedge_f, max_abs_hedge=max_abs_hedge_limit(ticker_a, ticker_b)):
        return {"ok": False, "reason": f"insane_hedge={hedge_f:.4f}", "hedge": hedge_f}

    return {
        "ok": True,
        "p_value": float(p_val),
        "hedge_ratio": hedge_f,
        "pass_rate": float(pass_thresh),
    }


async def main() -> int:
    from src.config import settings
    from src.monitor_helpers import is_crypto_pair
    from src.services.pair_discovery_helpers import (
        is_pair_denied,
        normalize_denylist,
        occupied_tickers_from_pairs,
    )
    from src.services.persistence_service import persistence_service
    from src.services.portfolio_book_guards import canonical_book_symbol

    max_active = int(settings.MAX_ACTIVE_PAIRS)
    denylist = normalize_denylist(getattr(settings, "PAIR_DENYLIST", None))

    active = await _list_pairs_by_status("Active")
    benched = await _list_pairs_by_status("Benched")
    logger.info(
        "start active=%d benched=%d max_active=%d pass_rate=%.2f entry_z=%.2f",
        len(active),
        len(benched),
        max_active,
        float(settings.COINTEGRATION_ROLLING_PASS_RATE),
        float(settings.MONITOR_ENTRY_ZSCORE),
    )

    # Prefer overnight known-good equities first, then remaining ARBITRAGE_PAIRS.
    preferred = [
        ("GOOGL", "GOOG"),
        ("UNH", "ELV"),
        ("VLO", "MPC"),
        ("KO", "PEP"),
        ("MA", "V"),
        ("XOM", "CVX"),
        ("JPM", "BAC"),
        ("MSFT", "AAPL"),
        ("HD", "LOW"),
        ("PG", "CL"),
    ]
    configured = [
        (str(p["ticker_a"]), str(p["ticker_b"]))
        for p in (settings.ARBITRAGE_PAIRS or [])
        if isinstance(p, dict)
    ]
    seen_keys: set[frozenset[str]] = set()
    candidates: list[tuple[str, str]] = []
    for a, b in [*preferred, *configured]:
        if is_crypto_pair(a, b):
            continue
        key = frozenset((a.upper(), b.upper()))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        candidates.append((a, b))

    occupied = occupied_tickers_from_pairs(active, id_key="id")
    open_slots = max(0, max_active - len(active))
    if open_slots <= 0:
        logger.info("no open Active slots (active=%d max=%d)", len(active), max_active)
        return 0

    hist_cache: dict[str, Any] = {}
    promote_payloads: list[dict[str, Any]] = []
    rejected = 0

    for ticker_a, ticker_b in candidates:
        if len(promote_payloads) >= open_slots:
            break
        pair_id = f"{ticker_a}_{ticker_b}"
        if is_pair_denied(pair_id=pair_id, denylist=denylist):
            rejected += 1
            continue
        canon_a = canonical_book_symbol(ticker_a)
        canon_b = canonical_book_symbol(ticker_b)
        if canon_a in occupied or canon_b in occupied:
            continue
        # Skip if already Active
        if any(p["id"] == pair_id or p["id"] == f"{ticker_b}_{ticker_a}" for p in active):
            continue

        verdict = await _evaluate_equity(ticker_a, ticker_b, hist_cache=hist_cache)
        if not verdict or not verdict.get("ok"):
            rejected += 1
            logger.info(
                "reject %s/%s: %s",
                ticker_a,
                ticker_b,
                (verdict or {}).get("reason", "no_verdict"),
            )
            continue

        payload = {
            "id": pair_id,
            "ticker_a": ticker_a,
            "ticker_b": ticker_b,
            "hedge_ratio": float(verdict["hedge_ratio"]),
            "is_cointegrated": True,
            "status": "Active",
        }
        promote_payloads.append(payload)
        occupied |= {canon_a, canon_b}
        logger.info(
            "promote %s/%s p=%.4f hedge=%.4f",
            ticker_a,
            ticker_b,
            float(verdict["p_value"]),
            float(verdict["hedge_ratio"]),
        )

    if promote_payloads:
        await persistence_service.save_trading_pairs(promote_payloads)
        logger.info("saved %d Active promotions", len(promote_payloads))
    else:
        logger.warning("no equities passed cointegration at current thresholds")

    active_after = await _list_pairs_by_status("Active")
    equity = [
        p
        for p in active_after
        if not is_crypto_pair(p["ticker_a"], p["ticker_b"])
    ]
    crypto = [
        p
        for p in active_after
        if is_crypto_pair(p["ticker_a"], p["ticker_b"])
    ]
    logger.info(
        "done active=%d equity=%d crypto=%d promoted=%d rejected=%d",
        len(active_after),
        len(equity),
        len(crypto),
        len(promote_payloads),
        rejected,
    )
    for p in equity:
        logger.info("  equity Active %s/%s", p["ticker_a"], p["ticker_b"])
    for p in crypto:
        logger.info("  crypto Active %s/%s", p["ticker_a"], p["ticker_b"])
    return 0 if promote_payloads or equity else 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130)
