# Trading Bot Enhancements Specification

## 1. UI/UX & Security Polish (Module 1)

### 1.1 Sensitive Input Visibility
- **File:** `frontend/src/pages/SettingsPage.tsx`
- **Feature:** Add a state `visibleFields: Set<string>`. For any input where `item.sensitive` is true, render a toggle button (👁️/🙈) next to the input to switch its `type` between `password` and `text`.

### 1.2 2FA Success Feedback
- **File:** `frontend/src/App.tsx`
- **Feature:** In `handleConfirmSaveWithOtp`, after successfully calling `updateConfig`, ensure that `refreshConfig()` is awaited and a prominent `systemMessage` ("Configuration updated successfully!") is displayed so the user knows the state is saved.

## 2. Bot Control UX (Module 2)

### 2.1 Control Button State Tracking
- **File:** `frontend/src/pages/BotControlPage.tsx`
- **Feature:** Add `pendingAction` state. When "Start/Stop/Restart" is clicked, button changes to "Starting.../Stopping.../Restarting..." and disables itself. It listens to `currentBotState` (via `useTelemetry`) and clears `pendingAction` once the backend state catches up to the intended state.

## 3. Intelligent Pair Discovery & Rotation (Module 3 & 4)

### 3.1 20-Pair "Elite" Limit
- **Config:** Add `MAX_ACTIVE_PAIRS = 20` to `src/config.py`.
- **Database (`TradingPair`):** Serve as the single source of truth for the active universe. Pairs have `status = 'Active'` or `status = 'Scout'`.
- **Monitor Runtime:** `monitor.py` will load only the `Active` pairs from the database at startup. It will periodically (e.g., every 6 hours) query the database for hot-swaps.

### 3.2 Discovery Engine (Scouting)
- **Agent:** `PortfolioManagerAgent`
- **Mechanism:** A background process (triggered via cron or API endpoint `/api/pairs/discover`) fetches the S&P 500 and Top 50 Crypto assets.
- **Filtration:** Discards cross-currency pairs or pairs exceeding `PAIR_MAX_ROUND_TRIP_COST_PCT`.
- **Cointegration:** Runs `check_rolling_cointegration` on candidate pairs. Pairs that pass are saved to `universe_candidates` with their Sortino ratio and expected returns.

### 3.3 Dynamic Rotation
- **Logic:** During the daily global reset in `monitor.py`, compare the bottom-performing `Active` pairs (based on recent PnL or degraded cointegration) against the top `Scout` candidates. If a scout significantly outperforms an active pair, swap their statuses in the `TradingPair` database.

### 3.4 Dashboard Integration
- **Endpoint:** Add `POST /api/pairs/discover` to trigger the scouting run.
- **UI:** Add a "Search & Update Eligibles" button in the dashboard to manually trigger discovery.
