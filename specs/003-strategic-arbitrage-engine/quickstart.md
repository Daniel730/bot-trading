# Quickstart: Strategic Arbitrage Engine

## Prerequisites
- Docker & Docker Compose
- Trading 212 API Key (Beta)
- Polygon.io API Key (Free tier)
- Telegram Bot Token & Chat ID
- Gemini API Key

## Configuration
1. **Prepare `.env`**:
   Copy `.env.template` to `.env` and fill in your keys.
   ```bash
   cp .env.template .env
   ```
2. **Set PAPER_TRADING**:
   Ensure `PAPER_TRADING=true` in `.env` for your first run.

## Deployment
1. **Launch Containers**:
   ```bash
   docker-compose up --build -d
   ```
2. **Monitor Logs**:
   ```bash
   docker-compose logs -f bot
   ```

## User Workflow
1. **Signal Generation**: The bot monitors pairs and sends an alert to Telegram when Z-Score > 2.5.
2. **AI Validation**: Gemini CLI automatically analyzes news and provides a rationale.
3. **Manual Approval**: Click "Approve" on the Telegram message to execute the trade.
4. **Execution**: The bot sends market orders to Trading 212 and logs the trade.
