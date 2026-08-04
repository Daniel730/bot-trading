# Audit Phase 5 — Operational Trust (post-platform)

**Date:** 2026-08-04  
**Context:** After Phases 1–4 the platform has financial-system properties (exactly-once, broker SoT, distributed locks, fail-closed LIVE gate). The remaining risk is largely **operational and statistical**, not implementation bugs.

## Distinction

| Stage | Meaning |
|---|---|
| **Pronto para colocar dinheiro** | Platform will not silently double-order, invent broker state, or bypass halt/checklist. |
| **Pronto para confiar dinheiro** | Strategy edge is proven OOS across regimes; ops can reconstruct, rollback, and stop on objective kills. |

Phase-4 verdict (**READY FOR LIMITED LIVE CAPITAL**) addresses the first stage. Phase-5 starts the second without pretending unit tests prove alpha.

---

## Operational conditions before scaling capital

1. **48h soak** — `scripts/phase4_soak_chaos.py --signals 100000 --hours 48` with zero invariant violations.
2. **Small capital** — loss must be personally acceptable.
3. **Objective stop criteria** (enforced in code via `limited_live_kill`):
   - consecutive broker reconcile failures ≥ 3
   - shadow/LIVE divergences ≥ 10 (session)
   - capital / equity drawdown halt (Phase-4 R-303)
4. **Continuous monitoring** + **rollback &lt; 30s operator path** (`scripts/rollback_deploy.sh`).
5. Only then: gradual exposure increase.

---

## What shipped (foundations)

### 1. Observability / reconstruction
- `scripts/replay_trade.py --trade-id|--signal-id|--order-id`
- Joins ledger legs, agent reasoning, trade journal, execution intents, incident packs
- Compares trade provenance vs runtime commit/config hash

### 2. Strategy versioning on every trade
Provenance stamped into ledger metadata via `stamp_trade_metadata`:

- `strategy_version`, `risk_version`, `feature_version`, `model_version`
- `git_commit`, `config_hash`, `feature_hash`

### 3. Shadow vs LIVE divergence skeleton
- `shadow_live_divergence` monitor — decision/confidence divergence → WARNING
- LIVE path records decisions; parallel shadow recorder can feed the other side
- Divergences feed limited-LIVE kill criteria

### 4. One-command rollback
- `scripts/rollback_deploy.sh [sha]` — pull+recreate previous image tag, **never** `down -v`
- Follow with `scripts/post_deploy_smoke.sh`

### 5. Limited-LIVE kill switch
- `evaluate_limited_live_kill` checked in `execute_trade` for real-money LIVE
- Reconcile failure counter updated by continuous reconciler

---

## Still operator / research work (not closed by this phase)

| Item | Why it matters |
|---|---|
| Multi-regime OOS performance | Platform ≠ edge |
| Parameter sensitivity | Overfit detection |
| Real slippage/spread/fees in sims | Live PnL vs backtest gap |
| Permanent dual shadow executor process | Full LIVE vs shadow parity (skeleton only today) |
| Deterministic full indicator replay | Ring buffer is process-local; packs must be exported |

---

## Scores (ops trust layer)

| Dimension | Score | Notes |
|---|---|---|
| Observability | **7.8** | Replay CLI + provenance; full AI trail still needs pack export discipline |
| Operability | **8.0** | Rollback script + kill criteria |
| Strategy evidence | **n/a / research** | Not a code score |

Platform Phase-4 scores unchanged. **Do not confuse platform maturity with statistical edge.**

---

## Verdict affirmation

**READY FOR LIMITED LIVE CAPITAL** — with Phase-5 operational conditions above.

Not ready to *trust* large capital until soak + OOS strategy evidence + dual shadow maturity.

---

## Files

- `src/services/trade_provenance.py`
- `src/services/trade_reconstruction.py`
- `src/services/shadow_live_divergence.py`
- `src/services/limited_live_kill.py`
- `scripts/replay_trade.py`
- `scripts/rollback_deploy.sh`
- `tests/unit/test_audit_phase5_ops.py`
- `docs/AUDIT_PHASE5_OPS.md`
