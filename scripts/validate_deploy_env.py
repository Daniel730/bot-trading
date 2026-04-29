#!/usr/bin/env python3
"""Validate deployment-only secrets without printing their values."""

from __future__ import annotations

import argparse
from pathlib import Path


BLOCKED_POSTGRES_PASSWORDS = {"bot_pass", "postgres", "password", "changeme"}
BLOCKED_DASHBOARD_TOKENS = {"arbi-elite-2026", "dashboard-token", "changeme"}


def _clean_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value.strip()


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = _clean_value(value)
    return values


def validate(values: dict[str, str]) -> list[str]:
    errors: list[str] = []

    postgres_password = values.get("POSTGRES_PASSWORD", "")
    if not postgres_password:
        errors.append("POSTGRES_PASSWORD is missing or empty.")
    elif postgres_password.lower() in BLOCKED_POSTGRES_PASSWORDS:
        errors.append("POSTGRES_PASSWORD is still a blocked default value.")

    dashboard_token = values.get("DASHBOARD_TOKEN", "")
    if not dashboard_token:
        errors.append("DASHBOARD_TOKEN is missing or empty.")
    elif dashboard_token in BLOCKED_DASHBOARD_TOKENS:
        errors.append("DASHBOARD_TOKEN is still a blocked default value.")
    elif len(dashboard_token) < 16:
        errors.append("DASHBOARD_TOKEN must be at least 16 characters long.")

    database_url = values.get("DATABASE_URL", "")
    if database_url and "bot_pass" in database_url:
        errors.append("DATABASE_URL still contains the default Postgres password.")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate deployment env secrets before Docker Compose starts services."
    )
    parser.add_argument("env_file", type=Path, help="Path to the deployment .env file")
    args = parser.parse_args()

    if not args.env_file.exists():
        print(f"Deploy environment validation failed: {args.env_file} does not exist.")
        return 1

    errors = validate(load_env(args.env_file))
    if errors:
        print("Deploy environment validation failed:")
        for error in errors:
            print(f"- {error}")
        print(
            "Fix the persistent deployment env file with strong values before starting "
            "containers. If POSTGRES_PASSWORD changes for an existing Postgres volume, "
            "rotate the database user's password too."
        )
        return 1

    print("Deploy environment OK: required secrets are set and non-default.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
