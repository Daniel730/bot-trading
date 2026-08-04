# Agent Ensemble

The agent layer validates statistical signals before the monitor asks for approval or execution. It is intentionally async and fault-tolerant: individual agent failures should veto or degrade a signal, not stop the whole scan loop.

## Orchestrator

`src/agents/orchestrator.py`

Responsibilities:

- blocks new entries while `operational_status=DEGRADED_MODE`;
- performs macro beacon fail-fast checks;
- runs bull, bear, fundamental-cache, whale watcher, and news-risk reads concurrently;
- labels bull/bear telemetry as `HEURISTIC` when theme agents are non-LLM stubs (does not paint fixed/heuristic confidence as AI BULLISH/BEARISH);
- annotates `final_verdict` with a `THEME:` quality note (heuristic vs LLM);
- broadcasts intermediate thoughts to telemetry;
- applies fundamental hard vetoes (live fail-closed on unknown scores; paper keeps default score);
- records whale watcher as `INACTIVE` in the active runtime (legacy agent code remains; not a live veto today);
- applies news risk veto/shrink only when the agent marks `active=True` (opt-in; missing feed does not block entries);
- adjusts confidence with portfolio logic and global strategy accuracy;
- resets `DEGRADED_MODE` back to normal after successful agent loops.

The orchestrator is currently a direct async Python coordinator. It does not require LangGraph at runtime even though `langgraph` is present in dependencies.

## Bull Agent

`src/agents/bull_agent.py` (helpers in `src/agents/theme_agent_utils.py`)

Looks for upside/mean-reversion support in the signal context and returns a confidence/verdict payload used by the orchestrator.

**Runtime quality: heuristic stub by default (not LLM).** The old fixed `0.7` confidence was theater — it is replaced by a z-score-scaled heuristic labeled `source=heuristic_stub` / `quality=non_llm` / `llm_used=false`. Telemetry verdict is `HEURISTIC`, not AI `BULLISH`. Optional Gemini/OpenAI scoring is gated behind `BULL_BEAR_LLM_ENABLED` (default `false`) plus usable keys and process-local hourly/daily call caps (`BULL_BEAR_LLM_MAX_CALLS_PER_*`); exhausted budget or missing keys fall back to the heuristic without retry-spamming.

## Bear Agent

`src/agents/bear_agent.py` (same theme helpers)

Looks for downside, structural-break, and risk arguments against the signal. Its confidence is combined adversarially with the bull agent.

Same quality contract as bull: default heuristic (formerly fixed `0.4` theater), optional capped LLM only when explicitly enabled. Orchestrator final verdicts append `THEME: heuristic stub (not LLM)` when both sides are non-LLM so operators do not read MAB weights as model-scored AI quality.

## Macro Economic Agent

`src/agents/macro_economic_agent.py`

Provides ticker/sector regime labels such as:

- `BULLISH`
- `BEARISH`
- `EXTREME_VOLATILITY`

The orchestrator treats `EXTREME_VOLATILITY` on a beacon asset as a hard veto.

## Portfolio Manager Agent

`src/agents/portfolio_manager_agent.py`

Evaluates whether a signal improves the portfolio from an allocation/risk perspective. The orchestrator can boost or dampen confidence from this result.

## Whale Watcher Agent

`src/agents/whale_watcher_agent.py`

**Runtime status: inactive (hard-dormant stub).** The orchestrator emits `verdict: INACTIVE` and applies whale veto/multiplier only when a verdict explicitly sets `active=True`. Today the stub always returns `active=False` with identity multipliers, and `WHALE_WATCHER_ENABLED` is ignored until a restored evaluator ships (GitHub #91). Whale is not a Thompson/MAB arm (only bull/bear/SEC). The former cache-backed whale service under `legacy/` was removed.

When re-enabled, the intended behavior is a crypto/context risk filter that reads cached flow summaries and can veto conflicting flow, reduce confidence, or slightly support aligned flow. Re-enablement must: honor `WHALE_WATCHER_ENABLED`, set `active=True` only with fresh cache data, and add ingestion/veto/telemetry tests — do not flip the env flag alone.

## News Risk Agent

`src/agents/news_risk_agent.py` (feeds in `src/services/news_feed.py`)

**Role: veto-only risk overlay — not directional news trading / alpha prediction.**

- Opt-in via `NEWS_RISK_ENABLED` (default **false**).
- Maps headlines → tickers with a simple alias table (Coca-Cola→KO, Pepsi→PEP, …) plus exact ticker tokens.
- Scores materiality with keyword severity heuristics first. `NEWS_RISK_LLM_ENABLED` defaults false (same spirit as `BULL_BEAR_LLM_ENABLED`).
- Veto only when `active=True` and materiality ≥ `NEWS_RISK_VETO_SCORE`, the headline hits `ticker_a` or `ticker_b`, and it is inside `NEWS_RISK_TTL_SECONDS`.
- Mild materiality can shrink confidence via `NEWS_RISK_CONFIDENCE_MULTIPLIER` without a hard veto.
- Pluggable feeds: `rss` (default), `file`, `stub`, `polygon` (needs usable `POLYGON_API_KEY`).
- **Fail semantics:** missing API key / empty `NEWS_RISK_FEED_URLS` / empty feed → inactive **no-veto** (trading continues). Parse/network errors → inactive no-veto with a warning. Orchestrator applies news effects only when `active=True`.
- Not a Thompson/MAB arm.

Enable RSS path example:

```env
NEWS_RISK_ENABLED=true
NEWS_RISK_PROVIDER=rss
NEWS_RISK_FEED_URLS=https://finance.yahoo.com/rss/headline?s=KO,PEP
NEWS_RISK_TTL_SECONDS=7200
NEWS_RISK_VETO_SCORE=0.75
```

## Fundamental Analyst And SEC Worker

The hot path does not run slow SEC analysis directly. Instead:

- `src/daemons/sec_fundamental_worker.py` refreshes structural/fundamental scores in the background (equity tickers only, pre-market window).
- The orchestrator reads cached scores from Redis and treats missing, fallback, or stale entries (`ORCH_FUNDAMENTAL_MAX_AGE_SECONDS`) as unknown.
- Cache misses default to `ORCH_FUNDAMENTAL_DEFAULT_SCORE` and emit high-priority telemetry.
- Live mode (`PAPER_TRADING=false`) vetoes unknown fundamental state; paper mode keeps the default so SEC worker downtime does not block validation.
- Scores below `ORCH_FUNDAMENTAL_VETO_SCORE` veto the signal.
- When EDGAR is unreachable the worker circuit-breaks instead of caching neutral fallbacks or hammering every ticker.

## Reflection / Learning

`src/agents/reflection_agent.py`

Handles post-trade learning and confidence adjustment inputs. The orchestrator also reads `global_strategy_accuracy` from persistence to scale future confidence.

## Operational Notes

- Agent timeouts are bounded by `ORCHESTRATOR_TIMEOUT_SECONDS`.
- Agent failures are collected with `return_exceptions=True`.
- Telemetry thought events feed the dashboard's Agent Reasoning panel.
- Keep new agents side-effect-light; use services for I/O and persistence.
