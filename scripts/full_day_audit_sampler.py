#!/usr/bin/env python3
"""Periodic local soak sampler for full-day application audit.

Writes JSONL samples under data/audit/samples/ without printing secrets.
Authenticates to the dashboard API via TOTP when credentials are present.
"""
from __future__ import annotations

import json
import os
import re
import signal
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import httpx
import psutil

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "data" / "audit" / "samples"
LOG_PATH = ROOT / "data" / "audit" / "sampler.log"
MONITOR_LOG = ROOT / "data" / "audit" / "logs" / "monitor.out"
TOKEN_PATH = ROOT / "data" / "audit" / ".dashboard_token.txt"
TOTP_PATH = ROOT / "data" / "audit" / "totp_secret.txt"
INTERVAL = float(os.environ.get("AUDIT_SAMPLE_INTERVAL_SEC", "60"))
API = os.environ.get("AUDIT_API_BASE", "http://127.0.0.1:8080")
stop = False
_session_token: str | None = None
_session_expires_at: float = 0.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(msg: str) -> None:
    line = f"{_now()} {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _handle(sig, frame):  # noqa: ARG001
    global stop
    stop = True


def _rss_for(cmdline_substr: str) -> dict | None:
    for proc in psutil.process_iter(["pid", "name", "cmdline", "memory_info", "cpu_percent", "create_time"]):
        try:
            cmd = " ".join(proc.info.get("cmdline") or [])
            if cmdline_substr in cmd:
                mi = proc.info.get("memory_info")
                return {
                    "pid": proc.info["pid"],
                    "rss_mb": round((mi.rss if mi else 0) / (1024 * 1024), 1),
                    "cpu_percent": proc.cpu_percent(interval=0.0),
                    "uptime_s": int(time.time() - (proc.info.get("create_time") or time.time())),
                }
        except (psutil.Error, TypeError):
            continue
    return None


def _tail_errors(path: Path, n: int = 500) -> dict:
    if not path.exists():
        return {"exists": False}
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()[-n:]
    patterns = {
        "error": re.compile(r"\bERROR\b|Traceback|Exception", re.I),
        "warning": re.compile(r"\bWARNING\b", re.I),
        "reject": re.compile(r"REJECT|VETO|BLOCK|DENIED|PARTIAL_EXPOSURE", re.I),
        "trade": re.compile(r"EXECUTE|FILL|OPEN_PAIR|CLOSE_PAIR|shadow|place_market", re.I),
        "oom": re.compile(r"MemoryError|OOM|prune|MEMORY_", re.I),
        "cointegration": re.compile(r"cointegrat|bench|quarantine|Kalman", re.I),
        "scan": re.compile(r"Iteration Complete|SCAN \[", re.I),
    }
    counts = {k: 0 for k in patterns}
    last = {k: None for k in patterns}
    for line in lines:
        clean = re.sub(r"\x1b\[[0-9;]*m", "", line)
        for k, rx in patterns.items():
            if rx.search(clean):
                counts[k] += 1
                last[k] = clean[-240:]
    return {"exists": True, "tail_lines": len(lines), "counts": counts, "last": last}


def _login(client: httpx.Client) -> str | None:
    global _session_token, _session_expires_at
    if _session_token and time.time() < _session_expires_at - 60:
        return _session_token
    if not TOKEN_PATH.exists() or not TOTP_PATH.exists():
        return None
    token = TOKEN_PATH.read_text(encoding="utf-8").strip()
    secret = TOTP_PATH.read_text(encoding="utf-8").strip()
    # Prefer in-app TOTP helper so windows match verify_setup.
    sys.path.insert(0, str(ROOT))
    from src.services.dashboard_service import dashboard_service

    otp = dashboard_service.totp.totp_token(secret)
    r = client.post(
        "/api/auth/login",
        json={"security_token": token, "otp_token": otp, "actor": "full-day-audit"},
        timeout=15.0,
    )
    if not r.is_success:
        _log(f"login_failed status={r.status_code} body={r.text[:160]}")
        return None
    data = r.json()
    _session_token = data.get("session_token")
    # Session lasts ~12h per login response; refresh hourly anyway.
    _session_expires_at = time.time() + 3600
    return _session_token


