"""Venue metadata: ticker -> market session, currency, and cost model.

This is the single source of truth used by the pair-eligibility service and the
cost-aware edge filter. It is intentionally a pure-Python module (no external
state) so it can be imported from any service without circular dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class VenueProfile:
    """Static metadata about a venue (exchange).

    stamp_duty_per_side: True -> stamp duty charged on BOTH buy and sell
        (HK, SIX). False -> charged on buys only (UK SDRT, Italian FTT).
    session_group: coarser bucket for the optional EU-overlap rule. Venues
        sharing wall-clock windows can be opted into same-session via
        ``allow_eu_continental_overlap``.
    """

    market_id: str
    currency: str
    fx_fee_pct: float = 0.0
    stamp_duty_pct: float = 0.0
    stamp_duty_per_side: bool = False
    typical_spread_bps: float = 5.0
    session_group: str = ""


_SUFFIX_VENUES: Dict[str, VenueProfile] = {
    "hk": VenueProfile(market_id="HKEX", currency="HKD",
        fx_fee_pct=0.0015, stamp_duty_pct=0.0013, stamp_duty_per_side=True,
        typical_spread_bps=15.0, session_group="ASIA"),
    "l": VenueProfile(market_id="LSE", currency="GBP",
        fx_fee_pct=0.0015, stamp_duty_pct=0.005, stamp_duty_per_side=False,
        typical_spread_bps=8.0, session_group="UK"),
    "as": VenueProfile(market_id="EURONEXT", currency="EUR",
        fx_fee_pct=0.0015, stamp_duty_pct=0.0,
        typical_spread_bps=5.0, session_group="EU_CONTINENTAL"),
    "pa": VenueProfile(market_id="EURONEXT", currency="EUR",
        fx_fee_pct=0.0015, stamp_duty_pct=0.0,
        typical_spread_bps=5.0, session_group="EU_CONTINENTAL"),
    "br": VenueProfile(market_id="EURONEXT", currency="EUR",
        fx_fee_pct=0.0015, stamp_duty_pct=0.0,
        typical_spread_bps=8.0, session_group="EU_CONTINENTAL"),
    "ls": VenueProfile(market_id="EURONEXT", currency="EUR",
        fx_fee_pct=0.0015, stamp_duty_pct=0.0,
        typical_spread_bps=10.0, session_group="EU_CONTINENTAL"),
    "de": VenueProfile(market_id="XETRA", currency="EUR",
        fx_fee_pct=0.0015, stamp_duty_pct=0.0,
        typical_spread_bps=5.0, session_group="EU_CONTINENTAL"),
    "mi": VenueProfile(market_id="BORSA_ITALIANA", currency="EUR",
        fx_fee_pct=0.0015, stamp_duty_pct=0.001, stamp_duty_per_side=False,
        typical_spread_bps=8.0, session_group="EU_CONTINENTAL"),
    "sw": VenueProfile(market_id="SIX", currency="CHF",
        fx_fee_pct=0.0015, stamp_duty_pct=0.00075, stamp_duty_per_side=True,
        typical_spread_bps=8.0, session_group="EU_CONTINENTAL"),
    "co": VenueProfile(market_id="NASDAQ_COPENHAGEN", currency="DKK",
        fx_fee_pct=0.0015, stamp_duty_pct=0.0,
        typical_spread_bps=10.0, session_group="NORDIC"),
    "st": VenueProfile(market_id="NASDAQ_STOCKHOLM", currency="SEK",
        fx_fee_pct=0.0015, stamp_duty_pct=0.0,
        typical_spread_bps=10.0, session_group="NORDIC"),
    "to": VenueProfile(market_id="TSX", currency="CAD",
        fx_fee_pct=0.0015, stamp_duty_pct=0.0,
        typical_spread_bps=8.0, session_group="NORTH_AMERICA"),
    "t": VenueProfile(market_id="TSE", currency="JPY",
        fx_fee_pct=0.0015, stamp_duty_pct=0.0,
        typical_spread_bps=10.0, session_group="ASIA"),
}

_US_VENUE = VenueProfile(market_id="US_EQUITY", currency="USD",
    fx_fee_pct=0.0015, stamp_duty_pct=0.0,
    typical_spread_bps=3.0, session_group="NORTH_AMERICA")

_CRYPTO_VENUE = VenueProfile(market_id="CRYPTO_24_7", currency="USD",
    fx_fee_pct=0.0, stamp_duty_pct=0.0,
    typical_spread_bps=10.0, session_group="CRYPTO")


def get_venue_profile(ticker: str) -> VenueProfile:
    t = ticker.strip().upper()
    if "-USD" in t:
        return _CRYPTO_VENUE
    if "." in t:
        suffix = t.rsplit(".", 1)[1].lower()
        venue = _SUFFIX_VENUES.get(suffix)
        if venue is not None:
            return venue
    return _US_VENUE


def same_session(ticker_a: str, ticker_b: str, *,
                 allow_eu_continental_overlap: bool = False) -> bool:
    """Return True iff both tickers trade in the same session window.

    Default: strict market_id match. With ``allow_eu_continental_overlap``,
    venues in the EU_CONTINENTAL session group (XETRA, EURONEXT, SIX,
    BORSA_ITALIANA) are treated as the same session because their wall-clock
    windows overlap by ~7-8 hours.
    """
    v_a = get_venue_profile(ticker_a)
    v_b = get_venue_profile(ticker_b)
    if v_a.market_id == v_b.market_id:
        return True
    if allow_eu_continental_overlap:
        return (v_a.session_group != ""
                and v_a.session_group == v_b.session_group
                and v_a.session_group == "EU_CONTINENTAL")
    return False


def same_currency(ticker_a: str, ticker_b: str) -> bool:
    return get_venue_profile(ticker_a).currency == get_venue_profile(ticker_b).currency


def estimate_round_trip_cost_pct(ticker_a: str, ticker_b: str,
                                 account_currency: str = "EUR") -> float:
    """Combined round-trip cost (entry + exit) for a pair, as a fraction.

    Per leg:
      - FX fee x 2 (entry + exit) if currency != account_currency.
      - Stamp duty x 1 if buy-only (UK, Italian); x 2 if per-side (HK, SIX).
      - Typical spread once per leg.
    """
    total = 0.0
    for ticker in (ticker_a, ticker_b):
        v = get_venue_profile(ticker)
        leg_cost = 0.0
        if v.currency != account_currency:
            leg_cost += 2.0 * v.fx_fee_pct
        stamp_multiplier = 2.0 if v.stamp_duty_per_side else 1.0
        leg_cost += stamp_multiplier * v.stamp_duty_pct
        leg_cost += v.typical_spread_bps / 10000.0
        total += leg_cost
    return total


__all__ = ["VenueProfile", "get_venue_profile", "same_session",
           "same_currency", "estimate_round_trip_cost_pct"]
