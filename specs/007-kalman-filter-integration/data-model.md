# Data Model: Kalman Filter State

**Feature**: 007-kalman-filter-integration  
**Date**: 2026-03-31

## Entities

### `KalmanState`
Persists the internal state of the filter for each active trading pair.
- `pair_id`: UUID (Foreign Key to `arbitrage_pairs`)
- `timestamp`: DateTime (Last update)
- `alpha`: Float (Intercept of the spread)
- `beta`: Float (Hedge ratio / Slope)
- `p_matrix`: JSON (State covariance matrix, 2x2)
- `q_matrix`: JSON (Process noise matrix, 2x2)
- `r_value`: Float (Measurement noise variance)

## State Transitions

1. **Initialization (Startup)**:
   - If `KalmanState` exists for `pair_id`, load `alpha`, `beta`, and `p_matrix`.
   - If not, run a 30-day OLS via `ArbitrageService` to seed the initial `alpha` and `beta`. Set `p_matrix` to a high-uncertainty identity matrix.
2. **Update (Per Tick)**:
   - Perform the Predict/Correct cycle.
   - Overwrite `alpha`, `beta`, and `p_matrix` in the database.
3. **Reset**:
   - If a "Structural Break" is detected by the News Analyst, the filter state can be reset to re-seed from new data.

## Relationships
- One `ArbitragePair` has one `KalmanState`.
- Every `Signal` recorded will now include the `beta` value produced by the Kalman Filter at that exact timestamp.