def _summarize_pairs(data: object) -> dict:
    if isinstance(data, list):
        return {
            "count": len(data),
            "ids": [(p.get("id") if isinstance(p, dict) else str(p)) for p in data[:30]],
        }
    if isinstance(data, dict):
        active = data.get("active") or data.get("pairs") or data.get("items")
        if isinstance(active, list):
            return {
                "count": len(active),
                "ids": [(p.get("id") if isinstance(p, dict) else str(p)) for p in active[:30]],
                "keys": list(data.keys())[:20],
            }
        return {"keys": list(data.keys())[:30]}
    return {"type": type(data).__name__}


def _api_snapshot(client: httpx.Client) -> dict:
    out: dict = {"authenticated": False}
    session = _login(client)
    headers = {"X-Dashboard-Session": session} if session else {}
    out["authenticated"] = bool(session)
    paths = (
        "/api/system/health",
        "/api/pairs",
        "/api/positions",
        "/api/stats/summary",
        "/api/approvals/pending",
        "/api/config",
    )
    for path in paths:
        try:
            r = client.get(path, headers=headers, timeout=12.0)
            entry: dict = {"status": r.status_code, "ok": r.is_success}
            if r.is_success and "json" in r.headers.get("content-type", ""):
                data = r.json()
                if path.endswith("/pairs"):
                    entry["summary"] = _summarize_pairs(data)
                elif path.endswith("/runtime") and isinstance(data, dict):
                    entry["summary"] = {
                        k: data.get(k)
                        for k in (
                            "execution_mode",
                            "paper_trading",
                            "broker_paper_trading",
                            "dev_mode",
                            "live_capital_danger",
                            "pair_discovery_enabled",
                            "monitor_entry_zscore",
                            "active_pairs",
                        )
                    }
                elif path.endswith("/health") and isinstance(data, dict):
                    entry["body"] = data
                elif isinstance(data, (list, dict)):
                    entry["n"] = len(data) if isinstance(data, list) else len(data.keys())
            elif not r.is_success:
                entry["body"] = r.text[:160]
            out[path] = entry
        except Exception as exc:  # noqa: BLE001
            out[path] = {"error": f"{type(exc).__name__}: {exc}"}
    return out


def sample_once() -> dict:
    monitor = _rss_for("src/monitor.py") or _rss_for("src.monitor")
    sample = {
        "ts": _now(),
        "monitor": monitor,
        "host": {
            "cpu_percent": psutil.cpu_percent(interval=0.2),
            "mem_percent": psutil.virtual_memory().percent,
            "mem_available_mb": round(psutil.virtual_memory().available / (1024 * 1024), 1),
        },
        "log_tail": _tail_errors(MONITOR_LOG),
    }
    try:
        with httpx.Client(base_url=API) as client:
            sample["api"] = _api_snapshot(client)
    except Exception as exc:  # noqa: BLE001
        sample["api"] = {"error": f"{type(exc).__name__}: {exc}"}
    return sample


def main() -> int:
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = SAMPLE_DIR / f"soak_{day}.jsonl"
    _log(f"sampler start interval={INTERVAL}s out={out_path}")
    while not stop:
        try:
            s = sample_once()
            with out_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(s, default=str) + "\n")
            mon = s.get("monitor") or {}
            api = s.get("api") or {}
            health = (api.get("/api/system/health") or {}).get("status")
            _log(
                f"sample rss_mb={mon.get('rss_mb')} auth={api.get('authenticated')} "
                f"health={health} uptime_s={mon.get('uptime_s')}"
            )
        except Exception:  # noqa: BLE001
            _log("sample_failed\n" + traceback.format_exc())
        for _ in range(int(INTERVAL * 10)):
            if stop:
                break
            time.sleep(0.1)
    _log("sampler stop")
    return 0


if __name__ == "__main__":
    sys.exit(main())
