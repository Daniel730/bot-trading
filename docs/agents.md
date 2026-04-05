# Agent Hierarchy

## PortfolioManagerAgent (Orchestrator)
Acts as the user-facing Robo-Advisor.
- **Responsibilities**: Goal tracking, horizon management, trade orchestration.
- **Logic**: Kelly Criterion sizing, Sharpe-based portfolio optimization.

## MacroEconomicAgent (Environment Monitor)
Provides global market context.
- **Responsibilities**: Monitoring interest rates (^TNX) and inflation data.
- **Logic**: RISK_ON / RISK_OFF state detection for allocation guidance.

## ReflectionAgent (Learning Loop)
Handles post-trade evaluation and self-correction.
- **Responsibilities**: Vectorized trade post-mortems, agent weight updates.
- **Logic**: 30-day performance review, dynamic confidence adjustment.
