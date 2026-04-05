# Data Model: Elite Micro-Investor Bot

## Entities

### 1. CashSweep
Tracks the movement of idle cash into and out of high-yield vehicles (e.g., SGOV).
| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary Key |
| `timestamp` | DATETIME | Time of the sweep |
| `type` | ENUM | `SWEEP_IN` (to SGOV), `SWEEP_OUT` (for trade) |
| `amount` | DECIMAL(18,6) | Fiat value moved |
| `ticker` | TEXT | Usually `SGOV` or `MMF` |
| `balance_after` | DECIMAL(18,6) | Total idle cash remaining |

### 2. VolatilitySurface
Snapshot of market stress metrics for the Auto-Hedging Protocol.
| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary Key |
| `vix_value` | FLOAT | Current CBOE VIX value |
| `skew_value` | FLOAT | Current SKEW index value |
| `hedging_state` | ENUM | `NORMAL`, `DEFCON_1` (Hedging active) |
| `hedged_asset` | TEXT | Asset used for hedge (e.g., `SQQQ`) |
| `created_at` | DATETIME | Timestamp of snapshot |

### 3. SentimentAnomaly
Divergence data from social and dark pool monitoring.
| Field | Type | Description |
|-------|------|-------------|
| `ticker` | TEXT | Asset symbol |
| `social_score` | FLOAT | Normalized Reddit/X volume/sentiment |
| `dark_pool_volume` | FLOAT | Large block trade divergence score |
| `anomaly_detected` | BOOLEAN | True if social and dark pool converge |
| `confidence` | FLOAT | ML model confidence score |

### 4. TelemetryRecord (Federated Intelligence)
Anonymized trade outcome for global optimization.
| Field | Type | Description |
|-------|------|-------------|
| `payload_id` | UUID | Primary Key |
| `signal_type` | TEXT | e.g., `MeanReversion`, `Momentum` |
| `theoretical_pnl` | FLOAT | Projected profit |
| `actual_pnl` | FLOAT | Realized profit after slippage/fees |
| `agent_weights` | JSON | Confidence scores of involved agents |
| `is_synced` | BOOLEAN | Sent to global server |

### 5. TradeThesis (Enhanced)
Natural language and structured reasoning for a trade.
| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary Key |
| `trade_id` | TEXT | Link to `trade_records` |
| `thesis_text` | TEXT | 3-sentence minimum reasoning |
| `monte_carlo_path` | TEXT | File path to SVG/PNG visualization |
| `voice_note_path` | TEXT | File path to MP3/OGG summary |
| `kelly_fraction` | FLOAT | Calculated size multiplier |
| `explainability_scores` | JSON | SHAP/LIME values for agent influence (Constitution III) |
| `risk_veto_status` | TEXT | `PASSED`, `REJECTED_FEE`, `REJECTED_VOL` |

### 6. SyntheticOrder
In-memory representation of trailing stops and conditional orders for fractional shares (FR-012).
| Field | Type | Description |
|-------|------|-------------|
| `ticker` | TEXT | Asset symbol |
| `activation_price` | FLOAT | Price when stop was set |
| `trailing_pct` | FLOAT | e.g., 0.05 for 5% stop |
| `highest_price` | FLOAT | High-water mark for trailing logic |
| `is_active` | BOOLEAN | Tracking status |
