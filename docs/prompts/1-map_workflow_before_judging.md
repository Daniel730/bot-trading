Before finding bugs, reconstruct the workflow.

From the code I provide, map:

1. Startup sequence.
2. Market data ingestion sequence.
3. Signal generation sequence.
4. Opportunity validation sequence.
5. Risk check sequence.
6. Order creation sequence.
7. Order submission sequence.
8. Fill handling sequence.
9. Error/retry sequence.
10. Shutdown/restart sequence.

For each sequence:

- List the functions/classes involved.
- List the inputs and outputs.
- List the state that is read or mutated.
- List assumptions made by the code.
- Mark any missing link or unknown behavior.

Do not suggest fixes yet.

Before proposing a fix, explain the concrete sequence of events that makes this bug happen.
If you cannot reproduce or reason through the bug from the code, mark it as a risk, not a confirmed bug.
