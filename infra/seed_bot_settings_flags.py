#!/usr/bin/env python3
"""Write mode flags into /persist/bot_settings.json without touching secrets."""
from __future__ import annotations

import json
from pathlib import Path

env: dict[str, str] = {}
for raw in Path("/env.trading").read_text(encoding="utf-8", errors="replace").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    env[key.strip()] = value.strip().strip('"').strip("'")

path = Path("/persist/bot_settings.json")
existing: dict = {}
if path.exists():
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            existing = loaded
    except Exception:
        existing = {}

for key in ("PAPER_TRADING", "LIVE_CAPITAL_DANGER", "DEV_MODE"):
    if key not in existing and key in env:
        existing[key] = env[key].lower() == "true"

path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
print("bot_settings_keys=" + ",".join(sorted(existing)))
