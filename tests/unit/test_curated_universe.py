"""Universe hygiene: curated US pairs + discovery freeze defaults (PR E)."""

from src.config import settings


def test_arbitrage_pairs_are_us_liquid_same_session():
    pairs = settings.ARBITRAGE_PAIRS
    assert 20 <= len(pairs) <= 90
    for pair in pairs:
        for key in ("ticker_a", "ticker_b"):
            t = pair[key]
            assert "." not in t, f"regional suffix not allowed in curated list: {t}"
            assert not t.endswith((".L", ".DE", ".AS", ".PA", ".HK"))


def test_max_active_pairs_tighter_than_universe():
    assert settings.MAX_ACTIVE_PAIRS <= 20
    assert settings.MAX_ACTIVE_PAIRS < len(settings.ARBITRAGE_PAIRS)


def test_pair_discovery_frozen_by_default():
    assert settings.PAIR_DISCOVERY_ENABLED is False
    assert settings.PAIR_DISCOVERY_AUTO_PROMOTE is False
