import sqlite3
import json
import logging
import os
import uuid
from typing import Dict, Any, Optional, List
from src.config import settings

logger = logging.getLogger(__name__)

class PersistenceManager:
    def __init__(self, db_path: Optional[str] = None):
        # Fallback to a default if settings doesn't have it or passed as None
        # Use an absolute path for the default to avoid FileNotFoundError on Windows if CWD changes.
        default_db = os.path.join(os.getcwd(), "logs", "trading_bot.db")
        self.db_path = db_path or getattr(settings, "DB_PATH", default_db)
        self._memory_uri = None
        self._memory_anchor = None
        if self.db_path == ":memory:":
            self._memory_uri = f"file:persistence_{uuid.uuid4().hex}?mode=memory&cache=shared"
            self._memory_anchor = sqlite3.connect(self._memory_uri, uri=True)
            self._memory_anchor.row_factory = sqlite3.Row
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._init_db()

    def _connect(self):
        if self._memory_uri:
            conn = sqlite3.connect(self._memory_uri, uri=True)
        else:
            conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        try:
            conn = self._connect()
            # Legacy tables used by SECService, AgentLogService, DCA, etc.
            conn.execute("CREATE TABLE IF NOT EXISTS cik_mapping (ticker TEXT PRIMARY KEY, cik TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS thought_journal (signal_id TEXT PRIMARY KEY, bull TEXT, bear TEXT, news TEXT, verdict TEXT, shap TEXT, fundamental_impact REAL, sec_ref TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
            conn.execute("CREATE TABLE IF NOT EXISTS events (level TEXT, source TEXT, message TEXT, metadata TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
            conn.execute("CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, signal_id TEXT, level TEXT, source TEXT, message TEXT, metadata TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
            conn.execute("CREATE TABLE IF NOT EXISTS dca_schedules (id TEXT PRIMARY KEY, amount REAL, frequency TEXT, strategy_id TEXT, next_run TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS portfolio_strategies (strategy_id TEXT, ticker TEXT, weight REAL, risk_profile TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS system_state (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS fee_config (key TEXT PRIMARY KEY, value REAL)")
            conn.execute("CREATE TABLE IF NOT EXISTS investment_goals (name TEXT PRIMARY KEY, target_amount REAL, deadline TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS user_life_events (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, name TEXT, event_date TEXT, description TEXT)")
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
        return self._connect()

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
        bull = kwargs.get('bull', '')
        bear = kwargs.get('bear', '')
        news = kwargs.get('news', '')
        verdict = kwargs.get('verdict', '')
        shap = kwargs.get('shap')
        conn.execute(
            """
            INSERT OR REPLACE INTO thought_journal
                (signal_id, bull, bear, news, verdict, shap, fundamental_impact, sec_ref)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal_id,
                bull,
                bear,
                news,
                verdict,
                json.dumps(shap) if shap is not None else None,
                kwargs.get('fundamental_impact'),
                kwargs.get('sec_ref'),
            ),
        )
        conn.commit()
        conn.close()

    def log_event(self, level: str, source: str, message: str, metadata: Optional[Dict] = None):
        conn = self._get_connection()
        metadata_json = json.dumps(metadata) if metadata else None
        signal_id = metadata.get("signal_id") if metadata else None
        conn.execute("INSERT INTO events (level, source, message, metadata) VALUES (?, ?, ?, ?)", 
                     (level, source, message, metadata_json))
        conn.execute(
            "INSERT INTO logs (signal_id, level, source, message, metadata) VALUES (?, ?, ?, ?, ?)",
            (signal_id, level, source, message, metadata_json),
        )
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

    def get_portfolio_strategy(self, strategy_id: str) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT ticker, weight, risk_profile FROM portfolio_strategies WHERE strategy_id = ?",
            (strategy_id,),
        ).fetchall()
        conn.close()
        return [dict(row) for row in rows]
        
    def save_dca_schedule(self, amount: float, frequency: str, strategy_id: str, next_run: Any):
        schedule_id = str(uuid.uuid4())
        conn = self._get_connection()
        conn.execute("INSERT INTO dca_schedules (id, amount, frequency, strategy_id, next_run) VALUES (?, ?, ?, ?, ?)", 
                     (schedule_id, amount, frequency, strategy_id, next_run.isoformat() if hasattr(next_run, 'isoformat') else str(next_run)))
        conn.commit()
        conn.close()
        return schedule_id

    def get_active_dca_schedules(self) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT id, amount, frequency, strategy_id, next_run FROM dca_schedules ORDER BY next_run"
        ).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def update_dca_next_run(self, schedule_id: str, next_run: Any):
        conn = self._get_connection()
        conn.execute(
            "UPDATE dca_schedules SET next_run = ? WHERE id = ?",
            (next_run.isoformat() if hasattr(next_run, 'isoformat') else str(next_run), schedule_id),
        )
        conn.commit()
        conn.close()

    def set_fee_config(self, key: str, value: float):
        conn = self._get_connection()
        conn.execute("INSERT OR REPLACE INTO fee_config (key, value) VALUES (?, ?)", (key, float(value)))
        conn.commit()
        conn.close()

    def get_fee_config(self, key: str, default: float = 0.0) -> float:
        conn = self._get_connection()
        row = conn.execute("SELECT value FROM fee_config WHERE key = ?", (key,)).fetchone()
        conn.close()
        return float(row["value"]) if row else default

    def save_investment_goal(self, name: str, target_amount: float, deadline: str):
        conn = self._get_connection()
        conn.execute(
            "INSERT OR REPLACE INTO investment_goals (name, target_amount, deadline) VALUES (?, ?, ?)",
            (name, float(target_amount), deadline),
        )
        conn.commit()
        conn.close()

    def get_investment_goals(self) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        rows = conn.execute("SELECT name, target_amount, deadline FROM investment_goals").fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def save_user_life_event(self, user_id: str, name: str, event_date: str, description: str):
        conn = self._get_connection()
        conn.execute(
            "INSERT INTO user_life_events (user_id, name, event_date, description) VALUES (?, ?, ?, ?)",
            (user_id, name, event_date, description),
        )
        conn.commit()
        conn.close()

    def get_user_life_events(self, user_id: str) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT user_id, name, event_date, description FROM user_life_events WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        conn.close()
        return [dict(row) for row in rows]

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
