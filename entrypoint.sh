#!/bin/bash
set -e

# 1. Database Initialization (Only if using SQLite, but we recommend Postgres for production)
# In production, ensure DATABASE_URL is set to your Supabase/Postgres instance
python scripts/init_db.py

# 2. Authenticate with Prefect (Required for production monitoring)
if [ -n "$PREFECT_API_KEY" ]; then
    echo "Authenticating with Prefect Cloud..."
    prefect config set PREFECT_API_KEY="$PREFECT_API_KEY"
    prefect config set PREFECT_API_URL="$PREFECT_API_URL"
    
    # 3. Apply the deployment (This registers the flow with Prefect Cloud)
    echo "Applying Prefect deployment..."
    python deployment.py
    
    # 4. Start the worker (Wait for and execute flows)
    echo "Starting Prefect worker 'koyeb-runner'..."
    prefect worker start --pool "default-agent-pool" --work-queue "koyeb-runner"
else
    echo "No PREFECT_API_KEY found. Falling back to local monitor loop..."
    # Local fallback for development (non-orchestrated)
    exec python src/monitor.py
fi
