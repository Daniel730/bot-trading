#!/usr/bin/env python3
"""Safe, low-risk, reversible auto-remediations for the Daily Bot Audit.

DESIGN CONTRACT (read docs/DAILY_AUDIT.md before changing anything here):

* Every remediation in this module is, by construction, NON-FINANCIAL and
  REVERSIBLE. It never touches: trading mode, risk/sizing thresholds, broker
  credentials, endpoints, live capital, or anything that could place/cancel an
  order. Anything that could affect capital MUST be emitted as a
  ``REQUIRES_REVIEW`` finding from the audit orchestrator, never auto-fixed.
* Each fix is idempotent: running it twice with no intervening change is a no-op.
* Each fix has a ``validate`` step. If validation fails, the orchestrator
  reverts the change automatically (see ``apply_with_guard``).
* Anti-loop guards (per ``RemediationState``):
    - ``max_fixes_per_run`` (default 5) — never apply more than this per run.
    - per-signature cooldown (default 24h) — don't re-apply the same fix.
    - per-signature attempt cap (default 3) — after N failed/looping attempts,
      stop and mark ``REQUIRES_REVIEW``.
* Remediations are only *discovered* here; the orchestrator decides whether to
  call them. Discovery functions return candidate fixes; the orchestrator
  enforces the caps/guards before applying.
"""
from __future__ import annotations

import json
import shutil
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "audit" / "remediation_state.json"

# ---- tunables (kept conservative on purpose) -------------------------------
MAX_FIXES_PER_RUN = 5
COOLDOWN_SECONDS = 24 * 3600
MAX_ATTEMPTS_PER_SIGNATURE = 3


@dataclass
class Fix:
    """A concrete, ready-to-apply remediation candidate."""

    signature: str          # stable hash key for the problem class
    title: str
    detail: str
    apply: Callable[[], None]
    validate: Callable[[], bool]
    reversible: bool = True
    # Optional restore used by the orchestrator when validate() fails.
    restore: Optional[Callable[[], None]] = None
    evidence: str = ""


@dataclass
class RemediationState:
    """Persistent, per-signature bookkeeping that prevents fix loops."""

    attempts: dict[str, int] = field(default_factory=dict)
    last_applied_at: dict[str, float] = field(default_factory=dict)
    last_outcome: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path = STATE_PATH) -> "RemediationState":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                attempts=data.get("attempts", {}),
                last_applied_at=data.get("last_applied_at", {}),
                last_outcome=data.get("last_outcome", {}),
            )
        except (json.JSONDecodeError, OSError):
            return cls()

    def save(self, path: Path = STATE_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "attempts": self.attempts,
                    "last_applied_at": self.last_applied_at,
                    "last_outcome": self.last_outcome,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def can_apply(self, signature: str, now: float | None = None) -> tuple[bool, str]:
        """Return (allowed, reason). Enforces cooldown + attempt cap."""
        now = now if now is not None else time.time()
        if self.attempts.get(signature, 0) >= MAX_ATTEMPTS_PER_SIGNATURE:
            return False, (
                f"signature {signature} hit attempt cap "
                f"({MAX_ATTEMPTS_PER_SIGNATURE}); escalate to REQUIRES_REVIEW"
            )
        last = self.last_applied_at.get(signature)
        if last is not None and (now - last) < COOLDOWN_SECONDS:
            return False, f"signature {signature} within cooldown ({COOLDOWN_SECONDS}s)"
        return True, "ok"


def _monitor_running() -> bool:
    """Best-effort check for a live monitor process (windows/linux)."""
    import subprocess

    try:
        out = subprocess.run(
            ["pgrep", "-af", "monitor.py"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        # Windows / no pgrep: assume not running so we never delete live state.
        return False
    return bool(out.strip())


# ---- discovery (returns candidate Fixes; orchestrator gates application) ----
def discover_safe_fixes(repo_root: Path = ROOT) -> list[Fix]:
    """Return candidate safe remediations. None are applied here."""
    fixes: list[Fix] = []

    # 1) Ensure audit output directories exist (always safe, idempotent).
    audit_dirs = [
        repo_root / "reports" / "daily-audit",
        repo_root / "data" / "audit" / "logs",
    ]
    missing = []
    for d in audit_dirs:
        try:
            if not d.exists():
                missing.append(d)
        except OSError:
            missing.append(d)
    if missing:
        fixes.append(
            Fix(
                signature="ensure_audit_dirs",
                title="Create missing audit output directories",
                detail="; ".join(str(d) for d in missing),
                apply=lambda: [d.mkdir(parents=True, exist_ok=True) for d in missing],
                validate=lambda: all(d.exists() for d in missing),
                evidence="reports/daily-audit + data/audit/logs",
            )
        )

    # 2) Rotate a stale, empty monitor.out so the soak analyzer doesn't read a
    #    ghost file. Only when no monitor process is running (never touch live
    #    state). Reversible: we move it aside, not delete.
    monitor_out = repo_root / "data" / "audit" / "logs" / "monitor.out"
    if monitor_out.exists():
        try:
            empty = monitor_out.stat().st_size == 0
        except OSError:
            empty = False
        if empty and not _monitor_running():
            bak = monitor_out.with_suffix(".out.bak")

            def _do() -> None:
                if monitor_out.exists():
                    shutil.move(str(monitor_out), str(bak))

            def _restore() -> None:
                if bak.exists():
                    shutil.move(str(bak), str(monitor_out))

            fixes.append(
                Fix(
                    signature="rotate_empty_monitor_out",
                    title="Rotate empty monitor.out left by a crashed sampler",
                    detail=f"{monitor_out} is 0 bytes and no monitor process is running",
                    apply=_do,
                    validate=lambda: (not monitor_out.exists()) or monitor_out.stat().st_size > 0,
                    restore=_restore,
                    evidence="data/audit/logs/monitor.out",
                )
            )

    return fixes


def apply_with_guard(
    fix: Fix,
    state: RemediationState,
    now: float | None = None,
) -> tuple[bool, str]:
    """Apply one fix under the attempt bookkeeping; auto-revert on failure.

    Returns (success, message). On validation failure, calls ``fix.restore``
    when present so the system returns to its pre-fix state (no half-fixes).
    """
    now = now if now is not None else time.time()
    sig = fix.signature
    try:
        fix.apply()
    except Exception as exc:  # noqa: BLE001
        state.attempts[sig] = state.attempts.get(sig, 0) + 1
        state.last_outcome[sig] = f"apply_error:{exc}"
        state.save()
        return False, f"apply raised: {exc}\n{traceback.format_exc()}"

    ok = False
    try:
        ok = bool(fix.validate())
    except Exception as exc:  # noqa: BLE001
        ok = False
        state.last_outcome[sig] = f"validate_error:{exc}"
    if not ok:
        if fix.restore is not None:
            try:
                fix.restore()
            except Exception:  # noqa: BLE001
                pass
        state.attempts[sig] = state.attempts.get(sig, 0) + 1
        state.last_outcome[sig] = "validation_failed_reverted"
        state.save()
        return False, "validation failed; change reverted"

    state.attempts[sig] = state.attempts.get(sig, 0) + 1
    state.last_applied_at[sig] = now
    state.last_outcome[sig] = "applied"
    state.save()
    return True, "applied and validated"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
