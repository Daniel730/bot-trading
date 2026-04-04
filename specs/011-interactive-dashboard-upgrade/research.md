# Research: Interactive Dashboard Upgrade

## Technical Context
- **Frontend Framework**: Vanilla JS with Lucide Icons (existing) or lightweight React/Preact. Given the "beautiful and functional prototype" mandate, we will upgrade the existing Vanilla JS structure to use a more robust component-based approach without full React overhead if possible, or use Vite + React for better scalability.
- **Styling**: Vanilla CSS (Tailwind avoided per guidelines unless requested). Existing Cyberpunk theme will be enhanced with real-time charts.
- **Real-time Data**: SSE (Server-Sent Events) via FastAPI (existing) will be expanded to include more granular data.
- **Visuals**: Chart.js or Lightweight Charts for performance tracking.

## Decisions

### 1. Data Source Strategy
- **Decision**: Expand `DashboardService` to poll `PersistenceManager` and `ShadowService` every 5 seconds for portfolio metrics.
- **Rationale**: Avoids over-complicating the `Monitor` loop while ensuring the UI is never more than 5s stale.
- **Alternatives Considered**: Direct push from `Monitor`. Rejected to keep concerns separated.

### 2. UI Architecture
- **Decision**: Implement a "Modular HUD" in the frontend.
- **Rationale**: Allows independent updates of metrics (Revenue, Investments) without re-rendering the whole page.
- **Alternatives Considered**: Full SPA (React). Rejected for MVP speed, but will keep code modular.

### 3. Metric Definitions
- **Revenue**: Sum of `total_pnl` from `trade_records` (is_shadow=True).
- **Investments**: Sum of `(size_a * entry_price_a + size_b * entry_price_b)` for 'Open' trades.
- **Profit Production**: Current Daily PnL trend.
- **Signals**: Real-time list of 'Analyzing' pairs and their Z-scores.

## Best Practices
- **SSE**: Ensure `EventSource` handles reconnections gracefully.
- **Performance**: Use CSS transitions for the "Robot" animations to keep Main Thread free for data parsing.
- **Security**: Sanitize all data coming from the SQLite DB before rendering.
