import sqlite3
import uuid
from datetime import datetime
from typing import List, Optional, Dict
import json

class PersistenceManager:
    def __init__(self, db_path: str = "trading_bot.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # ArbitragePair
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS arbitrage_pairs (
                    id TEXT PRIMARY KEY,
                    ticker_a TEXT NOT NULL,
                    ticker_b TEXT NOT NULL,
                    hedge_ratio REAL,
                    is_cointegrated BOOLEAN,
                    last_adf_pvalue REAL,
                    status TEXT DEFAULT 'Active'
                )
            """)

            # Signal
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id TEXT PRIMARY KEY,
                    pair_id TEXT NOT NULL,
                    z_score REAL NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    confidence_score REAL,
                    news_sentiment REAL,
                    FOREIGN KEY (pair_id) REFERENCES arbitrage_pairs (id)
                )
            """)

            # TradeRecord
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_records (
                    id TEXT PRIMARY KEY,
                    signal_id TEXT,
                    pair_id TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_timestamp DATETIME NOT NULL,
                    exit_timestamp DATETIME,
                    size_a REAL NOT NULL,
                    size_b REAL NOT NULL,
                    entry_price_a REAL,
                    entry_price_b REAL,
                    exit_price_a REAL,
                    exit_price_b REAL,
                    is_shadow BOOLEAN DEFAULT TRUE,
                    status TEXT DEFAULT 'Open',
                    pnl REAL,
                    FOREIGN KEY (signal_id) REFERENCES signals (id),
                    FOREIGN KEY (pair_id) REFERENCES arbitrage_pairs (id)
                )
            """)

            # ThoughtJournal
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS thought_journals (
                    id TEXT PRIMARY KEY,
                    signal_id TEXT NOT NULL,
                    bull_argument TEXT,
                    bear_argument TEXT,
                    news_analysis TEXT,
                    final_verdict TEXT,
                    shap_values TEXT,
                    FOREIGN KEY (signal_id) REFERENCES signals (id)
                )
            """)

            # VirtualPortfolio
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS virtual_portfolio (
                    ticker TEXT PRIMARY KEY,
                    allocated_amount REAL DEFAULT 0,
                    current_value REAL DEFAULT 0,
                    last_reconciliation DATETIME
                )
            """)
            conn.commit()

    def save_pair(self, ticker_a: str, ticker_b: str, hedge_ratio: float = None) -> str:
        pair_id = str(uuid.uuid4())
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO arbitrage_pairs (id, ticker_a, ticker_b, hedge_ratio) VALUES (?, ?, ?, ?)",
                (pair_id, ticker_a, ticker_b, hedge_ratio)
            )
            conn.commit()
        return pair_id

    def log_signal(self, pair_id: str, z_score: float, confidence: float = None, sentiment: float = None) -> str:
        signal_id = str(uuid.uuid4())
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO signals (id, pair_id, z_score, confidence_score, news_sentiment) VALUES (?, ?, ?, ?, ?)",
                (signal_id, pair_id, z_score, confidence, sentiment)
            )
            conn.commit()
        return signal_id

    def log_thought(self, signal_id: str, bull: str, bear: str, news: str, verdict: str, shap: Dict = None) -> str:
        journal_id = str(uuid.uuid4())
        shap_json = json.dumps(shap) if shap else None
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO thought_journals (id, signal_id, bull_argument, bear_argument, news_analysis, final_verdict, shap_values) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (journal_id, signal_id, bull, bear, news, verdict, shap_json)
            )
            conn.commit()
        return journal_id

    def save_trade(self, pair_id: str, direction: str, size_a: float, size_b: float, signal_id: str = None, is_shadow: bool = True) -> str:
        trade_id = str(uuid.uuid4())
        with self._get_connection() as conn:
            conn.execute(
                """INSERT INTO trade_records (id, signal_id, pair_id, direction, entry_timestamp, size_a, size_b, is_shadow) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (trade_id, signal_id, pair_id, direction, datetime.now(), size_a, size_b, is_shadow)
            )
            conn.commit()
        return trade_id
