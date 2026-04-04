# Data Model: Correlation Cluster Tracking

**Feature**: 008-correlation-cluster-guard  
**Date**: 2026-03-31

## Configuration Extensions (`config.py`)

| Field | Type | Description |
|-------|------|-------------|
| `MAX_SECTOR_EXPOSURE` | `float` | Max % of portfolio allowed in a single sector (default 0.30). |
| `PAIR_SECTORS` | `Dict[str, str]` | Maps pair IDs to sectors (e.g., 'JPM_BAC': 'Financials'). |

## Instrumented State (`RiskService`)

The `RiskService` will track active exposure per sector:

| Attribute | Type | Description |
|-----------|------|-------------|
| `active_exposure` | `Dict[str, float]` | Sum of allocated capital per sector. |
| `cluster_map` | `Dict[str, List[str]]` | Map of sector -> list of active pair IDs. |

## Persistence

- **`trade_records`**: Every trade will now be tagged with its `sector` for historical drawdown analysis and QuantStats reporting.

## Decisions

1. **Correlation vs Sector**: While true correlation matrices are mathematically elegant, simple Sector-based bucketing is more "Mechanical" (Principle II) and easier for the AI Analyst to reason about. We will prioritize Sector Overlap first.
2. **Veto Logic**: If a sector is at 100% of its limit, the `monitor.py` will skip the Signal even before calling the LLM, saving tokens and time.
