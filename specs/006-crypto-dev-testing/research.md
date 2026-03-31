# Research: 24/7 Crypto Development Mode

## Decision: 24/7 Connectivity Strategy

- **Choice**: Use `yfinance` with Crypto tickers (`BTC-USD`, `ETH-USD`) as primary data source in `DEV_MODE`.
- **Rationale**: `yfinance` is already integrated and supports crypto 24/7 without additional API costs. It provides a reliable stream of price data to validate the `ArbitrageMonitor` logic.
- **Alternatives considered**: Polygon.io Crypto API. Rejected because it requires separate authentication and the current implementation is already skewed towards `yfinance` for historical/polling data.

## Decision: Periodic Warning Mechanism

- **Choice**: Implement a timestamp-based check in the `monitor.py` main loop.
- **Rationale**: A simple `last_warning_time` check within the existing `while True` loop is lightweight and ensures the warning appears even if cycle times vary.
- **Implementation**:
  ```python
  if settings.DEV_MODE and (now - self.last_dev_warning).total_seconds() >= 300:
      logger.warning("\n" + "!"*40 + "\n!!! DEVELOPMENT MODE ACTIVE: MONITORING CRYPTO 24/7 !!!\n" + "!"*40)
      self.last_dev_warning = now
  ```

## Decision: Resource Monitoring (CHK010)

- **Choice**: Log basic system stats (CPU/Memory usage) in `AuditService` every 30 cycles.
- **Rationale**: Prevents silent failures during extended 24/7 runs.
- **Implementation**: Use `psutil` or similar to fetch `process.cpu_percent()` and `process.memory_info().rss`.

## Decision: Startup Audit (CHK014)

- **Choice**: Log the configuration state (including `DEV_MODE` status) in the first log entry of `monitor.py`.
- **Rationale**: Ensures traceability of the execution state from the start of the process.

## Decision: Unreachable Execution Service (CHK011)

- **Choice**: If a signal is generated but the execution service (T212) is unreachable, the orchestrator MUST record the failure as a `DEV_EXECUTION_FAILURE` in the `signals` table and log a `CRITICAL` alert.
- **Rationale**: This simulates the real production behavior without halting the entire monitoring cycle.

## NEEDS CLARIFICATION Resolved

- **Q**: How to handle different ticker formats between `yfinance` and T212?
- **A**: `DEV_MODE` will map internal "test pairs" (Crypto) to "execution tickers" (Stocks like AAPL/MSFT) defined in `settings.py`.
- **Q**: Is there a limit to `yfinance` polling?
- **A**: At 1-minute intervals, we are well within rate limits for a few pairs.
