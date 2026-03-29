import sqlite3
import os
from pathlib import Path

# Base Directory
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "trading_bot.sqlite"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create ArbitragePair table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ArbitragePair (
            id TEXT PRIMARY KEY,
            ticker_a TEXT NOT NULL,
            ticker_b TEXT NOT NULL,
            beta REAL,
            status TEXT DEFAULT 'MONITORING',
            last_z_score REAL,
            is_cointegrated BOOLEAN
        )
    ''')

    # Create SignalRecord table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS SignalRecord (
            id TEXT PRIMARY KEY,
            pair_id TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            z_score REAL,
            price_a REAL,
            price_b REAL,
            trigger_type TEXT,
            ai_validation_status TEXT DEFAULT 'PENDING',
            ai_rationale TEXT,
            user_approval_status TEXT DEFAULT 'PENDING',
            FOREIGN KEY (pair_id) REFERENCES ArbitragePair (id)
        )
    ''')

    # Create VirtualPieAsset table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS VirtualPieAsset (
            ticker TEXT PRIMARY KEY,
            target_weight REAL,
            current_quantity REAL,
            currency TEXT
        )
    ''')

    # Create TradeLedger table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS TradeLedger (
            id TEXT PRIMARY KEY,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            ticker TEXT NOT NULL,
            quantity REAL,
            price REAL,
            order_type TEXT,
            is_paper BOOLEAN,
            status TEXT DEFAULT 'COMPLETED'
        )
    ''')

    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")

if __name__ == "__main__":
    init_db()
