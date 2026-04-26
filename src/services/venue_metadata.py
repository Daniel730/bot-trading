"""Venue metadata: ticker -> market session, currency, and cost model.

This is the single source of truth used by the pair-eligibility service and the
cost-aware edge filter. It is intentionally a pure-Python module (no external
state) so it can be imported from any service without circular dependencies.

A ticker's "session" is the trading window during which its native exchange
publishes prices. Two tickers with different sessions cannot form a Kalman
pairs-trading pair: the spread would be evaluated against stale prices on one
leg, breaking the cointegration premise.

A ticker's "currency" is the settlement currency on the user's broker. Pairing
two assets in different currencies turns FX moves into a hidden second factor
that the Kalman filter cannot decouple from the alpha signal.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class VenueProfile:
    """Static metadata about a venue (exchange).

    fx_fee_pct: round-trip currency conversion fee charged by the broker when
        the user's account is denominated in a different currency than this
        venue. Trading 212's documented retail fee is 0.15 % per conversion.
    stamp_duty_pct: government stamp duty levied at purchase. UK LSE charges
        0.5 % on most stocks (AIM exempt, ETFs exempt). Most other venues
        charge zero.
    typical_spread_bps: realistic round-trip spread the bot should assume even
        when L1 quotes look tight. Used as a floor in the cost model.
    market_id: human-readable session id used to gate pair eligibility.
        Two tickers must share the same market_id to be paired.
    """

    market_id: str
    currency: str
    fx_fee_pct: float = 0.0
    stamp_duty_pct: float = 0.0
    typical_spread_bps: float = 5.0  # 5 bps = 0.05% baseline


# --- Suffix-driven venue rules (Yahoo Finance / Trading 212 conventions) ---
# Keys are ticker suffixes (lower-cased without dot prefix). Order matters
# only for documentation; lookup is exact-match.
_SUFFIX_VENUES: Dict[str, VenueProfile] = {
    "hk": VenueProfile(
        market_id="HKEX",
        currency="HKD",
        fx_fee_pct=0.0015,
        stamp_duty_pct=0.0013,  # HK stamp duty 0.13 % per trade leg
        typical_spread_bps=15.0,
    ),
    "l": VenueProfile(
        market_id="LSE",
        currency="GBP",
        fx_fee_pct=0.0015,
        stamp_duty_pct=0.005,  # UK SDRT 0.5 % on buys (AIM exempt — handled via override)
        typical_spread_bps=8.0,
    ),
    "as": VenueProfile(  # Euronext Amsterdam
        market_id="EURONEXT",
        currency="EUR",
        fx_fee_pct=0.0015,
        stamp_duty_pct=0.0,
        typical_spread_bps=5.0,
    ),
    "pa": VenueProfile(  # Euronext Paris
        market_id="EURONEXT",
        currency="EUR",
        fx_fee_pct=0.0015,
        stamp_duty_pct=0.0,
        typical_spread_bps=5.0,
    ),
    "br": VenueProfile(  # Euronext Brussels
        market_id="EURONEXT",
        currency="EUR",
        fx_fee_pct=0.0015,
        stamp_duty_pct=0.0,
        typical_spread_bps=8.0,
    ),
    "ls": VenueProfile(  # Euronext Lisbon
        market_id="EURONEXT",
        currency="EUR",
        fx_fee_pct=0.0015,
        stamp_duty_pct=0.0,
        typical_spread_bps=10.0,
    ),
    "de": VenueProfile(  # Xetra
        market_id="XETRA",
        currency="EUR",
        fx_fee_pct=0.0015,
        stamp_duty_pct=0.0,
        typical_spread_bps=5.0,
    ),
    "mi": VenueProfile(  # Borsa Italiana
        market_id="BORSA_ITALIANA",
        currency="EUR",
        fx_fee_pct=0.0015,
        stamp_duty_pct=0.001,  # Italian FTT for derivatives is higher; equities ~0.1 %
        typical_spread_bps=8.0,
    ),
    "sw": VenueProfile(  # SIX Swiss
        market_id="SIX",
        currency="CHF",
        fx_fee_pct=0.0015,
        stamp_duty_pct=0.00075,  # Swiss stamp duty
        typical_spread_bps=8.0,
    ),
    "co": VenueProfile(  # Copenhagen
        market_id="NASDAQ_COPENHAGEN",
        currency="DKK",
        fx_fee_pct=0.0015,
        stamp_duty_pct=0.0,
        typical_spread_bps=10.0,
    ),
    "st": VenueProfile(  # Stockholm
        market_id="NASDAQ_STOCKHOLM",
        currency="SEK",
        fx_fee_pct=0.0015,
        stamp_duty_pct=0.0,
        typical_spread_bps=10.0,
    ),
    "to": VenueProfile(  # Toronto
        market_id="TSX",
        currency="CAD",
        fx_fee_pct=0.0015,
        stamp_duty_pct=0.0,
        typical_spread_bps=8.0,
    ),
    "t": VenueProfile(  # Tokyo
        market_id="TSE",
        currency="JPY",
        fx_fee_pct=0.0015,
        stamp_duty_pct=0.0,
        typical_spread_bps=10.0,
    ),
}

# Default for plain US tickers (no suffix).
_US_VENUE = VenueProfile(
    market_id="US_EQUITY",
    currency="USD",
    fx_fee_pct=0.0015,  # Portuguese-resident T212 user pays FX even on USD
    stamp_duty_pct=0.0,
    typical_spread_bps=3.0,
)

# Crypto pairs traded against USD. We model them as a single 24/7 session.
_CRYPTO_VENUE = VenueProfile(
    market_id="CRYPTO_24_7",
    currency="USD",
    fx_fee_pct=0.0,  # crypto routes through Web3, no FX leg
    stamp_duty_pct=0.0,
    typical_spread_bps=10.0,
)


def get_venue_profile(ticker: str) -> VenueProfile:
    """Return the VenueProfile that owns this ticker.

    The function is suffix-driven and falls back to US equity. Crypto tickers
    (containing "-USD") are always classified as CRYPTO_24_7.
    """
    t = ticker.strip().upper()
    if "-USD" in t:
        return _CRYPTO_VENUE
    if "." in t:
        suffix = t.rsplit(".", 1)[1].lower()
        venue = _SUFFIX_VENUES.get(suffix)
        if venue is not None:
            return venue
    return _US_VENUE


def same_session(ticker_a: str, ticker_b: str) -> bool:
    """Return True iff both tickers trade in the same session window."""
    return get_venue_profile(ticker_a).market_id == get_venue_profile(ticker_b).market_id


def same_currency(ticker_a: str, ticker_b: str) -> bool:
    """Return True iff both tickers settle in the same currency."""
    return get_venue_profile(ticker_a).currency == get_venue_profile(ticker_b).currency


def estimate_round_trip_cost_pct(ticker_a: str, ticker_b: str, account_currency: str = "EUR") -> float:
    """Estimate the round-trip cost of trading both legs of a pair, as a percentage.

    Includes for each leg:
        - FX fee (only if leg currency != account currency)
        - Stamp duty (charged once on the buy leg; we assume one buy + one sell
          per round-trip per pair, so one stamp duty per leg lifecycle)
        - Typical spread (round-trip)

    The result is the *combined* cost across both legs and represents the
    minimum z-score-driven edge the strategy must beat to be profitable.
    """
    total = 0.0
    for ticker in (ticker_a, ticker_b):
        v = get_venue_profile(ticker)
        leg_cost = 0.0
        if v.currency != account_currency:
            # Round-trip FX: pay on entry, pay on exit.
            leg_cost += 2.0 * v.fx_fee_pct
        leg_cost += v.stamp_duty_pct
        leg_cost += v.typical_spread_bps / 10000.0  # bps -> pct
        total += leg_cost
    return total


__all__ = [
    "VenueProfile",
    "get_venue_profile",
    "same_session",
    "same_currency",
    "estimate_round_trip_cost_pct",
]
