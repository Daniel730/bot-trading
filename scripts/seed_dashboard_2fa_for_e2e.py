#!/usr/bin/env python3
"""Seed dashboard 2FA for optional local Playwright runs against a real paper API.

Paper-safe: does not touch brokerage. Writes TOTP secret + one backup code to
stdout (never commit). Requires PYTHONPATH=. and a configured .env.

Usage:
  PYTHONPATH=. python scripts/seed_dashboard_2fa_for_e2e.py
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    from src.services.dashboard_service import dashboard_service

    totp = dashboard_service.totp
    status = totp.public_status()
    if status.get("enabled"):
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": "2FA already enabled — use an existing TOTP/backup code for e2e",
                    "hint": "Do not wipe production auth state from this script.",
                }
            )
        )
        return 2

    setup = totp.initiate_setup()
    secret = setup["secret"]
    backup_codes = setup.get("backup_codes") or []
    token = totp.totp_token(secret)
    assert totp.verify_setup(token), "failed to enable 2FA after initiate_setup"
    print(
        json.dumps(
            {
                "ok": True,
                "secret": secret,
                "backup_code": backup_codes[0] if backup_codes else None,
                "note": "Use DASHBOARD_TOKEN from .env + backup_code (or live TOTP) in Playwright against a local paper stack.",
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
