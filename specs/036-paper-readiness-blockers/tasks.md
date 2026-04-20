# Tasks: Paper-Trading Readiness Blockers

**Branch**: `036-paper-readiness-blockers`
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

Tasks are ordered by dependency. Each has a concrete acceptance check a reviewer can run.

## T001 — Wire paper-mode fast path in `request_approval` (US1, P1)

**File**: `src/services/notification_service.py`
**Depends on**: none

Modify `NotificationService.request_approval(trade_summary: str) -> bool` so that when `settings.PAPER_TRADING` is truthy it:

1. Returns `True` in under 100 ms.
2. Fires a non-blocking Telegram notification via `asyncio.create_task(self.send_message(...))`, wrapped in try/except so Telegram failures cannot propagate.
3. Still writes to the dashboard terminal via `dashboard_state.add_message("BOT", text, metadata={"type": "paper_auto_approved"})` as a fire-and-forget task.
4. Skips the inline-keyboard, correlation-ID future, and 5-minute `asyncio.wait_for`.

The live-mode (`settings.PAPER_TRADING is False`) code path must be byte-identical to today's.

**Acceptance**:

- Importing the module still succeeds: `python -c "from src.services.notification_service import notification_service"`.
- Unit test (to be added in T004) asserts paper path returns `True` within 100 ms and does NOT create an entry in `self.pending_approvals`.

## T002 — Add DEV_MODE / market-hours pre-flight log line (US3, P3)

**File**: `src/monitor.py`
**Depends on**: none (independent of T001)

At the top of `ArbitrageMonitor.run()`, before the existing "Initializing Databases..." log, emit one INFO line with the format:

```
MODE: PAPER | DEV_MODE={bool} | Pair universe: {N} equity pairs | Next NYSE open: {ISO-timestamp in MARKET_TIMEZONE}
```

When `DEV_MODE=true`, collapse to:

```
MODE: PAPER | DEV_MODE=true (crypto test pairs, 24/7 scan, randomised prices)
```

Compute next-market-open with a small helper: advance `datetime.now(tz=MARKET_TIMEZONE)` to the next weekday 09:30 if outside 09:30–16:00 or on a weekend. Pure function, no external calls.

**Acceptance**:

- `python src/monitor.py` on a Sunday prints a line matching the Monday 09:30 format.
- Set `DEV_MODE=true` in `.env` and re-run → crypto message appears instead.

## T003 — Runbook execution: rotate four credentials (US2, P2)

**File**: `.env` (gitignored, local-only)
**Depends on**: none (operator action, can run in parallel with T001/T002)

Follow `specs/036-paper-readiness-blockers/rotation-runbook.md` end-to-end. For each of Gemini, Polygon, T212 (key + secret), Telegram: revoke at provider → paste new value into `.env` → verify with the runbook's curl probe.

**Acceptance**:

- All four curl probes from Section 5 of the runbook succeed with the new values.
- Probing any of the four old values returns `401`/`403`/`400` ("key not valid").
- `git ls-files | grep -E '^\.env$'` still prints nothing.

## T004 — Regression test for paper auto-approve

**File**: `tests/unit/test_notification_service_paper.py` (new)
**Depends on**: T001

Write a pytest-asyncio test that monkeypatches `settings.PAPER_TRADING = True`, monkeypatches `NotificationService.app.bot.send_message` to raise `RuntimeError("network down")`, then asserts `await notification_service.request_approval("test")` returns `True` and `notification_service.pending_approvals` is empty.

**Acceptance**:

- `pytest tests/unit/test_notification_service_paper.py -v --asyncio-mode=auto` passes.

## T005 — Smoke verification

**Depends on**: T001, T002, T003

Run the quickstart boot sequence. Confirm:

1. Pre-flight line appears first.
2. Telegram "🚀 Arbitrage Bot Online" heartbeat arrives (proves rotated token works).
3. If a signal fires during the smoke (or via a forced test), it simulates through `shadow_service` and produces a Telegram "Paper trade executed" message with no inline keyboard.

**Acceptance**:

- Quickstart's "Expected log sequence" matches observed output.

## Parallelizable

- T001 and T002 touch different files and can be done in parallel.
- T003 is operator-only; can run in parallel with T001/T002.
- T004 depends on T001.
- T005 is the final integration gate.
