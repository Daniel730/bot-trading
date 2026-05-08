Audit this bot as a state machine.

Identify all possible states, including:

- idle
- collecting market data
- signal detected
- opportunity validated
- risk approved
- order pending
- first leg submitted
- first leg filled
- first leg rejected
- second leg submitted
- second leg filled
- second leg rejected
- partial fill
- cancelling
- hedging
- cooldown
- error
- stopped/restarted

For each state:

1. What event moves the bot into this state?
2. What event moves it out?
3. What state variables are required?
4. What invalid transitions are possible in the current code?
5. What transition is missing?
6. What transition can happen twice?
7. What transition can happen out of order?
8. What happens if the process crashes in this state?

Find bugs where the code assumes a happy path.

Before proposing a fix, explain the concrete sequence of events that makes this bug happen.
If you cannot reproduce or reason through the bug from the code, mark it as a risk, not a confirmed bug.
