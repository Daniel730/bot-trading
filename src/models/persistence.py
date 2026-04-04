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

            # ThoughtJournal - Updated for Feature 009
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS thought_journals (
                    id TEXT PRIMARY KEY,
                    signal_id TEXT NOT NULL,
                    bull_argument TEXT,
                    bear_argument TEXT,
                    news_analysis TEXT,
                    final_verdict TEXT,
                    shap_values TEXT,
                    fundamental_impact REAL,
                    sec_reference_snippet TEXT,
                    FOREIGN KEY (signal_id) REFERENCES signals (id)
                )
            """)

            # Simple migration for existing databases
            try:
                cursor.execute("ALTER TABLE thought_journals ADD COLUMN fundamental_impact REAL")
            except sqlite3.OperationalError: pass
            try:
                cursor.execute("ALTER TABLE thought_journals ADD COLUMN sec_reference_snippet TEXT")
            except sqlite3.OperationalError: pass

            # VirtualPortfolio
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS virtual_portfolio (
                    ticker TEXT PRIMARY KEY,
                    allocated_amount REAL DEFAULT 0,
                    current_value REAL DEFAULT 0,
                    last_reconciliation DATETIME
                )
            """)

            # KalmanState
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS kalman_state (
                    pair_id TEXT PRIMARY KEY,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    alpha REAL NOT NULL,
                    beta REAL NOT NULL,
                    p_matrix TEXT NOT NULL,
                    q_matrix TEXT NOT NULL,
                    r_value REAL NOT NULL,
                    ve REAL,
                    FOREIGN KEY (pair_id) REFERENCES arbitrage_pairs (id)
                )
            """)

            # TickerCIKMap - NEW for Feature 009
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ticker_cik_map (
                    ticker TEXT PRIMARY KEY,
                    cik TEXT NOT NULL,
                    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # SecFilingCache - NEW for Feature 009
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sec_filing_cache (
                    accession_number TEXT PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    filing_type TEXT NOT NULL,
                    filing_date DATE NOT NULL,
                    risk_summary TEXT,
                    structural_integrity_score INTEGER,
                    FOREIGN KEY (ticker) REFERENCES ticker_cik_map (ticker)
                )
            """)
            conn.commit()

    def save_cik_mapping(self, ticker: str, cik: str):
        """Persists a ticker to CIK mapping."""
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO ticker_cik_map (ticker, cik, last_updated) VALUES (?, ?, ?)",
                (ticker, cik, datetime.now())
            )
            conn.commit()

    def load_cik_mapping(self, ticker: str) -> Optional[str]:
        """Loads a CIK for a given ticker."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT cik FROM ticker_cik_map WHERE ticker = ?", (ticker,)).fetchone()
            return row["cik"] if row else None

    def save_sec_filing(self, accession_number: str, ticker: str, filing_type: str, filing_date: str, risk_summary: str, score: int):
        """Persists the result of an SEC filing analysis."""
        with self._get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO sec_filing_cache (accession_number, ticker, filing_type, filing_date, risk_summary, structural_integrity_score)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (accession_number, ticker, filing_type, filing_date, risk_summary, score)
            )
            conn.commit()

    def get_sec_filing(self, ticker: str, filing_type: str) -> Optional[Dict]:
        """Loads the most recent cached SEC filing analysis for a given ticker and type."""
        with self._get_connection() as conn:
            row = conn.execute(
                """SELECT accession_number, filing_date, risk_summary, structural_integrity_score 
                   FROM sec_filing_cache 
                   WHERE ticker = ? AND filing_type = ? 
                   ORDER BY filing_date DESC LIMIT 1""",
                (ticker, filing_type)
            ).fetchone()
            
            if row:
                return {
                    "accession_number": row["accession_number"],
                    "date": row["filing_date"],
                    "risk_summary": row["risk_summary"],
                    "integrity_score": row["structural_integrity_score"]
                }
        return None

    def save_kalman_state(self, pair_id: str, alpha: float, beta: float, p_matrix: List[List[float]], q_matrix: List[List[float]], r_value: float, ve: float):
        """Persists the recursive state of a Kalman filter."""
        p_matrix_json = json.dumps(p_matrix)
        q_matrix_json = json.dumps(q_matrix)
        with self._get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO kalman_state (pair_id, timestamp, alpha, beta, p_matrix, q_matrix, r_value, ve)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (pair_id, datetime.now(), alpha, beta, p_matrix_json, q_matrix_json, r_value, ve)
            )
            conn.commit()

    def load_kalman_state(self, pair_id: str) -> Optional[Dict]:
        """Loads the persisted state for a Kalman filter."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT alpha, beta, p_matrix, q_matrix, r_value, ve FROM kalman_state WHERE pair_id = ?",
                (pair_id,)
            ).fetchone()
            
            if row:
                return {
                    "alpha": row["alpha"],
                    "beta": row["beta"],
                    "p_matrix": json.loads(row["p_matrix"]),
                    "q_matrix": json.loads(row["q_matrix"]),
                    "r_value": row["r_value"],
                    "ve": row["ve"]
                }
        return None

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

    def log_thought(self, signal_id: str, bull: str, bear: str, news: str, verdict: str, shap: Dict = None, fundamental_impact: float = None, sec_ref: str = None) -> str:
        journal_id = str(uuid.uuid4())
        shap_json = json.dumps(shap) if shap else None
        with self._get_connection() as conn:
            conn.execute(
                """INSERT INTO thought_journals 
                   (id, signal_id, bull_argument, bear_argument, news_analysis, final_verdict, shap_values, fundamental_impact, sec_reference_snippet) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (journal_id, signal_id, bull, bear, news, verdict, shap_json, fundamental_impact, sec_ref)
            )
            conn.commit()
        return journal_id

    def save_trade(self, pair_id: str, direction: str, size_a: float, size_b: float, price_a: float = 0.0, price_b: float = 0.0, signal_id: str = None, is_shadow: bool = True) -> str:
        trade_id = str(uuid.uuid4())
        with self._get_connection() as conn:
            conn.execute(
                """INSERT INTO trade_records (id, signal_id, pair_id, direction, entry_timestamp, size_a, size_b, entry_price_a, entry_price_b, is_shadow, status) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Open')""",
                (trade_id, signal_id, pair_id, direction, datetime.now(), size_a, size_b, price_a, price_b, is_shadow)
            )
            conn.commit()
        return trade_id

    def get_open_trade(self, pair_id: str, is_shadow: bool = True) -> Optional[Dict]:
        """Returns the open trade for a specific pair if one exists."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, direction, size_a, size_b, entry_price_a, entry_price_b FROM trade_records WHERE pair_id = ? AND status = 'Open' AND is_shadow = ?",
                (pair_id, is_shadow)
            ).fetchone()
            if row:
                return dict(row)
        return None

    def close_trade(self, trade_id: str, exit_price_a: float, exit_price_b: float, pnl: float):
        """Marks a trade as Closed and records exit data."""
        with self._get_connection() as conn:
            conn.execute(
                """UPDATE trade_records 
                   SET status = 'Closed', exit_timestamp = ?, exit_price_a = ?, exit_price_b = ?, pnl = ?
                   WHERE id = ?""",
                (datetime.now(), exit_price_a, exit_price_b, pnl, trade_id)
            )
            conn.commit()

    def get_daily_pnl(self, target_date: str, is_shadow: bool = False) -> float:
        """Returns the total PnL for all trades closed on a specific date."""
        with self._get_connection() as conn:
            row = conn.execute(
                """SELECT SUM(pnl) as total_pnl FROM trade_records 
                   WHERE date(exit_timestamp) = date(?) AND is_shadow = ? AND status = 'Closed'""",
                (target_date, is_shadow)
            ).fetchone()
            return float(row["total_pnl"] or 0.0)

    def get_daily_invested(self, target_date: str, is_shadow: bool = False) -> float:
        """Returns the total capital invested (size * entry_price) for trades opened on a specific date."""
        with self._get_connection() as conn:
            row = conn.execute(
                """SELECT SUM((size_a * entry_price_a) + (size_b * entry_price_b)) as total_invested 
                   FROM trade_records 
                   WHERE date(entry_timestamp) = date(?) AND is_shadow = ?""",
                (target_date, is_shadow)
            ).fetchone()
            return float(row["total_invested"] or 0.0)

    def get_daily_trades(self, target_date: str, is_shadow: bool = False) -> List[Dict]:
        """Returns all trades (open and closed) for a specific date for analysis."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """SELECT * FROM trade_records 
                   WHERE date(entry_timestamp) = date(?) AND is_shadow = ?""",
                (target_date, is_shadow)
            ).fetchall()
            return [dict(row) for row in rows]

    def get_total_revenue(self, is_shadow: bool = True) -> float:
        """Returns the lifetime realized PnL for closed trades."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT SUM(pnl) as total FROM trade_records WHERE status = 'Closed' AND is_shadow = ?",
                (is_shadow,)
            ).fetchone()
            return float(row["total"] or 0.0)

    def get_current_investment(self, is_shadow: bool = True) -> float:
        """Returns the total entry value of all currently open positions."""
        with self._get_connection() as conn:
            row = conn.execute(
                """SELECT SUM((size_a * entry_price_a) + (size_b * entry_price_b)) as total 
                   FROM trade_records 
                   WHERE status = 'Open' AND is_shadow = ?""",
                (is_shadow,)
            ).fetchone()
            return float(row["total"] or 0.0)
