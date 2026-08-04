"""Idempotent dual-database schema ensure (Postgres + SQLite).

Safe for bot-server: additive migrations only — never DROP tables, truncate, or
wipe Docker volumes. Run via entrypoint, cron, or manually after image pulls:

    PYTHONPATH=/app python scripts/init_db.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.config import settings  # noqa: E402
from src.models.persistence import PersistenceManager  # noqa: E402
from src.services.persistence_service import persistence_service  # noqa: E402


async def ensure_postgres() -> None:
    print("Ensuring PostgreSQL schema (additive migrations)...")
    await persistence_service.init_db()
    print("✓ PostgreSQL schema OK.")


def ensure_sqlite() -> None:
    print(f"Ensuring SQLite schema at {settings.DB_PATH}...")
    # Construction runs CREATE TABLE IF NOT EXISTS + ensure_sqlite_columns.
    PersistenceManager(settings.DB_PATH)
    print("✓ SQLite schema OK.")


async def main() -> None:
    print("Initializing Dual-Database Schema (PostgreSQL + SQLite)...")
    print("Mode: additive only (no volume wipe / no DROP).")
    try:
        await ensure_postgres()
    except Exception as e:
        print(f"✗ Failed to initialize PostgreSQL: {e}")
        sys.exit(1)
    try:
        ensure_sqlite()
    except Exception as e:
        print(f"✗ Failed to initialize SQLite: {e}")
        sys.exit(1)
    print("✓ Dual-database schema ensure complete.")


if __name__ == "__main__":
    asyncio.run(main())
