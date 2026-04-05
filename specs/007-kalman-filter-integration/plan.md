# Implementation Plan: Kalman Filter Integration

**Branch**: `007-kalman-filter-integration` | **Date**: 2026-03-31 | **Spec**: `/specs/007-kalman-filter-integration/spec.md`

## Summary
Replace the static OLS-based hedge ratio calculation with a recursive **Kalman Filter**. This allows the bot to estimate the "true" relationship between two assets in real-time, adapting to beta drift and reducing signal noise. The filter state (state vector and covariance matrix) will be persisted in SQLite to ensure continuity across bot restarts.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: `numpy`, `statsmodels` (for initial state seeding)
**Storage**: SQLite (`kalman_state` table for persistence)
**Testing**: `pytest` (validation of convergence and Z-score smoothing)
**Target Platform**: Linux / Docker
**Project Type**: Statistical Math Engine Update
**Performance Goals**: State update < 5ms; Zero memory leak across recursive iterations.
**Constraints**: Must maintain constitutional "Racionalidade Mecânica" (Principle II).

## Constitution Check

- **I. Preservação de Capital**: ✅ Aumenta a segurança ao reduzir sinais falsos de "beta drift".
- **II. Racionalidade Mecânica**: ✅ Substitui médias móveis arbitrárias por um modelo de estado-espaço estatisticamente superior.
- **III. Auditabilidade Total**: ✅ O estado do filtro (Q, R, P matrices) será logado no Thought Journal.
- **IV. Operação Estrita**: ✅ Respeita os horários de mercado; o filtro "congela" quando o mercado fecha.
- **V. Virtual-Pie First**: ✅ Melhora a precisão do rebalanceamento ao fornecer um hedge ratio mais exato.

## Project Structure

### Documentation
```text
specs/007-kalman-filter-integration/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Kalman equations and state-space logic
├── data-model.md        # Schema for filter state persistence
└── tasks.md             # Implementation tasks
```

### Source Code Changes
```text
src/
├── services/
│   ├── kalman_service.py    # NEW: Recursive Kalman Filter logic
│   └── arbitrage_service.py # UPDATED: Use Kalman instead of OLS
├── models/
│   └── persistence.py       # UPDATED: CRUD for kalman_state
└── monitor.py              # UPDATED: Initialize and update filter state
```

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| State Persistence | Restart continuity | Without persistence, the filter takes ~20 iterations to converge every restart, losing signals. |
