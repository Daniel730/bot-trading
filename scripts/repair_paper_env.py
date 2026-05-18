#!/usr/bin/env python3
"""Repair non-secret .env keys needed for host-side paper startup."""

from __future__ import annotations

import argparse
from pathlib import Path


PAPER_STARTUP_VALUES = {
    "PAPER_TRADING": "true",
    "LIVE_CAPITAL_DANGER": "false",
    "REDIS_HOST": "localhost",
    "REDIS_PORT": "6379",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "5433",
}


def repair_env_text(text: str) -> tuple[str, list[str]]:
    lines = text.splitlines()
    had_trailing_newline = text.endswith(("\n", "\r\n"))
    seen: set[str] = set()
    changed: list[str] = []
    repaired: list[str] = []

    for line in lines:
        stripped = line.lstrip()
        export_prefix = "export " if stripped.startswith("export ") else ""
        assignment = stripped[len(export_prefix) :] if export_prefix else stripped
        if "=" not in assignment or stripped.startswith("#"):
            repaired.append(line)
            continue

        key, _value = assignment.split("=", 1)
        key = key.strip()
        if key not in PAPER_STARTUP_VALUES:
            repaired.append(line)
            continue

        seen.add(key)
        leading = line[: len(line) - len(stripped)]
        new_line = f"{leading}{export_prefix}{key}={PAPER_STARTUP_VALUES[key]}"
        if line != new_line:
            changed.append(key)
        repaired.append(new_line)

    for key, value in PAPER_STARTUP_VALUES.items():
        if key not in seen:
            repaired.append(f"{key}={value}")
            changed.append(key)

    new_text = "\n".join(repaired)
    if had_trailing_newline or text:
        new_text += "\n"
    return new_text, changed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Repair non-secret .env keys for host-side paper startup."
    )
    parser.add_argument("env_file", type=Path, help="Path to the local .env file")
    args = parser.parse_args()

    if not args.env_file.exists():
        print(f"Paper env repair failed: {args.env_file} does not exist.")
        return 1

    repaired, changed = repair_env_text(args.env_file.read_text(encoding="utf-8"))
    if changed:
        args.env_file.write_text(repaired, encoding="utf-8")
        print("Updated paper startup keys: " + ", ".join(sorted(set(changed))))
    else:
        print("Paper startup env already OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
