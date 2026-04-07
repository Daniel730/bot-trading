import sqlite3
import json
import logging
import os
from typing import Dict, Any, Optional
from src.config import settings

logger = logging.getLogger(__name__)

class PersistenceManager:
    def __init__(self, db_path: Optional[str] = None):
        # Fallback to a default if settings doesn't have it or passed as None
        self.db_path = db_path or getattr(settings, "DB_PATH", "logs/trading_bot.db")
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            # Legacy tables used by SECService, AgentLogService, DCA, etc.
            conn.execute("CREATE TABLE IF NOT EXISTS cik_mapping (ticker TEXT PRIMARY KEY, cik TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS thought_journal (signal_id TEXT PRIMARY KEY, bull TEXT, bear TEXT, news TEXT, verdict TEXT, shap TEXT, fundamental_impact REAL, sec_ref TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
            conn.execute("CREATE TABLE IF NOT EXISTS events (level TEXT, source TEXT, message TEXT, metadata TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
            conn.execute("CREATE TABLE IF NOT EXISTS dca_schedules (id TEXT PRIMARY KEY, amount REAL, frequency TEXT, strategy_id TEXT, next_run TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS portfolio_strategies (strategy_id TEXT, ticker TEXT, weight REAL, risk_profile TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS system_state (key TEXT PRIMARY KEY, value TEXT)")
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"PersistenceManager init error: {e}")

    def load_cik_mapping(self, ticker: str) -> Optional[str]:
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT cik FROM cik_mapping WHERE ticker = ?", (ticker,)).fetchone()
        conn.close()
        return row[0] if row else None

    def save_cik_mapping(self, ticker: str, cik: str):
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT OR REPLACE INTO cik_mapping VALUES (?, ?)", (ticker, cik))
        conn.commit()
        conn.close()

    def log_thought(self, signal_id: str, **kwargs):
        conn = sqlite3.connect(self.db_path)
        # Simplified insert for legacy support
        verdict = kwargs.get('verdict', '')
        conn.execute("INSERT OR REPLACE INTO thought_journal (signal_id, verdict) VALUES (?, ?)", (signal_id, verdict))
        conn.commit()
        conn.close()

    def log_event(self, level: str, source: str, message: str, metadata: Optional[Dict] = None):
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT INTO events (level, source, message, metadata) VALUES (?, ?, ?, ?)", 
                     (level, source, message, json.dumps(metadata) if metadata else None))
        conn.commit()
        conn.close()

    def get_system_state(self, key: str, default: Any = None) -> Any:
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT value FROM system_state WHERE key = ?", (key,)).fetchone()
        conn.close()
        return row[0] if row else default

    def set_system_state(self, key: str, value: Any):
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT OR REPLACE INTO system_state VALUES (?, ?)", (key, str(value)))
        conn.commit()
        conn.close()
        
    def save_portfolio_strategy(self, strategy_id: str, ticker: str, weight: float, risk_profile: str):
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT INTO portfolio_strategies (strategy_id, ticker, weight, risk_profile) VALUES (?, ?, ?, ?)", 
                     (strategy_id, ticker, weight, risk_profile))
        conn.commit()
        conn.close()
        
    def save_dca_schedule(self, amount: float, frequency: str, strategy_id: str, next_run: Any):
        import uuid
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT INTO dca_schedules (id, amount, frequency, strategy_id, next_run) VALUES (?, ?, ?, ?, ?)", 
                     (str(uuid.uuid4()), amount, frequency, strategy_id, next_run.isoformat() if hasattr(next_run, 'isoformat') else str(next_run)))
        conn.commit()
        conn.close()

    # Dashboard polling stubs (Legacy)
    def get_daily_invested(self, date_str: str, is_shadow: bool = True) -> float: return 0.0
    def get_total_revenue(self, is_shadow: bool = True) -> float: return 0.0
    def get_current_investment(self, is_shadow: bool = True) -> float: return 0.0
    def get_daily_pnl(self, date_str: str, is_shadow: bool = True) -> float: return 0.0
