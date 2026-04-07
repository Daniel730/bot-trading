# bot-trading Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-04-07

## Active Technologies
- Python 3.11 + `FastMCP`, `pandas`, `statsmodels`, `python-telegram-bot`, `requests`, `yfinance`, `tenacity`, `grpcio`, `grpcio-tools`, `numpy`, `scipy` (028-dynamic-risk-and-volatility-switch)
- SQLite (Arbitrage pairs, Signal records, Virtual Pie state, Trade Ledger, DCA Schedules, Portfolio Strategies) (014-low-budget-investor-suite)
- PostgreSQL (R2DBC) (028-dynamic-risk-and-volatility-switch)
- Redis (Idempotency, Entropy, Latency Telemetry) (028-dynamic-risk-and-volatility-switch)
- gRPC (Python/Java with Nanosecond Interceptors) (027-model-calibration)

## Project Structure

```text
src/
  agents/
    portfolio_manager_agent.py (Feature 014)
    macro_economic_agent.py (Feature 014)
  services/
    dca_service.py (Feature 014)
    performance_service.py (Feature 028)
    volatility_service.py (Feature 028)
    execution_service_client.py (Feature 027)
    calibration_service.py (Feature 027)
```

## Recent Changes
- 028-dynamic-risk-and-volatility-switch: Added Performance Service (Sharpe/Drawdown) and Volatility Switch (L2 Entropy).
- 027-model-calibration: Added gRPC Latency Monitoring (Nanosecond Interceptors), Redis Idempotency hardening, and Shadow Mode Fill Realism Audit (Walk-the-Book VWAP).
- 014-low-budget-investor-suite: Added Fractional Engine, DCA Service, Portfolio Manager, and Macro Agent.

### Senior Developer (Elite Software Engineer)
- **Rigor:** Zero-tolerance for unhandled exceptions or missing type hints.
- **Async:** Use `asyncio` and `FastMCP` for all I/O bound operations.
- **Testing:** New features MUST include unit and integration tests. (MANDATORY for 027)
- **Patterns:** Favor `src/services/` singleton exports and `pydantic` models.
- **Fractional Precision:** Use 6 decimal places for fractional share calculations (Feature 014).
- **Latency Monitoring:** Sub-millisecond gRPC RTT is a hard requirement. `LATENCY_ALARM` triggers if >10% of samples exceed 1ms.

### Senior Investor (Quantitative Analyst)
- **Alpha Verification:** "Achievable Alpha" must be verified via `CalibrationService` audits against L2 snapshots.
- **Simulation Fidelity:** Shadow Mode must penalize trade size via 0.5bps impact per 10% depth consumed.
- **Clock Sync:** Clock drift between environments must remain <100μs (enforced via `chrony`).

### Senior Investor (Quantitative Analyst)
- **Risk:** No pair > 5% equity. Max 15% strategy drawdown.
- **Alpha:** Cointegration (p < 0.05) and Correlation (> 0.85) are mandatory for new pairs.
- **Verification:** Dynamic Kalman Filter for spread and Z-score calculations.
- **SEC Integration:** Fundamental analysis must include SEC filing checks.
- **Retail Optimization:** Maintain < 1.5% friction for micro-investments (Feature 014).

## Commands

# /invest.set_goal name="Goal" amount=X date=YYYY-MM-DD risk=Level - Configure a long-term financial target.
# /invest.dca amount=X frequency=Interval strategy=ID - Setup automated recurring micro-investments.
# /invest.life_event event="Name" date=YYYY-MM-DD - Report life changes to adjust your investment horizon.
# /invest.why_buy TICKER - Returns the detailed "Investment Thesis" for a recent trade.
# /invest.monitor_stops - Check current synthetic stops for fractional positions.
# /invest.analyze [ticker_a] [ticker_b] - Pair cointegration & correlation.
# /dev.audit - Project health & pattern check.
# /speckit.* - Custom workflow commands.

## Code Style

: Follow standard conventions

## Recent Changes
- 014-low-budget-investor-suite: Added Fractional Engine, DCA Service, Portfolio Manager, and Macro Agent.
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
