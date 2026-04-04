# Quickstart: Strategic Arbitrage Engine

## Prerequisites
- Docker and Docker Compose installed.
- Trading 212 API Key (Beta) and Secret.
- Telegram Bot Token and Chat ID.
- Gemini API Key.

## Setup
1. **Clone & Config**:
   Copy `.env.template` to `.env` and fill in credentials.
2. **Launch Infrastructure**:
   ```bash
   docker-compose up --build -d
   ```
3. **Register MCP Tools**:
   ```bash
   gemini mcp add arbitrage-engine http://mcp-server:8000/sse --type sse
   ```

## Running a Strategy
1. **Seed Data**: Run `python scripts/init_db.py` to add your first pair (e.g., KO/PEP).
2. **Monitor**: The bot will start polling prices. Check logs:
   ```bash
   docker-compose logs -f bot
   ```
3. **Approve Trades**: When a signal is detected and validated by AI, you will receive a Telegram message. Click **Approve** to execute.

## Paper Trading
Switch `PAPER_TRADING=true` in `.env` to simulate execution in the `TradeLedger` without hitting the brokerage API.
