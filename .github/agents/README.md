# GitHub custom agents (bot-trading)

Repository-level [Copilot custom agents](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/create-custom-agents) live here as `*.agent.md` profiles.

## Agents (minimal set)

| Agent | File | Use when |
|---|---|---|
| Trading Safety | `trading-safety.agent.md` | Strategy, risk, sizing, broker/mode, execution lanes |
| Code Reviewer | `code-reviewer.agent.md` | PR / diff review for bugs, regressions, architecture |
| Test Engineer | `test-engineer.agent.md` | Pytest / Vitest / Java tests, CI gaps, paper validation |
| Ops / SRE | `ops-sre.agent.md` | Compose, deploy, health, logs, incidents |

Do **not** add more agents unless a clear gap remains after using these four plus `AGENTS.md` / `docs/AGENT_WORKFLOW.md`.

## Not these agents

Runtime **signal** ensemble (bull/bear/orchestrator) is documented in [`docs/agents.md`](../../docs/agents.md) — that is production trading code, not Copilot profiles.

## Safety

All agents must keep `PAPER_TRADING=true` / Java `DRY_RUN=true` defaults unless a human explicitly requests broker-paper or live work. Dangerous changes require explicit human approval (see each agent profile and `.github/copilot-instructions.md`).
