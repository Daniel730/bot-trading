# Quickstart: 24/7 Crypto Development Mode

## Prerequisites

1.  Python 3.11 environment.
2.  Trading 212 API Key (Demo/Test account recommended).
3.  Telegram Bot Token (for approval notifications).

## Setup

1.  **Configure `.env`**:
    ```bash
    DEV_MODE=true
    TRADING_212_MODE=demo
    # CRYPTO_TEST_PAIRS is defined in src/config.py by default
    ```

2.  **Run the monitor**:
    ```bash
    python -m src.monitor
    ```

3.  **Expectation**:
    -   Bot skips NYSE/NASDAQ hour checks.
    -   `!!! DEVELOPMENT MODE ACTIVE !!!` warning appears every 5 minutes.
    -   Monitoring `BTC-USD` and `ETH-USD` (via `yfinance`).
    -   Orchestrator called on crypto signals.

## Validation (SC-001)

Check logs for the connectivity success rate:
`2026-03-31 15:00:00 - INFO - Connectivity: 100% (Cycle: 5, Successes: 5)`

## Manual Testing (T212 Path)

If a crypto signal triggers an IA confidence > 0.5:
1.  Receive Telegram approval request.
2.  Approve.
3.  Bot attempts `BUY` on `KO` (mapped from test tickers) to validate the T212 execution path.
