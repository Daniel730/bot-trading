from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import sqlite3
from src.config import DB_PATH

@dataclass
class TradingPair:
    id: str
    asset_a: str
    asset_b: str
    hedge_ratio: float = 0.0
    mean_spread: float = 0.0
    std_spread: float = 0.0
    last_z_score: float = 0.0

@dataclass
class VirtualPieAsset:
    ticker: str
    target_weight: float
    current_quantity: float = 0.0
    last_price: float = 0.0

@dataclass
class Signal:
    id: str
    timestamp: datetime
    pair_id: str
    z_score: float
    status: str  # PENDING_AI, PENDING_USER_CONFIRM, APPROVED, REJECTED, EXECUTED, EXPIRED

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS virtual_pie (
        ticker TEXT PRIMARY KEY,
        target_weight REAL NOT NULL,
        current_quantity REAL DEFAULT 0.0,
        last_price REAL DEFAULT 0.0
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS trading_pairs (
        id TEXT PRIMARY KEY,
        asset_a TEXT NOT NULL,
        asset_b TEXT NOT NULL,
        hedge_ratio REAL DEFAULT 0.0,
        mean_spread REAL DEFAULT 0.0,
        std_spread REAL DEFAULT 0.0,
        last_z_score REAL DEFAULT 0.0,
        FOREIGN KEY (asset_a) REFERENCES virtual_pie (ticker),
        FOREIGN KEY (asset_b) REFERENCES virtual_pie (ticker)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS signals (
        id TEXT PRIMARY KEY,
        timestamp TEXT NOT NULL,
        pair_id TEXT NOT NULL,
        z_score REAL NOT NULL,
        status TEXT NOT NULL,
        FOREIGN KEY (pair_id) REFERENCES trading_pairs (id)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS audit_logs (
        timestamp TEXT NOT NULL,
        signal_id TEXT,
        context_summary TEXT,
        ai_recommendation TEXT,
        user_confirmation TEXT,
        ai_rationale TEXT,
        action_taken TEXT,
        order_id TEXT,
        FOREIGN KEY (signal_id) REFERENCES signals (id)
    )
    ''')
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
