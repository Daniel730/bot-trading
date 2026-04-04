import sqlite3
import os
from pathlib import Path

# Base Directory
BASE_DIR = Path(__file__).resolve().parent.parent
# PersistenceManager uses trading_bot.db by default, but let's be safe and check monitor.py or config
DB_PATH = BASE_DIR / "trading_bot.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
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

    # TickerCIKMap
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ticker_cik_map (
            ticker TEXT PRIMARY KEY,
            cik TEXT NOT NULL,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # SecFilingCache
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
    conn.close()
    print(f"Database initialized at {DB_PATH}")

if __name__ == "__main__":
    init_db()
