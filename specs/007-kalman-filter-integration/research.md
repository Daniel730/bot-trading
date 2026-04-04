# Research: Kalman Filter for Dynamic Pair Trading

**Feature**: 007-kalman-filter-integration  
**Date**: 2026-03-31

## Technical Decision: Why Kalman Filter?

### The Problem with Static OLS
The current system uses OLS (Ordinary Least Squares) over a rolling window. This has two major drawbacks:
1.  **Window Sensitivity**: A 30-day window is too slow to react to new trends, while a 5-day window is too reactive to noise.
2.  **Sudden Shifts**: When a stock goes ex-dividend or a macro shift occurs, OLS carries the "memory" of the old regime until it falls out of the window.

### The Solution: State-Space Modeling
The Kalman Filter treats the hedge ratio as a hidden state that evolves over time.
-   **Recursive**: It only needs the *previous* state and the *current* observation. No large matrices in memory.
-   **Self-Correcting**: It calculates a "Kalman Gain" to decide how much to weight the new data versus the old prediction.

## Mathematical Model

We define the system state $x_t$ as a vector containing the intercept $\alpha$ and the hedge ratio $\beta$:
$x_t = [\alpha_t, \beta_t]^T$

**Transition Equation** (Identity transition with process noise):
$x_t = x_{t-1} + w_t$ where $w_t \sim N(0, Q)$

**Observation Equation** (Predicting Ticker A price from Ticker B):
$y_t = H_t x_t + v_t$ where $v_t \sim N(0, R)$
$H_t = [1, Price_{B,t}]$

### Tuning Parameters
-   **Q (Process Noise)**: Controls how fast the beta can change. Small $Q$ = stable/slow; Large $Q$ = adaptive/nervous.
-   **R (Measurement Noise)**: Controls how much we trust the new price data.

## Implementation Strategy
1.  **Library**: We will use a lightweight implementation (using `numpy`) to maintain the "Library-First" principle and avoid heavy dependencies.
2.  **Data Flow**: 
    -   Fetch Price A and Price B.
    -   Run Kalman Update (Predict -> Correct).
    -   Output current $\beta$ and $\alpha$.
    -   Calculate Spread: $Spread = Price_A - (\beta * Price_B + \alpha)$.
    -   Z-Score = $Spread / \sqrt{Error\_Variance}$.

## Expected Risks
-   **Exploding Beta**: If $Q$ is too high, the hedge ratio might fluctuate wildly during low liquidity. Mitigation: Implement a "Reasonableness Guard" (e.g., beta must be within 0.1 to 10.0).
-   **Inversion**: In cases where assets diverge permanently, Kalman will follow the divergence. Mitigation: The Gemini AI (Principle II) must detect this as a "Structural Change" and veto the trade.
