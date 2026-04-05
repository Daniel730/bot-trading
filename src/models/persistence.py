import sqlite3
import uuid
import time
from datetime import datetime
from typing import List, Optional, Dict
import json
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

class PersistenceManager:
    def __init__(self, db_path: str = "trading_bot.db"):
        self.db_path = db_path
        self._conn = None # For in-memory persistence
        self._init_db()

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(sqlite3.OperationalError),
        reraise=True
    )
    def _get_connection(self):
        """
        Retrieves a database connection with retry logic for locks.
        Decision 2: 30s timeout for busy handlers.
        """
        if self.db_path == ":memory:":
            if not self._conn:
                self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
                self._conn.row_factory = sqlite3.Row
                self._load_vec(self._conn)
            return self._conn

        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        self._load_vec(conn)
        return conn

    def _load_vec(self, conn):
        # Load sqlite-vec extension (Feature 015)
        try:
            import sqlite_vec
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
        except (ImportError, Exception):
            pass

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

            # Logs - NEW for Auditability (Principle III)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id TEXT PRIMARY KEY,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    level TEXT NOT NULL,
                    source TEXT NOT NULL,
                    message TEXT NOT NULL,
                    metadata TEXT,
                    signal_id TEXT
                )
            """)

            # Feature 014 Migration for logs table
            try:
                cursor.execute("ALTER TABLE logs ADD COLUMN signal_id TEXT")
            except sqlite3.OperationalError: pass

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

            # Feature 014: Portfolio & DCA
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS portfolio_strategies (
                ticker TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                target_weight REAL NOT NULL,
                risk_profile TEXT NOT NULL,
                PRIMARY KEY (ticker, strategy_id)
            )
            ''')

            cursor.execute('''
            CREATE TABLE IF NOT EXISTS dca_schedules (
                id TEXT PRIMARY KEY,
                amount REAL NOT NULL,
                frequency TEXT NOT NULL,
                day_of_week INTEGER,
                day_of_month INTEGER,
                strategy_id TEXT NOT NULL,
                next_run TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1
            )
            ''')

            cursor.execute('''
            CREATE TABLE IF NOT EXISTS fee_config (
                key TEXT PRIMARY KEY,
                value REAL NOT NULL
            )
            ''')

            # Seed default fee config if not exists
            cursor.execute("INSERT OR IGNORE INTO fee_config (key, value) VALUES ('max_friction_pct', 0.015)")
            cursor.execute("INSERT OR IGNORE INTO fee_config (key, value) VALUES ('min_trade_value', 1.00)")

            # Feature 015: Low-Budget Investor Suite

            # InvestmentGoal
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS investment_goals (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    name TEXT NOT NULL,
                    target_amount REAL,
                    current_amount REAL DEFAULT 0,
                    deadline DATE,
                    status TEXT DEFAULT 'Active'
                )
            """)

            # UserLifeEvent
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_life_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_date DATE NOT NULL,
                    description TEXT,
                    impact_on_horizon TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # InvestmentHorizon
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS investment_horizons (
                    id TEXT PRIMARY KEY,
                    goal_id TEXT,
                    horizon_type TEXT NOT NULL, -- Short, Medium, Long
                    risk_tolerance TEXT NOT NULL,
                    target_date DATE NOT NULL,
                    FOREIGN KEY (goal_id) REFERENCES investment_goals (id)
                )
            """)

            # CashSweep
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cash_sweeps (
                    id TEXT PRIMARY KEY,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    type TEXT NOT NULL, -- SWEEP_IN, SWEEP_OUT
                    amount REAL NOT NULL,
                    ticker TEXT NOT NULL,
                    balance_after REAL NOT NULL
                )
            """)

            # TradeThesis - Updated for Feature 015
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_theses (
                    id TEXT PRIMARY KEY,
                    trade_id TEXT,
                    thesis_text TEXT NOT NULL,
                    monte_carlo_path TEXT,
                    voice_note_path TEXT,
                    kelly_fraction REAL,
                    explainability_scores TEXT, -- JSON
                    risk_veto_status TEXT,
                    FOREIGN KEY (trade_id) REFERENCES trade_records (id)
                )
            """)

            # AgentPerformance
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agent_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name TEXT UNIQUE NOT NULL,
                    current_weight REAL DEFAULT 1.0,
                    historical_accuracy REAL DEFAULT 0.0,
                    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # SyntheticOrder
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS synthetic_orders (
                    ticker TEXT PRIMARY KEY,
                    activation_price REAL,
                    trailing_pct REAL,
                    highest_price REAL,
                    is_active BOOLEAN DEFAULT TRUE
                )
            """)

            # SystemState - Resolve Production Rigor Gaps (Decision 2)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            # Seed initial state
            cursor.execute("INSERT OR IGNORE INTO system_state (key, value) VALUES ('operational_status', 'NORMAL')")
            cursor.execute("INSERT OR IGNORE INTO system_state (key, value) VALUES ('consecutive_api_timeouts', '0')")

            conn.commit()

    def set_system_state(self, key: str, value: str):
        """Updates a persistent system state value (Decision 2)."""
        with self._get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)", (key, value))
            conn.commit()

    def get_system_state(self, key: str, default: str = None) -> Optional[str]:
        """Retrieves a persistent system state value (Decision 2)."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT value FROM system_state WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else default

    def save_investment_goal(self, name: str, target_amount: float, deadline: str, user_id: str = None) -> str:
        goal_id = str(uuid.uuid4())[:8]
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO investment_goals (id, name, target_amount, deadline, user_id) VALUES (?, ?, ?, ?, ?)",
                (goal_id, name, target_amount, deadline, user_id)
            )
            conn.commit()
        return goal_id

    def get_investment_goals(self) -> List[Dict]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM investment_goals WHERE status = 'Active'").fetchall()
            return [dict(row) for row in rows]

    def save_cash_sweep(self, sweep_type: str, amount: float, ticker: str, balance_after: float):
        sweep_id = str(uuid.uuid4())
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO cash_sweeps (id, timestamp, type, amount, ticker, balance_after) VALUES (?, ?, ?, ?, ?, ?)",
                (sweep_id, datetime.now(), sweep_type, amount, ticker, balance_after)
            )
            conn.commit()

    def get_latest_cash_balance(self) -> float:
        with self._get_connection() as conn:
            row = conn.execute("SELECT balance_after FROM cash_sweeps ORDER BY timestamp DESC LIMIT 1").fetchone()
            return float(row["balance_after"]) if row else 0.0

    def log_event(self, level: str, source: str, message: str, metadata: dict = None, signal_id: str = None):
        """Persists a system or terminal event for auditability."""
        log_id = str(uuid.uuid4())
        metadata_json = json.dumps(metadata) if metadata else None
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO logs (id, timestamp, level, source, message, metadata, signal_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (log_id, datetime.now(), level, source, message, metadata_json, signal_id)
            )
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

    # Feature 014: Portfolio & DCA Persistence

    def save_portfolio_strategy(self, strategy_id: str, ticker: str, weight: float, risk_profile: str):
        """Saves a strategy component (asset weight)."""
        with self._get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO portfolio_strategies (strategy_id, ticker, target_weight, risk_profile) 
                   VALUES (?, ?, ?, ?)""",
                (strategy_id, ticker, weight, risk_profile)
            )
            conn.commit()

    def get_portfolio_strategy(self, strategy_id: str) -> List[Dict]:
        """Returns all assets and weights for a specific strategy."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT ticker, target_weight, risk_profile FROM portfolio_strategies WHERE strategy_id = ?",
                (strategy_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def save_dca_schedule(self, amount: float, frequency: str, strategy_id: str, next_run: datetime, day_of_week: int = None, day_of_month: int = None):
        """Persists a new DCA investment schedule."""
        schedule_id = str(uuid.uuid4())[:8]
        with self._get_connection() as conn:
            conn.execute(
                """INSERT INTO dca_schedules (id, amount, frequency, strategy_id, next_run, day_of_week, day_of_month) 
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (schedule_id, amount, frequency, strategy_id, next_run.isoformat(), day_of_week, day_of_month)
            )
            conn.commit()
        return schedule_id

    def get_active_dca_schedules(self) -> List[Dict]:
        """Returns all enabled DCA schedules."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM dca_schedules WHERE is_active = 1").fetchall()
            return [dict(row) for row in rows]

    def update_dca_next_run(self, schedule_id: str, next_run: datetime):
        """Updates the next execution time for a schedule."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE dca_schedules SET next_run = ? WHERE id = ?",
                (next_run.isoformat(), schedule_id)
            )
            conn.commit()

    def set_fee_config(self, key: str, value: float):
        """Updates a global fee or threshold setting."""
        with self._get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO fee_config (key, value) VALUES (?, ?)", (key, value))
            conn.commit()

    def get_fee_config(self, key: str, default: float = 0.0) -> float:
        """Retrieves a fee or threshold setting."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT value FROM fee_config WHERE key = ?", (key,)).fetchone()
            return float(row["value"]) if row else default

    def save_trade_thesis(self, trade_id: str, vectorized_reasoning: bytes, confidence_scores: Dict, macro_state: Dict):
        """Stores the reasoning and confidence levels for a trade (T021)."""
        with self._get_connection() as conn:
            conn.execute(
                """INSERT INTO trade_theses (trade_id, vectorized_reasoning, confidence_scores, macro_state) 
                   VALUES (?, ?, ?, ?)""",
                (trade_id, vectorized_reasoning, json.dumps(confidence_scores), json.dumps(macro_state))
            )
            conn.commit()

    def save_user_life_event(self, user_id: str, event_type: str, event_date: str, description: str):
        """Persists a life event that impacts the investment horizon (T027)."""
        with self._get_connection() as conn:
            conn.execute(
                """INSERT INTO user_life_events (user_id, event_type, event_date, description) 
                   VALUES (?, ?, ?, ?)""",
                (user_id, event_type, event_date, description)
            )
            conn.commit()

    def save_investment_thesis(self, trade_id: str, thesis_text: str):
        """Saves the structured natural language justification for a trade (T029)."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE trade_theses SET thesis_text = ? WHERE trade_id = ?",
                (thesis_text, trade_id)
            )
            conn.commit()
