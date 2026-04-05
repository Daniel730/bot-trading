# Telegram Command Interface (Internal Contract)

This contract defines the natural language and slash commands exposed to the user for low-budget investing and portfolio management.

## Slash Commands

| Command | Arguments | Description |
|---------|-----------|-------------|
| `/invest` | `[amount] of [ticker]` | Executes a value-based fractional market order. |
| `/invest schedule` | `amount=X frequency=Y day=Z strategy=S` | Configures a recurring DCA schedule. |
| `/portfolio` | `define [id] ticker=T weight=W ...` | Creates or updates a portfolio strategy. |
| `/why` | `[ticker]` | Returns the "Investment Thesis" for the latest trade. |
| `/macro` | `N/A` | Returns a summary of current interest rates and market trend. |

## Natural Language Parsing (Persona-Driven)

The **Portfolio Manager Agent** MUST be able to parse and map the following intent patterns:

- **Intent: Micro-Investment**
  - "I just got a $20 tip, put it into something safe."
  - **Action**: Map to `/invest 20 strategy=safe` (or distribute $20 across "safe" assets).
  
- **Intent: Query Thesis**
  - "Why did we buy AAPL today?"
  - **Action**: Map to `/why AAPL`.
  
- **Intent: Market Context**
  - "How's the economy looking?"
  - **Action**: Map to `/macro`.

## Response Formats

### Investment Thesis
```text
Portfolio Manager 🛡️: I invested $5.00 in AAPL because:
1. Fundamental Agent noted a strong balance sheet from the latest SEC RAG data.
2. Bull Agent identified positive sentiment on current price action.
3. Fee Analyzer confirmed friction costs were only 0.2% ($0.01).
```

### Macro Summary
```text
Macro Economic Agent 🌐:
- 10Y Yield: 4.25% (Rising - suggest defensive allocation)
- VIX Index: 14.5 (Low volatility - risk-on conditions)
- Market Trend: Bullish (SPY above 50DMA)
```
