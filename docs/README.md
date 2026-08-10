# Alpha Arbitrage Bot — Documentation Index

> Documentation for **Alpha Arbitrage Bot**, an open-source statistical arbitrage and pairs-trading framework built in Python and Java. This index covers system architecture, operations, strategy, agent ensemble, budgets, and the React operations console.

**Related keywords:** statistical arbitrage docs, pairs trading framework, algorithmic trading bot documentation, Kalman filter spread strategy, Python trading bot, Java gRPC execution engine, Trading 212 integration, Alpaca integration, Web3 trading bot, paper trading guide, FastMCP tool server.

**Canonical (current) docs** — prefer these over audits/specs when they disagree:

| Document | Scope |
|---|---|
| `../README.md` | Repository overview and quick start |
| `../AGENTS.md` | Cursor Cloud / local VM runtime gotchas |
| `../GEMINI.md` | Assistant-oriented runtime notes (keep aligned with this index) |
| `../src/README.md` | Python backend, monitor, dashboard API, runtime state |
| `../frontend/README.md` | React operations console |
| `../execution-engine/README.md` | Java gRPC execution engine |
| `../infra/README.md` | Docker, compose, images, redeploy helper |
| `../.env.template` | Env surface (secrets stay blank; never commit `.env`) |
| `ARCHITECTURE.md` | Current system architecture |
| `OPERATIONS.md` | Local and Docker operating guide |
| `STRATEGY.md` | Strategy, signal, and risk logic |
| `DEVELOPER_BUDGET_GUIDE.md` | Venue budget implementation |
| `agents.md` | Agent ensemble and background analysis |
| `CLAUDE.md` | Assistant-oriented repo map and commands |
| `AGENT_WORKFLOW.md` | Required agent process: issues, PRs, Hermes, target stack |
| `tofix.md` | Current known backlog and open risks |
| `SUMMARY.md` | Readiness verdict snapshot (point-in-time; re-verify before acting) |
| `DECISIONS.md` | Architecture / safety decision log |
| `ROADMAP_DUAL_TRACK.md` | Platform maintenance vs quant research tracks |
| `../research/README.md` | Research track entry + acceptance protocol |

Default git branch is **`master`** (not `main`).

### Observability / quality (current vs target)

What exists **now**: internal `telemetry_service` (WebSocket broadcast + stub remote sync), dashboard `/ws/telemetry` and `/stream`, pytest/Vitest/JUnit, frontend ESLint, quality jobs inside `.github/workflows/deploy.yml`.

What is **not** live (tracked as targets in `AGENT_WORKFLOW.md` / issues #118–#135): OpenTelemetry SDK export, Sentry, Datadog, New Relic, Biome, Ruff, Codecov upload, Playwright, dedicated `ci.yml`, global skeletons / lazy panels.

## Historical / point-in-time (do not treat as current SoT)

Production audit series (2026-08-04 soak → Limited LIVE ops) — useful context; verify against code:

| Document | Scope |
|---|---|
| `FULL_DAY_AUDIT_2026-08-04.md` | Full-day soak findings |
| `AUDIT_PHASE2.md` | Phase 2 hardening |
| `AUDIT_PHASE3.md` | Phase 3 LIVE blockers (reservation, Telegram, 2FA) |
| `AUDIT_PHASE4.md` | Distributed reservation, exactly-once, broker SoT |
| `AUDIT_PHASE5_OPS.md` | Provenance, replay, divergence, rollback, kill criteria |
| `AUDIT_TECHNICAL_2026-08-04.md` | Technical deep-dive companion |

Other historical artifacts:

- `bugs.md` — older audit register; not the current backlog (`tofix.md` + GitHub issues).
- `MONDAY_READINESS_AUDIT.md` — paper-trading readiness state for 2026-04-20.
- `geminiplan.md` — original long-form design/research plan.
- `WIP_AUDIT_2026-07-17.md`, `OVERNIGHT_2026-08-04.md`, and ad-hoc `*-report.md` files — snapshots; prefer Phase docs + `SUMMARY.md` then re-check code.
- `specs/` and `.specify/` — feature-planning artifacts and templates, not always current runtime docs.
- `.brain/` — assistant working memory / ledgers; many items may already be fixed.
- The former `legacy/` tree (T212, Web3, whale cache service, old HTML dashboard) was removed; Alpaca is the only brokerage path.

## Support

If these docs help you, consider [sponsoring the project on GitHub](https://github.com/sponsors/Daniel730) — it funds infrastructure, new venue integrations, and maintenance.