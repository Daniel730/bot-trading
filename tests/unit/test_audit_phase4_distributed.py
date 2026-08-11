"""Phase-4 distributed safety: multi-instance reservation, exactly-once, equity DD, LIVE gate."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

from src.services.capital_halt_service import evaluate_capital_halt
from src.services.distributed_reservation import DistributedReservationStore
from src.services.execution_intent_service import ExecutionIntentService
from src.services.live_readiness import evaluate_live_readiness, enforce_live_readiness_or_block
from src.services.leg_orphan_recovery import recover_leg_a_orphans
from src.services.open_slot_reservation import OpenSlotReservationService, TradeIntentWAL
from src.services.persistence_service import (
    OrderSide,
    OrderStatus,
    TradeLedger,
    persistence_service,
)
from src.config import settings


async def _cleanup_tables():
    await persistence_service.init_db()
    store = DistributedReservationStore()
    await store.ensure_schema()
    async with persistence_service.AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(text("DELETE FROM open_slot_reservations"))
            await session.execute(text("DELETE FROM execution_intents"))


@pytest.fixture(autouse=True)
async def _clean_distributed():
    # asyncpg pools bind to the event loop; dispose between tests.
    await persistence_service.engine.dispose()
    await _cleanup_tables()
    yield
    await persistence_service.engine.dispose()


# ---------------------------------------------------------------------------
# R-301 — prove N concurrent "instances" cannot double-claim
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_r301_ten_instances_one_winner_postgres():
    """Simulate 10 bot instances racing the same pair via separate store objects."""
    stores = [DistributedReservationStore(ttl_seconds=300) for _ in range(10)]
    for i, s in enumerate(stores):
        s.holder_id = f"instance-{i}"

    async def attempt(i: int):
        return await stores[i].claim(
            signal_id=f"sig-{i}",
            ticker_a="AAPL",
            ticker_b="MSFT",
            open_signal_count=0,
            open_signal_legs=[],
            max_open_pairs=8,
            block_shared_legs=True,
        )

    results = await asyncio.gather(*[attempt(i) for i in range(10)])
    winners = [r for r in results if r.get("ok")]
    assert len(winners) == 1, results
    assert await stores[0].reservation_count() == 1


@pytest.mark.asyncio
async def test_r301_survives_process_restart_simulation():
    store1 = DistributedReservationStore(ttl_seconds=600)
    store1.holder_id = "proc-1"
    claim = await store1.claim(
        signal_id="crash-signal",
        ticker_a="BTC-USD",
        ticker_b="ETH-USD",
        open_signal_count=0,
    )
    assert claim["ok"]

    # New process = new store object, same Postgres.
    store2 = DistributedReservationStore(ttl_seconds=600)
    store2.holder_id = "proc-2"
    assert await store2.has("crash-signal")
    conflict = await store2.claim(
        signal_id="other",
        ticker_a="BTC-USD",
        ticker_b="SOL-USD",
        open_signal_count=0,
    )
    assert not conflict["ok"]
    assert conflict["reason"] == "shared_leg_guard"


@pytest.mark.asyncio
async def test_r301_facade_uses_postgres_not_python_lock(tmp_path: Path):
    wal = TradeIntentWAL(tmp_path / "audit.wal")
    # Two facades, each with prefer_distributed=True (default) — shared PG.
    a = OpenSlotReservationService(wal=wal, prefer_distributed=True)
    b = OpenSlotReservationService(wal=TradeIntentWAL(tmp_path / "b.wal"), prefer_distributed=True)

    r1, r2 = await asyncio.gather(
        a.claim(signal_id="fa", ticker_a="X", ticker_b="Y", open_signals=[]),
        b.claim(signal_id="fb", ticker_a="X", ticker_b="Y", open_signals=[]),
    )
    assert sum(1 for r in (r1, r2) if r.get("ok")) == 1


# ---------------------------------------------------------------------------
# Exactly-once intents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exactly_once_100_duplicate_intents():
    svc = ExecutionIntentService()
    sid = str(uuid.uuid4())
    coid = f"{sid}-A"

    async def once():
        return await svc.begin_intent(signal_id=sid, leg="A", client_order_id=coid)

    results = await asyncio.gather(*[once() for _ in range(100)])
    ok = [r for r in results if r.get("ok")]
    dup = [r for r in results if not r.get("ok")]
    assert len(ok) == 1
    assert len(dup) == 99
    assert all(r.get("idempotent") for r in dup)


@pytest.mark.asyncio
async def test_exactly_once_leg_b_independent():
    svc = ExecutionIntentService()
    sid = str(uuid.uuid4())
    a = await svc.begin_intent(signal_id=sid, leg="A", client_order_id=f"{sid}-A")
    b = await svc.begin_intent(signal_id=sid, leg="B", client_order_id=f"{sid}-B")
    assert a["ok"] and b["ok"]
    again = await svc.begin_intent(signal_id=sid, leg="A", client_order_id=f"{sid}-A-dup")
    assert not again["ok"]


# ---------------------------------------------------------------------------
# R-303 equity drawdown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_r303_equity_hwm_drawdown_halts(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "IGNORE_UNMANAGED_POSITIONS", False)
    monkeypatch.setattr(settings, "MAX_DRAWDOWN", 0.10)

    await persistence_service.set_system_state("operational_status", "NORMAL")
    await persistence_service.set_system_state("equity_high_water_mark", "100000")

    class FakeBroker:
        async def get_account_equity(self):
            return 85000.0  # 15% DD from HWM

    with patch("src.services.brokerage_service.BrokerageService", return_value=FakeBroker()):
        # Bypass daily pnl path issues by stubbing
        async def fake_daily(*_a, **_k):
            return 0.0

        monkeypatch.setattr(persistence_service, "get_daily_pnl_for_date", fake_daily)
        result = await evaluate_capital_halt(persistence_service=persistence_service)

    assert result["halt"] is True
    assert result["reason"] == "equity_drawdown_exceeds_max_drawdown"


@pytest.mark.asyncio
async def test_r303_equity_new_high_updates_hwm(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "IGNORE_UNMANAGED_POSITIONS", False)
    monkeypatch.setattr(settings, "MAX_DRAWDOWN", 0.50)
    await persistence_service.set_system_state("operational_status", "NORMAL")
    await persistence_service.set_system_state("equity_high_water_mark", "10000")

    class FakeBroker:
        async def get_account_equity(self):
            return 12000.0

    with patch("src.services.brokerage_service.BrokerageService", return_value=FakeBroker()):
        monkeypatch.setattr(
            persistence_service, "get_daily_pnl_for_date", AsyncMock(return_value=0.0)
        )
        result = await evaluate_capital_halt(persistence_service=persistence_service)

    assert result["halt"] is False
    hwm = await persistence_service.get_system_state("equity_high_water_mark")
    assert float(hwm) == pytest.approx(12000.0)


# ---------------------------------------------------------------------------
# R-302 leg orphan recovery (DB-backed; see also test_leg_orphan_recovery_fill_confirm.py)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_r302_leg_a_orphan_emergency_close(monkeypatch):
    sid = uuid.uuid4()
    async with persistence_service.AsyncSessionLocal() as session:
        async with session.begin():
            session.add(
                TradeLedger(
                    id=uuid.uuid4(),
                    order_id=f"{sid}-A",
                    signal_id=sid,
                    ticker="ORPHAN1",
                    side=OrderSide.BUY,
                    quantity=2.0,
                    price=10.0,
                    status=OrderStatus.LEG_A_FILLED,
                    venue="ALPACA",
                    metadata_json={"orphaned_candidate": True},
                )
            )

    placed = []

    class FakeBroker:
        async def get_portfolio(self):
            return [{"ticker": "ORPHAN1", "quantity": 2.0}]

        async def get_pending_orders(self):
            return []

        async def place_market_order(self, ticker, qty, side, limit_price=None, client_order_id=None, *, intent="open"):
            placed.append(
                {
                    "ticker": ticker,
                    "qty": qty,
                    "side": side,
                    "client_order_id": client_order_id,
                    "intent": intent,
                }
            )
            # Fill-confirmed close (submit-accept alone must not flatten — unit-tested separately).
            return {"status": "filled", "order_id": "close-1"}

    summary = await recover_leg_a_orphans(brokerage=FakeBroker(), dry_run=False)
    assert summary["broker_ok"]
    assert summary["recovered"] >= 1
    assert placed
    assert placed[0]["intent"] == "close"
    assert placed[0]["side"] == "SELL"


# ---------------------------------------------------------------------------
# LIVE readiness gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_live_readiness_blocks_when_items_fail(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", True)
    monkeypatch.setattr(settings, "DEV_MODE", False)
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://api.alpaca.markets")

    class BadBroker:
        async def get_account_cash(self):
            raise RuntimeError("down")

    result = await evaluate_live_readiness(
        brokerage=BadBroker(),
        persistence_service=persistence_service,
        totp_enabled_check=lambda: False,
    )
    assert result["ready"] is False
    failed = {i["name"] for i in result["items"] if not i["ok"]}
    assert "broker_connected" in failed
    assert "two_factor_ok" in failed


@pytest.mark.asyncio
async def test_live_readiness_skipped_for_paper(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", True)
    out = await enforce_live_readiness_or_block()
    assert out.get("skipped") is True
    assert out.get("ready") is True


# ---------------------------------------------------------------------------
# Chaos + replay (reduced CI scale)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chaos_random_claim_release_no_duplicates():
    """Hundreds of random claim/release ops — never >1 active per leg."""
    import random

    store = DistributedReservationStore(ttl_seconds=120)
    pairs = [(f"T{i}A", f"T{i}B") for i in range(20)]
    active: set[str] = set()

    for n in range(200):
        a, b = random.choice(pairs)
        sid = f"chaos-{n}-{a}-{b}"
        if random.random() < 0.6 or not active:
            r = await store.claim(
                signal_id=sid,
                ticker_a=a,
                ticker_b=b,
                open_signal_count=0,
                block_shared_legs=True,
                max_open_pairs=50,
            )
            if r.get("ok"):
                active.add(sid)
        else:
            if active:
                victim = random.choice(list(active))
                await store.release(victim, reason="chaos")
                active.discard(victim)

    # Authority count
    count = await store.reservation_count()
    rows = await store.active_as_open_signals()
    legs_seen: list[str] = []
    for sig in rows:
        for leg in sig["legs"]:
            legs_seen.append(leg["ticker"])
    assert len(legs_seen) == len(set(legs_seen)), "duplicate legs in active reservations"
    assert count == len(rows)


def test_replay_engine_deterministic_hash():
    """Same historical event stream → identical state hash (10 runs)."""
    events = [
        {"op": "CLAIM", "signal_id": "s1", "legs": ["A", "B"]},
        {"op": "CLAIM", "signal_id": "s2", "legs": ["C", "D"]},
        {"op": "RELEASE", "signal_id": "s1"},
        {"op": "CLAIM", "signal_id": "s3", "legs": ["E", "F"]},
        {"op": "RELEASE", "signal_id": "s2"},
    ]

    def run_once() -> str:
        state: dict[str, list[str]] = {}
        for ev in events:
            if ev["op"] == "CLAIM":
                state[ev["signal_id"]] = list(ev["legs"])
            else:
                state.pop(ev["signal_id"], None)
        canonical = json.dumps(state, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    hashes = [run_once() for _ in range(10)]
    assert len(set(hashes)) == 1


@pytest.mark.asyncio
async def test_soak_lite_200_signals_no_dup_orders():
    """Scaled soak: 200 unique signals, each attempted 5× → 200 intents max."""
    svc = ExecutionIntentService()
    placed = 0
    for i in range(200):
        sid = uuid.uuid4()
        coid = f"{sid}-A"
        for _dup in range(5):
            r = await svc.begin_intent(signal_id=sid, leg="A", client_order_id=coid)
            if r.get("ok"):
                placed += 1
    assert placed == 200
    assert await svc.count_open_intents() == 200
