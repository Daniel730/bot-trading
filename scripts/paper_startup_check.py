#!/usr/bin/env python3
"""Run the paper-startup env repair, validation, and dependency preflight."""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import bug_hunt_audit, repair_paper_env, validate_deploy_env
from src.services.persistence_service import persistence_service


ACTION_CONTAINER_SERVICES = ("bot", "mcp-server", "execution-engine", "sec-worker", "frontend")


def check_running_action_containers() -> list[str]:
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []

    running = []
    for raw_name in result.stdout.splitlines():
        name = raw_name.strip()
        if any(name.endswith(f"-{service}-1") for service in ACTION_CONTAINER_SERVICES):
            running.append(name)
    return running


def check_unresolved_reconciliation_rows() -> list[dict]:
    return asyncio.run(persistence_service.get_startup_reconciliation_rows(limit=5))


def count_unresolved_reconciliation_rows() -> int:
    return asyncio.run(persistence_service.count_startup_reconciliation_rows())


def run_check(env_file: Path) -> int:
    if not env_file.exists():
        print(f"Paper startup check failed: {env_file} does not exist.")
        return 1

    repaired, changed = repair_paper_env.repair_env_text(env_file.read_text(encoding="utf-8"))
    if changed:
        env_file.write_text(repaired, encoding="utf-8")
        print("Updated paper startup keys: " + ", ".join(sorted(set(changed))))
    else:
        print("Paper startup env already OK.")

    validation_errors = validate_deploy_env.validate(validate_deploy_env.load_env(env_file))
    if validation_errors:
        print("Paper startup validation failed:")
        for error in validation_errors:
            print(f"- {error}")
        return 1

    running_action_containers = check_running_action_containers()
    if running_action_containers:
        print("Paper startup container guard failed:")
        for container in running_action_containers:
            print(f"- {container} is already running; stop app/trading containers before paper startup.")
        return 1

    dependency_errors = bug_hunt_audit.check_paper_startup_dependencies(env_file)
    if dependency_errors:
        print("Paper startup dependency preflight failed:")
        for error in dependency_errors:
            print(f"- {error}")
        return 1

    try:
        unresolved_count = count_unresolved_reconciliation_rows()
        unresolved_rows = check_unresolved_reconciliation_rows()
    except Exception as exc:
        print("Paper startup reconciliation guard failed:")
        print(f"- Could not verify unresolved ledger rows: {exc}")
        return 1
    if unresolved_count > 0:
        print("Paper startup reconciliation guard failed:")
        print(f"- {unresolved_count} unresolved ledger rows require reconciliation.")
        for row in unresolved_rows:
            print(
                "- unresolved ledger row "
                f"id={row.get('id')} order_id={row.get('order_id')} "
                f"ticker={row.get('ticker')} status={row.get('status')} "
                f"venue={row.get('venue')}"
            )
        return 1

    print("Paper startup check passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Repair and validate a local .env before paper startup."
    )
    parser.add_argument("env_file", type=Path, help="Path to the local .env file")
    args = parser.parse_args()
    return run_check(args.env_file)


if __name__ == "__main__":
    raise SystemExit(main())
