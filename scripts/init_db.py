import sqlite3
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.config import DB_PATH

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # ArbitragePair table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS arbitrage_pairs (
        id TEXT PRIMARY KEY,
        ticker_a TEXT NOT NULL,
        ticker_b TEXT NOT NULL,
        beta REAL DEFAULT 0.0,
        status TEXT DEFAULT 'MONITORING',
        last_z_score REAL DEFAULT 0.0,
        is_cointegrated INTEGER DEFAULT 0
    )
    ''')
    
    # ZScoreHistory table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS zscore_history (
        pair_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        window INTEGER NOT NULL,
        value REAL NOT NULL,
        FOREIGN KEY (pair_id) REFERENCES arbitrage_pairs (id)
    )
    ''')
    
    # SignalRecord table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS signal_records (
        id TEXT PRIMARY KEY,
        pair_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        z_score REAL NOT NULL,
        price_a REAL,
        price_b REAL,
        trigger_type TEXT NOT NULL,
        ai_validation_status TEXT DEFAULT 'PENDING',
        ai_rationale TEXT,
        user_approval_status TEXT DEFAULT 'PENDING',
        FOREIGN KEY (pair_id) REFERENCES arbitrage_pairs (id)
    )
    ''')
    
    # VirtualPieAsset table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS virtual_pie_assets (
        ticker TEXT PRIMARY KEY,
        target_weight REAL NOT NULL,
        current_quantity REAL DEFAULT 0.0,
        currency TEXT DEFAULT 'EUR'
    )
    ''')
    
    # TradeLedger table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS trade_ledger (
        id TEXT PRIMARY KEY,
        timestamp TEXT NOT NULL,
        ticker TEXT NOT NULL,
        quantity REAL NOT NULL,
        price REAL NOT NULL,
        order_type TEXT NOT NULL,
        is_paper INTEGER DEFAULT 1,
        status TEXT DEFAULT 'COMPLETED'
    )
    ''')
    
    conn.commit()
    conn.close()

def seed_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Seed Virtual Pie Assets
    assets = [
        ('KO', 0.5, 0.0, 'EUR'),
        ('PEP', 0.5, 0.0, 'EUR')
    ]
    cursor.executemany('INSERT OR IGNORE INTO virtual_pie_assets VALUES (?, ?, ?, ?)', assets)
    
    # Seed Pairs
    # Using a deterministic UUID for seeding if needed, or just let it be.
    # For now, we'll use a string ID.
    pairs = [
        ('pair_ko_pep', 'KO', 'PEP', 0.0, 'MONITORING', 0.0, 0)
    ]
    cursor.executemany('INSERT OR IGNORE INTO arbitrage_pairs (id, ticker_a, ticker_b, beta, status, last_z_score, is_cointegrated) VALUES (?, ?, ?, ?, ?, ?, ?)', pairs)
    
    conn.commit()
    conn.close()
    print(f"Database initialized and seeded at {DB_PATH}")

if __name__ == "__main__":
    init_db()
    seed_data()
