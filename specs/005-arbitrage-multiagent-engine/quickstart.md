# Quickstart: Multi-Agent Arbitrage Engine

## Prerequisites
- Python 3.12+
- API Keys: Polygon.io (Stocks Tier), Google Gemini, Telegram Bot Token, Trading 212 API Key.

## Setup Instructions

1. **Environment Configuration**:
   Create a `.env` file in the root directory:
   ```bash
   POLYGON_API_KEY=your_key
   GEMINI_API_KEY=your_key
   TELEGRAM_BOT_TOKEN=your_token
   TELEGRAM_CHAT_ID=your_id
   TRADING_212_API_KEY=your_key
   TRADING_212_MODE=demo  # or live
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Initialize Database**:
   ```bash
   python scripts/init_db.py
   ```

4. **Define Arbitrage Pairs**:
   Update `src/config.py` with your 20 initial pairs:
   ```python
   ARBITRAGE_PAIRS = [
       {'ticker_a': 'KO', 'ticker_b': 'PEP'},
       {'ticker_a': 'MA', 'ticker_b': 'V'},
       # ... up to 20 pairs
   ]
   ```

5. **Run in Shadow Mode**:
   Validates strategy in real-time without capital risk.
   ```bash
   python src/monitor.py --mode shadow
   ```

6. **View Audit Reports**:
   Reports are generated automatically at the end of the trading day (21:00 WET) in the `reports/` folder.
   ```bash
   open reports/tearsheet_latest.html
   ```

## Key Commands
- `/status`: Get current Z-scores and active trades via Telegram.
- `/approve`: Manual approval for high-value trades (requested via notification).
- `/stop`: Panic button to close all open virtual positions.
