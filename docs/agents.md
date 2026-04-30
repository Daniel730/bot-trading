# Agent Ensemble

The agent layer validates statistical signals before the monitor asks for approval or execution. It is intentionally async and fault-tolerant: individual agent failures should veto or degrade a signal, not stop the whole scan loop.

## Orchestrator

`src/agents/orchestrator.py`

Responsibilities:

- blocks new entries while `operational_status=DEGRADED_MODE`;
- performs macro beacon fail-fast checks;
- runs bull, bear, fundamental-cache, and whale watcher reads concurrently;
- broadcasts intermediate thoughts to telemetry;
- applies fundamental hard vetoes;
- applies whale watcher veto or multiplier;
- adjusts confidence with portfolio logic and global strategy accuracy;
- resets `DEGRADED_MODE` back to normal after successful agent loops.

The orchestrator is currently a direct async Python coordinator. It does not require LangGraph at runtime even though `langgraph` is present in dependencies.

## Bull Agent

`src/agents/bull_agent.py`

Looks for upside/mean-reversion support in the signal context and returns a confidence/verdict payload used by the orchestrator.

## Bear Agent

`src/agents/bear_agent.py`

Looks for downside, structural-break, and risk arguments against the signal. Its confidence is combined adversarially with the bull agent.

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

Crypto/context risk filter that reads cached flow summaries and can:

- veto conflicting flow;
- reduce confidence;
- slightly support signals when flow aligns.

Config is controlled by `WHALE_WATCHER_*` settings.

## Fundamental Analyst And SEC Worker

The hot path does not run slow SEC analysis directly. Instead:

- `src/daemons/sec_fundamental_worker.py` refreshes structural/fundamental scores in the background.
- The orchestrator reads cached scores from Redis.
- Cache misses default to `ORCH_FUNDAMENTAL_DEFAULT_SCORE` and emit high-priority telemetry.
- Scores below `ORCH_FUNDAMENTAL_VETO_SCORE` veto the signal.

## Reflection / Learning

`src/agents/reflection_agent.py`

Handles post-trade learning and confidence adjustment inputs. The orchestrator also reads `global_strategy_accuracy` from persistence to scale future confidence.

## Operational Notes

- Agent timeouts are bounded by `ORCHESTRATOR_TIMEOUT_SECONDS`.
- Agent failures are collected with `return_exceptions=True`.
- Telemetry thought events feed the dashboard's Agent Reasoning panel.
- Keep new agents side-effect-light; use services for I/O and persistence.
