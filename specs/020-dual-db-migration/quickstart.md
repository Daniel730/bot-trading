# Quickstart: Dual-Database Setup

## 1. Local Environment Config
Add these to your `.env` file:
```env
# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# PostgreSQL Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=bot_admin
POSTGRES_PASSWORD=bot_pass
POSTGRES_DB=trading_bot
```

## 2. Dependency Update
Run the following to install required libraries:
```bash
pip install redis sqlalchemy asyncpg
```

## 3. Database Initialization
Use the following script (to be implemented) to initialize the schemas:
```bash
python scripts/init_db.py --dual-db
```

## 4. Run Migration
To migrate your legacy SQLite data:
```bash
python scripts/migrate_sqlite_to_pg.py --source data/trading_bot.db
```

## 5. Verification
Check if the bot is routing data correctly:
- **Redis**: Use `redis-cli HGETALL kalman:BTC-USD` to see active state.
- **PostgreSQL**: Use `psql` to query the `trade_ledger` table.
