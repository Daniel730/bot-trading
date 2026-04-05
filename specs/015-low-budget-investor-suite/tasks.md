# Tasks: Elite Micro-Investor Bot

**Feature**: `015-low-budget-investor-suite` | **Date**: 2026-04-05
**Plan**: `/specs/015-low-budget-investor-suite/plan.md`

## Phase 1: Setup

- [X] T001 Configure Redis service and environment variables in `docker-compose.backend.yml`
- [X] T002 Update `requirements.txt` with `redis`, `websockets`, `openai`, `scipy`, and `matplotlib`
- [X] T003 [P] Initialize `InvestmentGoal`, `InvestmentHorizon`, and `CashSweep` tables in `scripts/init_db.py`

## Phase 2: Foundational (Shadowing & Guardrails)

- [X] T004 Implement `RedisService` in `src/services/redis_service.py` for low-latency LOB shadowing
- [X] T005 [P] Update `DataService` in `src/services/data_service.py` to stream Polygon WebSockets into Redis price cache
- [X] T006 Update `FeeAnalyzer` in `src/services/risk_service.py` to enforce the 2% friction-cost veto rule
- [X] T006b Implement Kelly Criterion fractional sizing logic (FR-010) in `src/services/risk_service.py`

## Phase 3: User Story 1 - Goal-Oriented Low-Budget DCA

- [X] T007 [US1] Add `InvestmentGoal` and `InvestmentHorizon` entities to `src/models/persistence.py`
- [X] T008 [US1] Create `DCAService` in `src/services/dca_service.py` with weekly scheduler and budget allocation logic
- [X] T009 [US1] Update `BrokerageService` in `src/services/brokerage_service.py` to execute value-based fractional orders
- [X] T010 [US1] Implement `CashManagementService` in `src/services/cash_management_service.py` for SGOV yield sweeps
- [X] T011 [US1] Implement `/invest` and `/cash` Telegram commands in `src/services/notification_service.py`
- [X] T011b [US1] Implement Dividend Tracking and Reinvestment (DRIP) (FR-004) in `src/services/brokerage_service.py`

## Phase 4: User Story 2 - Intelligent Rebalancing & Reflection

- [X] T012 [US2] Implement `PortfolioManagerAgent` in `src/agents/portfolio_manager_agent.py` with Covariance Matrix optimization
- [X] T013 [US2] Implement `ReflectionAgent` in `src/agents/reflection_agent.py` for vectorized trade post-mortems
- [X] T013b [US2] Implement SHAP/LIME explainability metrics (Constitution III) in `src/agents/reflection_agent.py`
- [X] T014 [US2] Create `AlternativeDataAgent` in `src/agents/alternative_data_agent.py` for Sentiment Anomaly detection

## Phase 5: User Story 3 - Temporal Goal Tracking & Horizon Management

- [X] T015 [US3] Implement `MacroEconomicAgent` in `src/agents/macro_economic_agent.py` for VIX/SKEW monitoring
- [X] T016 [US3] Implement Auto-Hedging Protocol (DEFCON 1) in `src/services/risk_service.py` using inverse ETFs
- [X] T017 [US3] Update `PortfolioManagerAgent` to shift weights based on the `InvestmentHorizon` state
- [X] T017b [US3] Implement In-Memory Synthetic Trailing Stop evaluation (FR-012) in `src/monitor.py`

## Phase 6: Polish & Federated Intelligence

- [X] T018 [P] Implement `VoiceService` in `src/services/voice_service.py` using OpenAI TTS-1 for trade summaries
- [X] T019 [P] Implement `VisualizationService` in `src/services/visualization_service.py` for Monte Carlo "What-If" charts
- [X] T020 Implement `TelemetryService` in `src/services/telemetry_service.py` for Federated Swarm Intelligence (anonymized sync)
- [X] T021 Update `TradeThesis` in `src/models/persistence.py` to store paths for voice notes and Monte Carlo visualizations
- [X] T021b Implement LLM-based structured Investment Thesis generation (FR-007) in `src/prompts.py`
- [X] T022 Final integration test: End-to-end DCA run with Telegram notification containing voice note and chart
