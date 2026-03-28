# Quickstart: Strategic Arbitrage Engine

## Prerequisites
- Python 3.11+
- Trading 212 API Key (Beta)
- Polygon.io API Key (Free tier, WebSockets)
- Telegram Bot Token
- Gemini CLI installed

## Setup
1. **Clone & Install**:
   ```bash
   pip install fastmcp yfinance polygon-api-client python-telegram-bot statsmodels pandas tenacity quantstats
   ```
2. **Configure `.env`**:
   ```ini
   T212_API_KEY=your_key
   T212_API_SECRET=your_secret
   POLYGON_API_KEY=your_key
   TELEGRAM_BOT_TOKEN=your_token
   TELEGRAM_CHAT_ID=your_id
   PAPER_TRADING=true
   ACCOUNT_BASE_CURRENCY=EUR
   ```
3. **Initialize DB**:
   ```bash
   python scripts/init_db.py
   ```
4. **Register MCP Tools**:
   ```bash
   fastmcp install gemini-cli src/mcp_server.py
   ```

## Running the Engine
1. **Start the Orchestrator**:
   ```bash
   python src/monitor.py
   ```
2. **Paper Trading Mode**:
   Check the logs to see virtual trades being recorded in `TradeLedger`.
3. **Live Trading**:
   Switch `PAPER_TRADING=false` in `.env`.
