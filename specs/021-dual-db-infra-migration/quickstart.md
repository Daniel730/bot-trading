# Quickstart: Dual-Database Migration

## 1. Local Infrastructure Configuration
Update your `.env` file with these variables:
```env
# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
REDIS_APPENDONLY=yes

# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=bot_admin
POSTGRES_PASSWORD=bot_pass
POSTGRES_DB=trading_bot
```

## 2. Dependency Installation
Run the following to install required libraries:
```bash
pip install redis sqlalchemy asyncpg
```

## 3. Database Initialization
Use the new initialization script to set up PostgreSQL:
```bash
python scripts/init_db.py --dual-db
```

## 4. Run the Bot
Start the bot in development mode to verify connections:
```bash
python src/main.py --dev
```

## 5. Persistence Verification
Test state recovery and trade durability:
- **Redis**: Check `redis-cli HGETALL kalman:BTC-USD` to verify Kalman state persistence.
- **PostgreSQL**: Query `trade_ledger` via `psql` to verify persistent records.
