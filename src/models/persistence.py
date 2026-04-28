import sqlite3
import json
import logging
import os
from typing import Dict, Any, Optional, List
from src.config import settings

logger = logging.getLogger(__name__)

class PersistenceManager:
    def __init__(self, db_path: Optional[str] = None):
        # Fallback to a default if settings doesn't have it or passed as None
        self.db_path = db_path or getattr(settings, "DB_PATH", "logs/trading_bot.db")
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._init_db()

    def _init_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            # Legacy tables used by SECService, AgentLogService, DCA, etc.
            conn.execute("CREATE TABLE IF NOT EXISTS cik_mapping (ticker TEXT PRIMARY KEY, cik TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS thought_journal (signal_id TEXT PRIMARY KEY, bull TEXT, bear TEXT, news TEXT, verdict TEXT, shap TEXT, fundamental_impact REAL, sec_ref TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
            conn.execute("CREATE TABLE IF NOT EXISTS events (level TEXT, source TEXT, message TEXT, metadata TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
            conn.execute("CREATE TABLE IF NOT EXISTS dca_schedules (id TEXT PRIMARY KEY, amount REAL, frequency TEXT, strategy_id TEXT, next_run TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS portfolio_strategies (strategy_id TEXT, ticker TEXT, weight REAL, risk_profile TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS system_state (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS cash_sweeps (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT, amount REAL, ticker TEXT, balance_after REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS config_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor TEXT NOT NULL,
                    key TEXT NOT NULL,
                    old_value TEXT,
                    new_value TEXT,
                    requires_2fa INTEGER NOT NULL DEFAULT 0,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dashboard_auth_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"PersistenceManager init error: {e}")

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def load_cik_mapping(self, ticker: str) -> Optional[str]:
        conn = self._get_connection()
        row = conn.execute("SELECT cik FROM cik_mapping WHERE ticker = ?", (ticker,)).fetchone()
        conn.close()
        return row[0] if row else None

    def get_cik_mappings(self, tickers: list[str]) -> Dict[str, str]:
        if not tickers:
            return {}
        conn = self._get_connection()
        placeholders = ', '.join(['?'] * len(tickers))
        cursor = conn.execute(f"SELECT ticker, cik FROM cik_mapping WHERE ticker IN ({placeholders})", tickers)
        results = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()
        return results

    def save_cik_mapping(self, ticker: str, cik: str):
        conn = self._get_connection()
        conn.execute("INSERT OR REPLACE INTO cik_mapping VALUES (?, ?)", (ticker, cik))
        conn.commit()
        conn.close()

    def save_cik_mappings(self, mapping: Dict[str, str]):
        if not mapping:
            return
        conn = self._get_connection()
        conn.executemany("INSERT OR REPLACE INTO cik_mapping VALUES (?, ?)", list(mapping.items()))
        conn.commit()
        conn.close()

    def log_thought(self, signal_id: str, **kwargs):
        conn = self._get_connection()
        # Simplified insert for legacy support
        verdict = kwargs.get('verdict', '')
        conn.execute("INSERT OR REPLACE INTO thought_journal (signal_id, verdict) VALUES (?, ?)", (signal_id, verdict))
        conn.commit()
        conn.close()

    def log_event(self, level: str, source: str, message: str, metadata: Optional[Dict] = None):
        conn = self._get_connection()
        conn.execute("INSERT INTO events (level, source, message, metadata) VALUES (?, ?, ?, ?)", 
                     (level, source, message, json.dumps(metadata) if metadata else None))
        conn.commit()
        conn.close()

    def get_system_state(self, key: str, default: Any = None) -> Any:
        conn = self._get_connection()
        row = conn.execute("SELECT value FROM system_state WHERE key = ?", (key,)).fetchone()
        conn.close()
        return row[0] if row else default

    def set_system_state(self, key: str, value: Any):
        conn = self._get_connection()
        conn.execute("INSERT OR REPLACE INTO system_state VALUES (?, ?)", (key, str(value)))
        conn.commit()
        conn.close()
        
    def save_portfolio_strategy(self, strategy_id: str, ticker: str, weight: float, risk_profile: str):
        conn = self._get_connection()
        conn.execute("INSERT INTO portfolio_strategies (strategy_id, ticker, weight, risk_profile) VALUES (?, ?, ?, ?)", 
                     (strategy_id, ticker, weight, risk_profile))
        conn.commit()
        conn.close()
        
    def save_dca_schedule(self, amount: float, frequency: str, strategy_id: str, next_run: Any):
        import uuid
        conn = self._get_connection()
        conn.execute("INSERT INTO dca_schedules (id, amount, frequency, strategy_id, next_run) VALUES (?, ?, ?, ?, ?)", 
                     (str(uuid.uuid4()), amount, frequency, strategy_id, next_run.isoformat() if hasattr(next_run, 'isoformat') else str(next_run)))
        conn.commit()
        conn.close()

    def save_cash_sweep(self, sweep_type: str, amount: float, ticker: str, balance_after: float):
        conn = self._get_connection()
        conn.execute("INSERT INTO cash_sweeps (type, amount, ticker, balance_after) VALUES (?, ?, ?, ?)", 
                     (sweep_type, amount, ticker, balance_after))
        conn.commit()
        conn.close()

    def log_config_change(
        self,
        actor: str,
        key: str,
        old_value: Any,
        new_value: Any,
        requires_2fa: bool = False,
    ) -> None:
        conn = self._get_connection()
        conn.execute(
            """
            INSERT INTO config_audit_log (actor, key, old_value, new_value, requires_2fa)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                actor,
                key,
                json.dumps(old_value),
                json.dumps(new_value),
                1 if requires_2fa else 0,
            ),
        )
        conn.commit()
        conn.close()

    def get_recent_config_changes(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        rows = conn.execute(
            """
            SELECT actor, key, old_value, new_value, requires_2fa, timestamp
            FROM config_audit_log
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        conn.close()
        result = []
        for row in rows:
            result.append(
                {
                    "actor": row["actor"],
                    "key": row["key"],
                    "old_value": json.loads(row["old_value"]) if row["old_value"] else None,
                    "new_value": json.loads(row["new_value"]) if row["new_value"] else None,
                    "requires_2fa": bool(row["requires_2fa"]),
                    "timestamp": row["timestamp"],
                }
            )
        return result

    def set_dashboard_auth_state(self, key: str, value: Any) -> None:
        conn = self._get_connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO dashboard_auth_state (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
            (key, json.dumps(value)),
        )
        conn.commit()
        conn.close()

    def get_dashboard_auth_state(self, key: str, default: Any = None) -> Any:
        conn = self._get_connection()
        row = conn.execute(
            "SELECT value FROM dashboard_auth_state WHERE key = ?",
            (key,),
        ).fetchone()
        conn.close()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except Exception:
            return default

    def get_recent_events(self, source: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        if source:
            rows = conn.execute(
                """
                SELECT level, source, message, metadata, timestamp
                FROM events
                WHERE source = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (source, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT level, source, message, metadata, timestamp
                FROM events
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        conn.close()
        result = []
        for row in rows:
            result.append(
                {
                    "level": row["level"],
                    "source": row["source"],
                    "message": row["message"],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
                    "timestamp": row["timestamp"],
                }
            )
        return result

    # Dashboard polling stubs (Legacy)
    def get_daily_invested(self, date_str: str, is_shadow: bool = True) -> float: return 0.0
    def get_total_revenue(self, is_shadow: bool = True) -> float: return 0.0
    def get_current_investment(self, is_shadow: bool = True) -> float: return 0.0
    def get_daily_pnl(self, date_str: str, is_shadow: bool = True) -> float: return 0.0
