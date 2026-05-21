import pytest


@pytest.mark.asyncio
async def test_official_fake_fixtures_cover_core_service_boundaries(
    fake_broker,
    fake_market_data,
    fake_redis,
    fake_persistence,
):
    fake_market_data.latest_prices["SGOV"] = 100.0
    fake_redis.json_values["health"] = {"ok": True}

    assert fake_broker.get_venue() == "ALPACA"
    assert await fake_broker.get_account_cash() == 10_000.0
    assert await fake_market_data.get_bid_ask("SGOV") == (99.5, 100.5)
    assert await fake_market_data.get_latest_price_async(["SGOV"]) == {"SGOV": 100.0}
    assert await fake_redis.get_json("health") == {"ok": True}
    assert await fake_persistence.get_open_signals() == []
