You are auditing my arbitrage bot for real workflow bugs.

Do not focus on style, formatting, or generic best practices.

I want confirmed bugs and serious risks that can cause wrong trades, duplicated orders, missed execution, stale signals, incorrect PnL, broken state, or financial exposure.

For each file I provide:

1. Summarize what the file does.
2. Identify which workflow it belongs to.
3. Identify what state it reads/writes.
4. Identify assumptions it makes.
5. Find confirmed bugs.
6. Find serious risks.
7. For each finding:
   - Severity: Critical / High / Medium / Low
   - Exact code location
   - Concrete sequence of events that triggers it
   - Expected behavior
   - Actual behavior
   - Financial or workflow consequence
   - Smallest safe fix
   - Test that would catch it
8. Mark anything uncertain as “risk”, not “bug”.

Important:
Do not refactor yet.
Do not rewrite architecture yet.
Do not optimize performance yet.
First, prove where the bot can break.
