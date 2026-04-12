import asyncio
from src.services.persistence_service import persistence_service
import sys

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
