# Quickstart: Low-Budget Investor Suite

## Overview
This feature introduces fractional shares, DCA scheduling, and a Portfolio Manager agent to the bot. It is optimized for retail investors with account balances under $500.

## Setup Instructions

1.  **Configure Max Friction (Fee Threshold)**:
    Set your preferred maximum fee impact in the Telegram Terminal:
    `/config set max_friction_pct 0.015` (1.5% default)

2.  **Define a Portfolio Strategy**:
    Create a "safe" or "growth" strategy using the Portfolio Manager:
    `/portfolio define safe ticker=SPY weight=0.6 ticker=BND weight=0.4`

3.  **Schedule DCA**:
    Set up a recurring weekly investment of $15:
    `/invest schedule amount=15 frequency=weekly day=Friday strategy=safe`

4.  **Enable DRIP**:
    Enable micro-dividend reinvestment to ensure all cash is put to work:
    `/config set drip_enabled true`

## Common Commands (Telegram Terminal)

- `/invest [amount] of [ticker]`: Execute a one-time fractional value-based order.
- `/invest status`: View active DCA schedules and total amount invested.
- `/why [ticker]`: Query the Portfolio Manager for the "Investment Thesis" behind the latest trade in that asset.
- `/macro`: Get the "Big Picture" summary from the Macro Economic Agent.

## Testing Your Setup

- **Dry Run (Shadow Mode)**: Run the bot with `DEV_MODE=true` to test DCA schedules and portfolio allocation without executing real trades.
- **Fractional Test**: Use a small amount (e.g., $1.00) to verify your brokerage (T212) correctly handles fractional quantities (e.g., buying 0.0058 of AAPL).
- **Fee Check**: Submit a very small trade (e.g., $0.10) where the spread/fee exceeds 1.5%. Verify the bot correctly auto-rejects it.
