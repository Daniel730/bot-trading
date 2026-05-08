Audit the strategy logic for correctness bugs.

Focus on:

1. False arbitrage signals.
2. Backtest/live mismatch.
3. Lookahead bias.
4. Using candle close data before the candle is closed.
5. Using old spread/z-score/cointegration values in live decisions.
6. Incorrect Kalman filter update order.
7. Incorrect hedge ratio usage.
8. Incorrect normalization.
9. Wrong currency conversion.
10. Wrong fee model.
11. Wrong slippage model.
12. Comparing prices from different timestamps.
13. Using last traded price when bid/ask/order book should be used.
14. Signal generated from mid-price but execution done on bid/ask.
15. Profit threshold calculated before fees.
16. Profit threshold calculated in wrong unit or currency.

For each issue:

- Explain why the signal is wrong.
- Explain when it appears profitable but is not.
- Explain how to correct it.
- Give a test using fake market data.

Before proposing a fix, explain the concrete sequence of events that makes this bug happen.
If you cannot reproduce or reason through the bug from the code, mark it as a risk, not a confirmed bug.
