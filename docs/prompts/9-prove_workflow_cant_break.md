Try to prove that this workflow is correct.

For each major workflow:

- market data → signal
- signal → validation
- validation → risk approval
- risk approval → order submission
- order submission → fill handling
- fill handling → PnL/state update
- error → recovery

Answer:

1. What must be true before this workflow starts?
2. What must be true after it ends?
3. What can go wrong in the middle?
4. Does the code handle every branch?
5. Which branch is missing?
6. Which branch assumes success?
7. Which branch can leave state inconsistent?
8. Which branch can lose money?

Be adversarial. Your goal is to break the workflow.

Before proposing a fix, explain the concrete sequence of events that makes this bug happen.
If you cannot reproduce or reason through the bug from the code, mark it as a risk, not a confirmed bug.
