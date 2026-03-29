# Implementation Plan: 24/7 Crypto Development Mode

**Branch**: `006-crypto-dev-testing` | **Date**: 2026-03-29 | **Spec**: [specs/006-crypto-dev-testing/spec.md]
**Input**: Plan to support 24/7 testing using Crypto market.

## Summary

This feature adds a `DEVELOPMENT_MODE` toggle to allow the bot to operate 24/7, bypassing NYSE/NASDAQ hour restrictions. It introduces crypto pairs (BTC, ETH, LTC) into the configuration to enable weekend testing of the entire arbitrage engine, including data fetching, Z-score calculation, and multi-agent debate.

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: yfinance, pandas
**Storage**: SQLite (to record dev trades)
**Target Platform**: Local / Docker
**Constraints**: Bypasses Principle IV (Strict Operation) only when `DEV_MODE=True`.

## Constitution Check

- **IV. Strict Operation**: VIOLATION (Justified). Bypassing market hours is strictly for development and testing of the system's infrastructure. It MUST NOT be enabled in production for stock arbitrage.

## Project Structure

### Documentation

```text
specs/006-crypto-dev-testing/
├── plan.md
├── research.md
└── tasks.md
```

### Proposed Changes

1. **`src/config.py`**:
   - Add `DEV_MODE: bool = False`.
   - Add `CRYPTO_TEST_PAIRS: list` with BTC-USD/ETH-USD.
2. **`src/monitor.py`**:
   - Modify `run` loop to skip hour checks if `settings.DEV_MODE` is true.
   - Use `CRYPTO_TEST_PAIRS` if in dev mode.
3. **`src/services/data_service.py`**:
   - Ensure ticker format handling for crypto.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Bypassing hours | 24/7 validation | Waiting for Monday morning prevents rapid iteration on weekends. |
