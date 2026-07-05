Audit this code for concurrency and race-condition bugs.

Look for:

1. Shared mutable state accessed by multiple tasks.
2. Signal generated while market data is being updated.
3. Order state updated by multiple callbacks.
4. Duplicate event handling.
5. Websocket messages arriving out of order.
6. REST and websocket data overwriting each other.
7. Retry task still running after cancellation.
8. Background task exceptions being swallowed.
9. Task created but never awaited.
10. Locks missing where state must be atomic.
11. Locks used too broadly and hiding bugs.
12. Queue consumers falling behind.
13. Race between balance check and order submission.
14. Race between stop signal and active execution.
15. Race between two opportunities using same capital.

For each bug:

- Show exact shared variable or async task.
- Explain the race timeline step by step.
- Explain actual bad outcome.
- Give minimal fix.
- Give a deterministic test or simulation.

Before proposing a fix, explain the concrete sequence of events that makes this bug happen.
If you cannot reproduce or reason through the bug from the code, mark it as a risk, not a confirmed bug.
