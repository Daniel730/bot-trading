"""Phase-3 audit remediations: F-015, F-020, Telegram LIVE auth, F-023, F-025."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import settings
from src.models.persistence import PersistenceManager
from src.services.dashboard_service import TOTPManager, require_step_up_2fa
from src.services.open_slot_reservation import (
    OpenSlotReservationService,
    TradeIntentWAL,
    _checksum,
)


# ---------------------------------------------------------------------------
# F-015 / F-020 — open-slot reservation + intent WAL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_f015_concurrent_claims_only_one_wins(tmp_path: Path):
    wal = TradeIntentWAL(tmp_path / "slots.wal")
    svc = OpenSlotReservationService(wal=wal, ttl_seconds=120, prefer_distributed=False)

    async def attempt(sid: str):
        return await svc.claim(
            signal_id=sid,
            ticker_a="AAPL",
            ticker_b="MSFT",
            open_signals=[],
            max_open_pairs=8,
            block_shared_legs=True,
        )

    results = await asyncio.gather(*[attempt(f"sig-{i}") for i in range(12)])
    winners = [r for r in results if r.get("ok")]
    losers = [r for r in results if not r.get("ok")]
    assert len(winners) == 1
    assert len(losers) == 11
    assert svc.reservation_count() == 1


@pytest.mark.asyncio
async def test_f015_shared_leg_blocked(tmp_path: Path):
    wal = TradeIntentWAL(tmp_path / "slots.wal")
    svc = OpenSlotReservationService(wal=wal, ttl_seconds=120, prefer_distributed=False)
    first = await svc.claim(
        signal_id="a",
        ticker_a="AAPL",
        ticker_b="MSFT",
        open_signals=[],
    )
    assert first["ok"]
    second = await svc.claim(
        signal_id="b",
        ticker_a="AAPL",
        ticker_b="GOOG",
        open_signals=[],
    )
    assert not second["ok"]
    assert second["reason"] == "shared_leg_guard"


@pytest.mark.asyncio
async def test_f015_max_open_pairs_under_concurrency(tmp_path: Path):
    wal = TradeIntentWAL(tmp_path / "cap.wal")
    svc = OpenSlotReservationService(wal=wal, ttl_seconds=120, prefer_distributed=False)
    # Pre-fill 2 "open" signals; max=3 → only one additional claim may succeed.
    open_signals = [
        {"signal_id": "o1", "legs": [{"ticker": "T1"}, {"ticker": "T2"}]},
        {"signal_id": "o2", "legs": [{"ticker": "T3"}, {"ticker": "T4"}]},
    ]

    async def attempt(i: int):
        return await svc.claim(
            signal_id=f"n{i}",
            ticker_a=f"N{i}A",
            ticker_b=f"N{i}B",
            open_signals=open_signals,
            max_open_pairs=3,
            block_shared_legs=False,
        )

    results = await asyncio.gather(*[attempt(i) for i in range(10)])
    assert sum(1 for r in results if r.get("ok")) == 1


@pytest.mark.asyncio
async def test_f015_release_idempotent(tmp_path: Path):
    wal = TradeIntentWAL(tmp_path / "rel.wal")
    svc = OpenSlotReservationService(wal=wal, ttl_seconds=120, prefer_distributed=False)
    await svc.claim(signal_id="r1", ticker_a="A", ticker_b="B", open_signals=[])
    assert await svc.release("r1") is True
    assert await svc.release("r1") is False
    assert svc.reservation_count() == 0



@pytest.mark.asyncio
async def test_f020_wal_replay_restores_active_claims(tmp_path: Path):
    path = tmp_path / "intent.wal"
    wal1 = TradeIntentWAL(path)
    svc1 = OpenSlotReservationService(wal=wal1, ttl_seconds=600, prefer_distributed=False)
    claim = await svc1.claim(
        signal_id="crash-me",
        ticker_a="BTC-USD",
        ticker_b="ETH-USD",
        open_signals=[],
    )
    assert claim["ok"]
    # Simulate process death + restart: new service, same WAL file.
    wal2 = TradeIntentWAL(path)
    svc2 = OpenSlotReservationService(wal=wal2, ttl_seconds=600, prefer_distributed=False)
    assert svc2.has("crash-me")
    assert svc2.reservation_count() == 1

    await svc2.release("crash-me", reason="done")
    svc3 = OpenSlotReservationService(wal=TradeIntentWAL(path), ttl_seconds=600, prefer_distributed=False)
    assert not svc3.has("crash-me")
    assert svc3.reservation_count() == 0


def test_f020_wal_checksum_rejects_tamper(tmp_path: Path):
    path = tmp_path / "tamper.wal"
    wal = TradeIntentWAL(path)
    wal.append("CLAIM", {"signal_id": "s1", "ticker_a": "A", "ticker_b": "B", "legs": ["A", "B"]})
    lines = path.read_text().strip().splitlines()
    rec = json.loads(lines[0])
    rec["signal_id"] = "EVIL"
    # Keep old checksum → mismatch on read
    path.write_text(json.dumps(rec) + "\n")
    good = list(wal.iter_records())
    assert good == []


def test_f020_wal_replay_equals_original_state_property(tmp_path: Path):
    """Property: for any CLAIM/RELEASE sequence, replay == live state."""
    path = tmp_path / "prop.wal"
    ops = [
        ("CLAIM", "s1", "A", "B"),
        ("CLAIM", "s2", "C", "D"),
        ("RELEASE", "s1", None, None),
        ("CLAIM", "s3", "E", "F"),
        ("RELEASE", "s2", None, None),
        ("CLAIM", "s1", "A", "B"),  # re-open after release
    ]

    async def run():
        wal = TradeIntentWAL(path)
        svc = OpenSlotReservationService(wal=wal, ttl_seconds=600, prefer_distributed=False)
        for op, sid, a, b in ops:
            if op == "CLAIM":
                r = await svc.claim(signal_id=sid, ticker_a=a, ticker_b=b, open_signals=[])
                assert r["ok"], r
            else:
                await svc.release(sid)
        live = sorted(svc._by_signal.keys())
        replayed = OpenSlotReservationService(
            wal=TradeIntentWAL(path), ttl_seconds=600, prefer_distributed=False
        )
        assert sorted(replayed._by_signal.keys()) == live

    asyncio.run(run())


def test_f020_sqlite_wal_mode_and_atomic_budget(tmp_path: Path):
    db = tmp_path / "state.db"
    pm = PersistenceManager(str(db))
    conn = pm._get_connection()
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert str(mode).lower() == "wal"

    pm.set_system_state("budget:ALPACA:used", "100.0")
    n1 = pm.increment_system_state_float("budget:ALPACA:used", 25.5)
    n2 = pm.increment_system_state_float("budget:ALPACA:used", 10.0)
    assert n1 == pytest.approx(125.5)
    assert n2 == pytest.approx(135.5)
    assert float(pm.get_system_state("budget:ALPACA:used")) == pytest.approx(135.5)


def test_f020_concurrent_budget_increments(tmp_path: Path):
    db = tmp_path / "race.db"
    pm = PersistenceManager(str(db))
    pm.set_system_state("budget:ALPACA:used", "0")

    import concurrent.futures

    def bump(_):
        local = PersistenceManager(str(db))
        return local.increment_system_state_float("budget:ALPACA:used", 1.0)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(bump, range(50)))

    assert float(pm.get_system_state("budget:ALPACA:used")) == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# Telegram LIVE trade approve refuse (login still allowed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_telegram_live_trade_approve_refused_login_allowed(monkeypatch):
    from src.services.notification_service import NotificationService

    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", True)
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://api.alpaca.markets")
    assert settings.should_auto_approve_trades is False

    svc = NotificationService.__new__(NotificationService)
    svc.chat_id = "999"
    svc.pending_approvals = {}
    svc.pending_approval_summaries = {}
    svc._redact_sensitive_text = lambda x: str(x)

    trade_cid = "trade01"
    login_cid = "login01"
    trade_fut = asyncio.get_running_loop().create_future()
    login_fut = asyncio.get_running_loop().create_future()
    svc.pending_approvals[trade_cid] = trade_fut
    svc.pending_approvals[login_cid] = login_fut
    svc.pending_approval_summaries[trade_cid] = "BUY AAPL"

    edited = []

    async def fake_edit(text=None, **_kwargs):
        edited.append(text or "")

    def make_update(cid: str):
        query = SimpleNamespace(
            from_user=SimpleNamespace(id=999, username="op"),
            data=f"approve:{cid}",
            answer=AsyncMock(),
            message=SimpleNamespace(text=f"msg {cid}"),
            edit_message_text=fake_edit,
        )
        return SimpleNamespace(callback_query=query)

    await svc._handle_callback(make_update(trade_cid), None)
    assert not trade_fut.done()
    assert trade_cid in svc.pending_approvals
    assert any("dashboard with 2FA" in t for t in edited)

    await svc._handle_callback(make_update(login_cid), None)
    assert login_fut.done() and login_fut.result() is True


@pytest.mark.asyncio
async def test_telegram_live_invest_refused(monkeypatch):
    from src.services.notification_service import NotificationService

    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", True)
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://api.alpaca.markets")
    assert settings.should_auto_approve_trades is False

    svc = NotificationService.__new__(NotificationService)
    svc.chat_id = "42"
    svc._redact_sensitive_text = lambda x: str(x)

    replies = []

    async def reply_text(text, **_kwargs):
        replies.append(text)

    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42, username="op"),
        message=SimpleNamespace(reply_text=reply_text),
    )
    context = SimpleNamespace(args=["10", "of", "AAPL", "confirm"])

    await svc._handle_invest(update, context)

    assert any("LIVE /invest is disabled" in r for r in replies)


# ---------------------------------------------------------------------------
# F-023 — pairs step-up
# ---------------------------------------------------------------------------


def test_f023_require_step_up_for_pairs_action(monkeypatch):
    from src.services import dashboard_service as ds

    monkeypatch.setattr(ds.dashboard_service.totp, "public_status", lambda: {"enabled": True})
    monkeypatch.setattr(
        ds.dashboard_service.totp, "verify_token_or_backup", lambda token: token == "999999"
    )
    with pytest.raises(Exception) as exc:
        require_step_up_2fa(None, action="mutating trading pairs")
    assert getattr(exc.value, "status_code", None) == 403

    require_step_up_2fa("999999", action="mutating trading pairs")


# ---------------------------------------------------------------------------
# F-025 — Fernet TOTP + salted backups
# ---------------------------------------------------------------------------


def test_f025_fernet_roundtrip_and_legacy_xor_migration(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DASHBOARD_TOKEN", "phase3-dashboard-token-for-tests-only")
    # Reload key material via fresh manager
    pm = PersistenceManager(str(tmp_path / "auth.db"))
    totp = TOTPManager(pm)

    secret = totp.generate_secret()
    protected = totp._protect_secret(secret)
    assert protected.startswith("fernet:")
    assert totp._unprotect_secret(protected) == secret

    # Legacy XOR ciphertext still decrypts
    key = totp._key_bytes()
    masked = bytes(b ^ key[i % len(key)] for i, b in enumerate(secret.encode("utf-8")))
    legacy = base64.urlsafe_b64encode(masked).decode("ascii")
    assert totp._unprotect_secret(legacy) == secret

    # Persist enabled state with legacy XOR; verify migrates to Fernet
    code = totp.totp_token(secret)
    state = {
        "enabled": True,
        "pending": None,
        "secret_encrypted": legacy,
        "backup_code_hashes": [],
    }
    totp.save_state(state)
    assert totp.verify_token_or_backup(code)
    migrated = totp.get_state()["secret_encrypted"]
    assert str(migrated).startswith("fernet:")


def test_f025_salted_backup_codes_and_legacy_sha(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DASHBOARD_TOKEN", "phase3-dashboard-token-for-tests-only")
    pm = PersistenceManager(str(tmp_path / "auth2.db"))
    totp = TOTPManager(pm)
    secret = totp.generate_secret()
    backup = "DEADBEEF"
    salted = totp.hash_backup_code(backup)
    assert "$" in salted
    legacy = hashlib.sha256(backup.encode("utf-8")).hexdigest()

    state = {
        "enabled": True,
        "pending": None,
        "secret_encrypted": totp._protect_secret(secret),
        "backup_code_hashes": [salted, legacy],
    }
    totp.save_state(state)
    assert totp.verify_token_or_backup(backup)
    # Single-use consumption
    remaining = totp.get_state()["backup_code_hashes"]
    assert len(remaining) == 1
    assert totp.verify_token_or_backup(backup)  # consumes legacy
    assert totp.get_state()["backup_code_hashes"] == []


# ---------------------------------------------------------------------------
# Fuzz-ish malformed inputs (no hypothesis dep)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_f015_fuzz_malformed_claims(tmp_path: Path):
    wal = TradeIntentWAL(tmp_path / "fuzz.wal")
    svc = OpenSlotReservationService(wal=wal, ttl_seconds=60, prefer_distributed=False)
    payloads = [
        {"signal_id": "", "ticker_a": "A", "ticker_b": "B"},
        {"signal_id": "ok", "ticker_a": "", "ticker_b": "B"},
        {"signal_id": "ok2", "ticker_a": "A", "ticker_b": "A"},
        {"signal_id": "ok3", "ticker_a": "A", "ticker_b": "B"},
    ]
    for p in payloads:
        r = await svc.claim(open_signals=[], **p)
        if p["signal_id"] == "ok3" and p["ticker_a"] != p["ticker_b"] and p["ticker_a"]:
            assert r["ok"]
        else:
            assert not r["ok"]


def test_f020_wal_corrupt_json_lines_skipped(tmp_path: Path):
    path = tmp_path / "corrupt.wal"
    wal = TradeIntentWAL(path)
    rec = wal.append("CLAIM", {"signal_id": "keep", "ticker_a": "A", "ticker_b": "B", "legs": ["A", "B"]})
    with path.open("a") as fh:
        fh.write("{not json\n")
        fh.write('{"seq":99,"op":"CLAIM","signal_id":"bad","checksum":"0"*64}\n'.replace('"0"*64', '"00"'))
    records = list(wal.iter_records())
    assert any(r.get("signal_id") == "keep" for r in records)
    assert all(r.get("signal_id") != "bad" for r in records)
    # checksum of keep still valid
    assert _checksum(rec) == rec["checksum"]
