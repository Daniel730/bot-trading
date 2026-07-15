#!/usr/bin/env python3
"""Poll dashboard approvals and approve them (agent / operator helper).

Auth uses DASHBOARD_TOKEN only (no 2FA session):

  GET  /api/approvals/pending?token=...
  POST /api/approvals/{cid}/approve?token=...

Examples:
  python scripts/auto_approve_pending.py --once
  python scripts/auto_approve_pending.py --interval 5 --base-url http://127.0.0.1:8082
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import json


def _request(method: str, url: str, timeout: float = 15.0) -> dict:
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-approve pending Telegram/dashboard trades")
    parser.add_argument("--base-url", default=os.environ.get("BOT_API_BASE_URL", "http://127.0.0.1:8082"))
    parser.add_argument("--token", default=os.environ.get("DASHBOARD_TOKEN", ""))
    parser.add_argument("--interval", type=float, default=5.0, help="Seconds between polls")
    parser.add_argument("--once", action="store_true", help="Poll once and exit")
    parser.add_argument("--dry-run", action="store_true", help="List pending without approving")
    args = parser.parse_args()

    token = (args.token or "").strip().strip('"').strip("'")
    if not token:
        print("DASHBOARD_TOKEN is required (env or --token)", file=sys.stderr)
        return 2

    base = args.base_url.rstrip("/")
    print(f"Polling {base}/api/approvals/pending every {args.interval}s")

    while True:
        qs = urllib.parse.urlencode({"token": token})
        try:
            payload = _request("GET", f"{base}/api/approvals/pending?{qs}")
        except urllib.error.HTTPError as exc:
            print(f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')}", file=sys.stderr)
            if args.once:
                return 1
            time.sleep(args.interval)
            continue
        except Exception as exc:
            print(f"Poll error: {exc}", file=sys.stderr)
            if args.once:
                return 1
            time.sleep(args.interval)
            continue

        pending = payload.get("pending") or []
        if not pending:
            print("No pending approvals")
        for item in pending:
            cid = item.get("correlation_id")
            summary = (item.get("summary") or "").replace("\n", " | ")[:200]
            print(f"PENDING {cid}: {summary}")
            if args.dry_run or not cid:
                continue
            try:
                result = _request("POST", f"{base}/api/approvals/{cid}/approve?{qs}")
                print(f"APPROVED {cid}: {result}")
            except Exception as exc:
                print(f"Approve failed {cid}: {exc}", file=sys.stderr)

        if args.once:
            return 0
        time.sleep(max(1.0, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
