import asyncio
import sys
from pathlib import Path

# Running this file directly (e.g. `python scripts/init_db.py`) puts the
# script's own directory on sys.path, NOT the repo root, so `from src...`
# raises ModuleNotFoundError. Prepend the repo root so the script works
# regardless of how it's invoked (direct, -m, from CI, from a cron, etc.).
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.services.persistence_service import persistence_service  # noqa: E402

async def main():
    print("Initializing Dual-Database Schema (PostgreSQL)...")
    try:
        await persistence_service.init_db()
        print("✓ PostgreSQL schema initialized successfully.")
    except Exception as e:
        print(f"✗ Failed to initialize PostgreSQL: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
