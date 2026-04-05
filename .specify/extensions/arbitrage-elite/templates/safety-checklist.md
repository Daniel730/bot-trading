# Trade Safety & Compliance Checklist: [FEATURE_NAME]

**Feature**: [Link to spec.md] | **Created**: [DATE]

## Principle I: Preservation of Capital
- [ ] Trades > $100 require manual Telegram approval.
- [ ] Position sizing follows Kelly Fractional (max 0.25x).
- [ ] Stop-loss mechanism (time or %-based) is defined.
- [ ] Portfolio risk capped at 2% per trade and 10% total drawdown.

## Principle II: Mechanical Rationality
- [ ] Decision uses Z-score (structured data) from `statsmodels`.
- [ ] Fundamental analysis (Gemini) provides a reasoning log before execution.
- [ ] All math occurs in `src/services/` (isolated from LLM internal arithmetic).

## Principle III: Total Auditability
- [ ] Thought Journal records Bull/Bear debate for this feature.
- [ ] SHAP/LIME importance values are recorded for the decision.
- [ ] QuantStats daily report integration is active.

## Principle IV: Strict Operation
- [ ] NYSE/NASDAQ hours guard (14:30-21:00 WET) is implemented.
- [ ] US Holiday check is active via `holidays` lib.
- [ ] Order suppression outside hours is verified by a test case.

## Principle V: Virtual-Pie First
- [ ] Local SQLite state is synced with T212 on startup.
- [ ] Individual quantity-based orders are used instead of native Pie API.
- [ ] Slippage tolerance check (< 0.5%) is implemented.
