# Quickstart: SEC RAG Analyst

## 1. Prerequisites
- **Python 3.11**
- **SEC User-Agent String**: Required for EDGAR (Format: `Company Name admin@email.com`).
- **Dependencies**: `pip install edgartools pydantic tenacity`.

## 2. Configuration
Add the following to your `.env` file:
```env
SEC_USER_AGENT="Project-Arbitrage-Elite admin@example.com"
GEMINI_API_KEY="your-api-key"
```

## 3. Usage (CLI Test)
Run the manual validation script to verify CIK mapping and SEC extraction:
```bash
python scripts/verify_sec_parser.py --ticker AAPL
```

## 4. Integration Verification
1. Start the bot: `python src/monitor.py`.
2. Observe the logs for: `[FundamentalAnalyst] Starting SEC analysis for ticker XYZ...`.
3. Check the SQLite DB for results:
```sql
SELECT * FROM fundamental_signals WHERE structural_integrity_score < 40;
```

## 5. Development Mode (Crypto Fallback)
If `DEV_MODE=true` is set, the SEC RAG analyst is skipped for crypto pairs (BTC-USD, etc.), returning a default confidence score.
