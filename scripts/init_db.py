import sqlite3
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.models.trading_models import init_db
from src.config import DB_PATH

def seed_initial_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Seed Virtual Pie
    assets = [
        ('AAPL_US_EQ', 0.25, 0.0, 0.0),
        ('MSFT_US_EQ', 0.25, 0.0, 0.0),
        ('KO_US_EQ', 0.25, 0.0, 0.0),
        ('PEP_US_EQ', 0.25, 0.0, 0.0)
    ]
    cursor.executemany('INSERT OR IGNORE INTO virtual_pie VALUES (?, ?, ?, ?)', assets)
    
    # Seed Pairs
    pairs = [
        ('AAPL_MSFT', 'AAPL_US_EQ', 'MSFT_US_EQ', 0.0, 0.0, 0.0, 0.0),
        ('KO_PEP', 'KO_US_EQ', 'PEP_US_EQ', 0.0, 0.0, 0.0, 0.0)
    ]
    cursor.executemany('INSERT OR IGNORE INTO trading_pairs VALUES (?, ?, ?, ?, ?, ?, ?)', pairs)
    
    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")

if __name__ == "__main__":
    init_db()
    seed_initial_data()
