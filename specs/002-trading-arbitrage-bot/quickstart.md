# Quickstart: Trading Arbitrage Bot

**Feature**: 002-trading-arbitrage-bot
**Date**: 2026-03-27

## Prerequisites
- Python 3.11+
- Gemini CLI installed and authenticated.
- Trading 212 Invest/ISA account with API credentials.
- Polygon.io Free Tier API key.
- Telegram Bot Token and Chat ID.

## Setup
1. **Clone & Install**:
   ```bash
   pip install fastmcp requests yfinance pytz python-dotenv statsmodels pandas tenacity
   ```
2. **Configure `.env`**:
   ```ini
   T212_API_KEY=your_key
   T212_API_SECRET=your_secret
   POLYGON_API_KEY=your_key
   TELEGRAM_BOT_TOKEN=your_token
   TELEGRAM_CHAT_ID=your_id
   MAX_ALLOCATION_PERCENTAGE=10.0  # Principle II
   OPERATING_TIMEZONE=WET
   ```
3. **Initialize Database**:
   ```bash
   python scripts/init_db.py  # Create SQLite tables and set targets
   ```
4. **Register MCP Tools**:
   ```bash
   fastmcp install gemini-cli src/mcp_server.py
   ```

## Running the Bot
1. **Start the Monitor**:
   ```bash
   python src/monitor.py
   ```
   *Note: On startup, the bot will re-sync current quantities from Trading 212.*

2. **Handle Confirmations**:
   When a signal is validated by AI, you will receive a Telegram message with `[Approve]` and `[Reject]` buttons. The trade will only execute after you click `[Approve]`.

## Constitutional Safety Checks
- **Hours**: Orders blocked outside 14:30 - 21:00 WET.
- **Risk**: Single-trade allocation capped at 10% (or `.env` value).
- **Control**: Mandatory manual confirmation for all rebalances.
