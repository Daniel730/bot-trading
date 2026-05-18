#!/usr/bin/env python3
"""Run the paper-startup env repair, validation, and dependency preflight."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import bug_hunt_audit, repair_paper_env, validate_deploy_env


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

    dependency_errors = bug_hunt_audit.check_paper_startup_dependencies(env_file)
    if dependency_errors:
        print("Paper startup dependency preflight failed:")
        for error in dependency_errors:
            print(f"- {error}")
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
