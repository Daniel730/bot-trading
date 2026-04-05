# Quickstart: Elite Micro-Investor Bot

## Prerequisites
- **Redis**: Required for local order book shadowing.
- **OpenAI API Key**: Required for TTS voice synthesis.
- **Polygon.io API Key**: Required for real-time WebSockets.
- **Trading 212 API Key**: Required for fractional execution.

## Setup
1. **Infrastructure**:
   ```bash
   # Start the environment with Redis
   docker-compose up -d redis bot
   ```
2. **Environment**:
   Update your `.env` with:
   ```env
   REDIS_URL=redis://localhost:6379/0
   OPENAI_API_KEY=sk-...
   POLYGON_API_KEY=...
   SGOV_SWEEP_TICKER=SGOV
   MIN_SWEEP_THRESHOLD=10.0
   ```
3. **Initialize DB**:
   ```bash
   python scripts/init_db.py --feature 015
   ```

## Key Commands (Telegram)
- `/invest [amount] [ticker]` - Execute a fractional trade with 2% fee protection.
- `/why [ticker]` - Generate a visual Monte Carlo and voice note summary.
- `/cash` - Check your idle cash balance and current SGOV yield sweep status.
- `/macro` - View the current Volatility Surface and Auto-Hedge (DEFCON) status.

## Verification
- **LOB Test**: Check Redis keys (`price:AAPL`) to ensure Polygon WebSockets are updating the shadow book.
- **Sweep Test**: Reduce your idle cash to $0 and check if the bot auto-liquidates SGOV for a new trade.
- **Voice Test**: Request a `/why` for any ticker and verify an MP3 is sent to your Telegram.
