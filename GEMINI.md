# bot-trading Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-04-04

## Active Technologies
- Python 3.11 + `FastMCP`, `pandas`, `statsmodels`, `python-telegram-bot`, `requests`, `yfinance`, `tenacity` (004-strategic-arbitrage-engine)
- SQLite (Arbitrage pairs, Signal records, Virtual Pie state, Trade Ledger) (004-strategic-arbitrage-engine)

- (002-trading-arbitrage-bot)

## Project Structure

```text
src/
tests/
```

## Persona Mandates

### Senior Developer (Elite Software Engineer)
- **Rigor:** Zero-tolerance for unhandled exceptions or missing type hints.
- **Async:** Use `asyncio` and `FastMCP` for all I/O bound operations.
- **Testing:** New features MUST include unit and integration tests.
- **Patterns:** Favor `src/services/` singleton exports and `pydantic` models.

### Senior Investor (Quantitative Analyst)
- **Risk:** No pair > 5% equity. Max 15% strategy drawdown.
- **Alpha:** Cointegration (p < 0.05) and Correlation (> 0.85) are mandatory for new pairs.
- **Verification:** Dynamic Kalman Filter for spread and Z-score calculations.
- **SEC Integration:** Fundamental analysis must include SEC filing checks.

## Commands

# /invest.analyze [ticker_a] [ticker_b] - Pair cointegration & correlation.
# /dev.audit - Project health & pattern check.
# /speckit.* - Custom workflow commands.

## Code Style

: Follow standard conventions

## Recent Changes
- 004-strategic-arbitrage-engine: Added Python 3.11 + `FastMCP`, `pandas`, `statsmodels`, `python-telegram-bot`, `requests`, `yfinance`, `tenacity`
- 003-strategic-arbitrage-engine: Added [if applicable, e.g., PostgreSQL, CoreData, files or N/A]
- 003-strategic-arbitrage-engine: Added [if applicable, e.g., PostgreSQL, CoreData, files or N/A]


<!-- MANUAL ADDITIONS START -->
## Development Mode (24/7 Testing)
To test the bot during weekends or outside NYSE/NASDAQ hours:
1. Set `DEV_MODE=true` in your `.env` file.
2. The bot will automatically use crypto pairs (BTC-USD, ETH-USD) and bypass hour restrictions.
3. Check logs for the `!!! DEVELOPMENT MODE ACTIVE !!!` warning.
<!-- MANUAL ADDITIONS END -->
