"""Additive, volume-safe schema migrations for Postgres + SQLite.

create_all only creates missing tables — it never adds columns to existing ones.
These helpers are idempotent (IF NOT EXISTS / PRAGMA checks) and never DROP
tables, truncate data, or recreate volumes.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Iterable, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)

# (table, column, postgres DDL type fragment after column name)
POSTGRES_ADDITIVE_COLUMNS: Sequence[tuple[str, str, str]] = (
    ("trade_ledger", "order_id", "VARCHAR(100)"),
    ("trade_ledger", "signal_id", "UUID"),
    ("trade_ledger", "fee", "NUMERIC(20, 10) DEFAULT 0.0"),
    ("trade_ledger", "venue", "VARCHAR(20) DEFAULT 'ALPACA'"),
    ("trade_ledger", "closed_at", "TIMESTAMP WITH TIME ZONE"),
    ("trade_ledger", "metadata", "JSON"),
    ("trade_ledger", "latency_rtt_ns", "INTEGER"),
    ("trade_ledger", "clock_sync_status", "BOOLEAN"),
    # Lane tags also live in metadata JSON; first-class columns enable filtering
    # and survive metadata-only reader drift on older bot-server volumes.
    ("trade_ledger", "execution_lane", "VARCHAR(20)"),
    ("trade_ledger", "is_shadow", "BOOLEAN"),
    ("trading_pairs", "hedge_ratio", "NUMERIC(20, 10) DEFAULT 0.0"),
    ("trading_pairs", "is_cointegrated", "BOOLEAN DEFAULT FALSE"),
    ("trading_pairs", "status", "VARCHAR(20) DEFAULT 'Active'"),
    ("universe_candidates", "hedge_ratio", "NUMERIC(20, 10) DEFAULT 0.0"),
    ("trade_journal", "signal_id", "UUID"),
    ("trade_journal", "metrics_at_entry", "JSON"),
    ("agent_reasoning", "trace_id", "UUID"),
)

POSTGRES_INDEXES: Sequence[str] = (
    "CREATE INDEX IF NOT EXISTS ix_trade_ledger_venue ON trade_ledger (venue)",
    "CREATE INDEX IF NOT EXISTS ix_trade_ledger_closed_at ON trade_ledger (closed_at)",
    "CREATE INDEX IF NOT EXISTS ix_trade_ledger_signal_id ON trade_ledger (signal_id)",
    "CREATE INDEX IF NOT EXISTS ix_trade_ledger_execution_lane ON trade_ledger (execution_lane)",
    "CREATE INDEX IF NOT EXISTS ix_trade_ledger_is_shadow ON trade_ledger (is_shadow)",
    "CREATE INDEX IF NOT EXISTS ix_trade_journal_signal_id ON trade_journal (signal_id)",
    "CREATE INDEX IF NOT EXISTS ix_agent_reasoning_trace_id ON agent_reasoning (trace_id)",
)

# Backfill first-class lane columns from legacy metadata JSON (no-op when already set).
POSTGRES_BACKFILLS: Sequence[str] = (
    """
    UPDATE trade_ledger
    SET is_shadow = CASE
            WHEN metadata->>'is_shadow' IN ('true', 'True', '1') THEN TRUE
            WHEN metadata->>'is_shadow' IN ('false', 'False', '0') THEN FALSE
            ELSE is_shadow
        END
    WHERE is_shadow IS NULL
      AND metadata IS NOT NULL
      AND metadata ? 'is_shadow'
    """,
    """
    UPDATE trade_ledger
    SET execution_lane = NULLIF(metadata->>'execution_lane', '')
    WHERE execution_lane IS NULL
      AND metadata IS NOT NULL
      AND metadata ? 'execution_lane'
    """,
    """
    UPDATE trade_ledger
    SET execution_lane = 'SHADOW'
    WHERE is_shadow IS TRUE
      AND (execution_lane IS NULL OR execution_lane = '')
    """,
)

# table -> column -> SQLite type fragment
SQLITE_ADDITIVE_COLUMNS: dict[str, dict[str, str]] = {
    "thought_journal": {
        "bull": "TEXT",
        "bear": "TEXT",
        "news": "TEXT",
        "verdict": "TEXT",
        "shap": "TEXT",
        "fundamental_impact": "REAL",
        "sec_ref": "TEXT",
        "timestamp": "DATETIME DEFAULT CURRENT_TIMESTAMP",
    },
    "logs": {
        "signal_id": "TEXT",
        "level": "TEXT",
        "source": "TEXT",
        "message": "TEXT",
        "metadata": "TEXT",
        "timestamp": "DATETIME DEFAULT CURRENT_TIMESTAMP",
    },
    "events": {
        "level": "TEXT",
        "source": "TEXT",
        "message": "TEXT",
        "metadata": "TEXT",
        "timestamp": "DATETIME DEFAULT CURRENT_TIMESTAMP",
    },
    "dca_schedules": {
        "amount": "REAL",
        "frequency": "TEXT",
        "strategy_id": "TEXT",
        "next_run": "TEXT",
    },
    "config_audit_log": {
        "actor": "TEXT",
        "key": "TEXT",
        "old_value": "TEXT",
        "new_value": "TEXT",
        "requires_2fa": "INTEGER NOT NULL DEFAULT 0",
        "timestamp": "DATETIME DEFAULT CURRENT_TIMESTAMP",
    },
    "dashboard_auth_state": {
        "value": "TEXT NOT NULL DEFAULT '{}'",
        "updated_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
    },
}


async def _exec_best_effort(conn: AsyncConnection, sql: str, *, label: str) -> None:
    try:
        await conn.execute(text(sql))
    except Exception as exc:  # noqa: BLE001 — additive migrations must not abort startup
        logger.warning("schema_migration skipped (%s): %s", label, exc)


async def apply_postgres_migrations(
    conn: AsyncConnection,
    *,
    order_status_values: Iterable[str] | None = None,
) -> None:
    """Apply idempotent additive Postgres migrations on an open connection."""
    if order_status_values:
        for status in order_status_values:
            await _exec_best_effort(
                conn,
                f"ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS '{status}'",
                label=f"orderstatus:{status}",
            )

    for table, column, col_type in POSTGRES_ADDITIVE_COLUMNS:
        await _exec_best_effort(
            conn,
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}",
            label=f"{table}.{column}",
        )

    for index_sql in POSTGRES_INDEXES:
        await _exec_best_effort(conn, index_sql, label="index")

    for backfill_sql in POSTGRES_BACKFILLS:
        await _exec_best_effort(conn, backfill_sql, label="lane_backfill")


def sqlite_existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    # PRAGMA table_info: cid, name, type, notnull, dflt_value, pk
    return {row[1] for row in rows}


def ensure_sqlite_columns(conn: sqlite3.Connection) -> list[str]:
    """Add missing columns on existing SQLite tables. Returns applied DDL labels."""
    applied: list[str] = []
    for table, columns in SQLITE_ADDITIVE_COLUMNS.items():
        existing = sqlite_existing_columns(conn, table)
        if not existing:
            # Table not created yet — CREATE TABLE IF NOT EXISTS handles full DDL.
            continue
        for column, col_type in columns.items():
            if column in existing:
                continue
            ddl = f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
            conn.execute(ddl)
            applied.append(f"{table}.{column}")
            logger.info("SQLite schema: added %s.%s", table, column)
    return applied
