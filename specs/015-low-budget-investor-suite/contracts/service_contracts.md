# Service Contracts: Elite Micro-Investor Bot

## 1. VoiceSynthesisContract (OpenAI TTS)
| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `generate_summary(text: str)` | `text` (min 20 chars) | `voice_note_path` (MP3/OGG) | Uses `tts-1` model with `alloy` or `onyx` voice to synthesize a trade summary. |
| `cleanup_voice_notes()` | - | `count: int` | Deletes voice files older than 48 hours to save disk space. |

## 2. VisualizationContract (Monte Carlo & Charts)
| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `generate_what_if(ticker: str, amount: float)` | `ticker`, `fiat_amount` | `image_path` (PNG) | Runs a 1,000-path Monte Carlo simulation for 6-month projected growth. |
| `generate_vix_surface()` | - | `image_path` (PNG) | Visualizes the current VIX vs. historical 30-day surface for risk awareness. |

## 3. FederatedTelemetryContract (Anonymized Sync)
| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `sync_outcomes()` | - | `success: bool` | Batches unsynced `TelemetryRecord` objects and POSTs to the global server. |
| `receive_weight_updates()` | - | `updated_weights: JSON` | GETs latest optimized global weights for the agent ensemble. |

## 4. CashManagementContract (Yield Sweeps)
| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `sweep_idle_cash()` | `min_threshold: float` | `executed_value: float` | Checks uninvested balance and buys SGOV if above threshold. |
| `liquidate_for_trade(amount: float)` | `target_amount: float` | `actual_liquidated: float` | Sells exactly the fractional amount of SGOV needed to fund a high-priority trade. |
