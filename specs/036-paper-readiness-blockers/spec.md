# Feature Specification: Paper-Trading Readiness Blockers

**Feature Branch**: `036-paper-readiness-blockers`
**Created**: 2026-04-19
**Status**: Draft
**Input**: User description: "Resolve paper-trading readiness blockers: auto-approve in paper mode, secret rotation hygiene, and DEV_MODE boot guidance"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Paper-mode signals execute without manual taps (Priority: P1)

When the bot is configured with `PAPER_TRADING=true`, any signal whose orchestrator confidence crosses the execution threshold should simulate through `shadow_service` immediately. The operator receives a Telegram notification for visibility, but no human action is required for the trade to proceed.

**Why this priority**: Without this, the bot is functionally dead in paper mode. The monitor calls `request_approval` before every paper execution; the current implementation blocks up to five minutes and returns `False` on timeout, so un-attended paper runs veto every signal. Fixing this is the single code change that unblocks overnight paper testing.

**Independent Test**: Set `PAPER_TRADING=true`, inject a synthetic signal with `final_confidence > 0.5`, observe that `shadow_service.execute_simulated_trade` is invoked within 1 second and that a Telegram message ("Paper trade executed …") appears without any inline keyboard.

**Acceptance Scenarios**:

1. **Given** `PAPER_TRADING=true` and a signal with confidence 0.75, **When** the monitor reaches the approval step, **Then** `request_approval` returns `True` in under 100 ms and no inline-button Telegram message is sent.
2. **Given** `PAPER_TRADING=true` and Telegram credentials are invalid, **When** the monitor reaches the approval step, **Then** the approval still returns `True` and the shadow trade still executes; the Telegram failure is logged but non-fatal.
3. **Given** `PAPER_TRADING=false` (live mode), **When** the monitor reaches the approval step, **Then** behavior is unchanged — an inline-button message is sent and the coroutine awaits human input.

---

### User Story 2 — Operator can rotate exposed credentials safely (Priority: P2)

The four third-party credentials (Gemini API key, Polygon API key, Trading 212 key + secret, Telegram bot token) were exposed in an earlier session transcript. The operator needs a guided, in-session path to invalidate the old credentials, generate new ones, and have them written to the gitignored local `.env` in a single pass.

**Why this priority**: Compromised keys are a real risk even though `.env` is gitignored. The rotation can happen in parallel with paper-trading prep; it does not block a clean boot if rotation is deferred.

**Independent Test**: Operator runs a single rotation pass; at the end, `.env` contains four new values and the old Telegram token no longer responds to `getMe`.

**Acceptance Scenarios**:

1. **Given** the old credentials in `.env`, **When** the operator completes the guided rotation, **Then** each new value is persisted to `.env` (not committed) and the prior Gemini / Polygon / T212 / Telegram credentials are revoked at the provider.
2. **Given** `.env` was never tracked by git, **When** verifying git state after rotation, **Then** `git ls-files` still does not show `.env` and `git status` shows no leaked-secret diff.

---

### User Story 3 — Operator sees market-hours context at boot (Priority: P3)

When the bot starts, the first-page log output should make it obvious (a) whether `DEV_MODE` is enabled, (b) what the active pair universe is (21 equity pairs vs. the crypto test pairs), and (c) when the next trading window opens in the bot's configured timezone. This prevents the operator from concluding "it's broken" when the bot is merely idling before market open.

**Why this priority**: Behavior is already correct; this is a quality-of-life change. Skipping it does not block paper trading.

**Independent Test**: Run `python src/monitor.py` at any hour; the first ten log lines must explicitly name the mode, pair count, and next-market-open timestamp.

**Acceptance Scenarios**:

1. **Given** `DEV_MODE=false` and it is Sunday, **When** the bot boots, **Then** the startup log contains `DEV_MODE=false | Pair universe: 21 equity pairs | Next NYSE open: Mon YYYY-MM-DD 09:30 ET`.
2. **Given** `DEV_MODE=true`, **When** the bot boots, **Then** the startup log contains `DEV_MODE=true (crypto test pairs, 24/7 scan, randomised prices)`.

---

### Edge Cases

- Telegram API unreachable during paper auto-approve → approval still returns `True`, exception is logged, shadow trade proceeds.
- Operator rotates Telegram token mid-session → the running `notification_service` instance keeps the old token until process restart; the runbook must call this out.
- `PAPER_TRADING` flips from `true` to `false` without restart → not supported (settings are read once at import); runbook must document the restart requirement.
- Monitor boots on a weekend with `DEV_MODE=false` → bot idles cleanly and logs the wait; this is not an error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST auto-approve trade requests when `settings.PAPER_TRADING` is `True`, returning `True` from `notification_service.request_approval` in under 100 ms without awaiting any external input.
- **FR-002**: System MUST still emit a Telegram notification for paper-approved trades, but failures in that send MUST NOT block or fail the approval.
- **FR-003**: System MUST preserve the existing interactive approval flow (inline buttons + 5-minute timeout) when `settings.PAPER_TRADING` is `False`.
- **FR-004**: `.env` MUST remain gitignored and untracked; the rotation runbook MUST verify `git ls-files | grep -E '^\.env$'` returns empty after completion.
- **FR-005**: The rotation runbook MUST cover all four exposed credentials (Gemini, Polygon, Trading 212 key+secret, Telegram bot token) with provider-specific revocation steps.
- **FR-006**: Monitor startup MUST log a single line that names the active mode, pair universe size, and — in non-DEV mode — the next market-open timestamp in the configured timezone.

### Key Entities

- **Approval Request**: Correlation-ID-keyed future awaiting a boolean resolution. In paper mode the future is pre-resolved to `True`; in live mode it is resolved by a Telegram callback or a 5-minute timeout.
- **Credential Set**: The four provider keys living in `.env`. Rotation replaces each atomically (old value is revoked at the provider before the new value is written locally).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In paper mode, the time from "signal generated" to "shadow trade logged" is under 2 seconds (vs. up to 300 seconds today).
- **SC-002**: 100% of paper-mode signals with `final_confidence > 0.5` reach `shadow_service.execute_simulated_trade`.
- **SC-003**: After rotation, the four old credentials return `401`/`403` (or equivalent revocation response) when probed at their respective providers.
- **SC-004**: An operator reading the first page of `monitor.py` log output can answer "is the bot trading right now, and if not why?" without needing to grep or inspect `.env`.

## Assumptions

- The operator has admin access to Google AI Studio, Polygon.io, Trading 212, and Telegram BotFather (i.e., they can issue and revoke keys themselves).
- `.env` is already gitignored and not tracked (verified in current repo state); the runbook does not need a `git rm --cached` step.
- Telegram remains the sole channel for paper-mode trade notifications; the dashboard terminal continues to receive its existing copy via `dashboard_state.add_message`.
- The Java execution engine and `shadow_service` are out of scope for this feature — the monitor's existing `if settings.PAPER_TRADING: await shadow_service.execute_simulated_trade(...)` branch is already correct and remains untouched.
- `DEV_MODE` behavior is already correct (crypto pairs + 24/7 scanning); only the boot-time log line needs to be added.
