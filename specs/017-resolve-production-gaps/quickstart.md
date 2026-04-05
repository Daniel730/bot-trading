# Quickstart: Resolve Production Rigor Gaps

## Integration Test Scenarios

### Scenario 1: Circuit Breaker Trigger

1. **Setup**: Ensure bot is in `NORMAL` status.
2. **Action**: Mock the `SECService` or `FundamentalAnalyst` to raise `asyncio.TimeoutError` for 3 consecutive calls.
3. **Validation**: Check SQLite `system_state` table for `operational_status == 'DEGRADED_MODE'`.
4. **Validation**: Attempt a new trade entry and verify it is blocked with a log message.

### Scenario 2: Micro-Budget Friction Reject

1. **Setup**: Configure a trade signal for $2.00.
2. **Action**: Set current spread to $0.04 (approx 2% friction).
3. **Validation**: Verify `BrokerageService.place_value_order` returns status `FRICTION_REJECT`.
4. **Validation**: Ensure no order was sent to the T212 API.

### Scenario 3: Exponential Backoff Verification

1. **Setup**: Disable internet connectivity or mock `yfinance` to fail.
2. **Action**: Trigger a price lookup.
3. **Validation**: Observe logs for 3 retry attempts with timestamps showing approx 1s, 2s, and 4s intervals.

### Scenario 4: OLS Intercept Check

1. **Setup**: Use two series `s1 = 2*s2 + 50 + noise`.
2. **Action**: Run `ArbitrageService.check_cointegration(s1, s2)`.
3. **Validation**: Verify the returned hedge ratio is approx 2.0 (not 2.5) and the intercept term is captured in internal logs.
