#!/bin/bash
set -e

# 1. Database Initialization (Only if using SQLite, but we recommend Postgres for production)
# In production, ensure DATABASE_URL is set to your Supabase/Postgres instance
python scripts/init_db.py

# Start the application
echo "Starting Strategic Arbitrage Bot (Watch: ${WATCH:-false})..."
if [ "${WATCH}" = "true" ]; then
    exec watchfiles "python src/monitor.py" src/
elif [ -n "$PREFECT_API_KEY" ]; then
    echo "Authenticating with Prefect Cloud..."
    prefect config set PREFECT_API_KEY="$PREFECT_API_KEY"
    prefect config set PREFECT_API_URL="$PREFECT_API_URL"
    
    echo "Applying Prefect deployment..."
    python infra/deployment.py
    
    echo "Starting Prefect worker 'koyeb-runner'..."
    prefect worker start --pool "default-agent-pool" --work-queue "koyeb-runner"
else
    echo "No PREFECT_API_KEY found. Falling back to local monitor loop..."

    exec python src/monitor.py
fi
