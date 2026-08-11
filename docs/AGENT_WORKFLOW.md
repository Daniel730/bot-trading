# Agent Workflow (required for every model)

This is the durable process for **any** coding agent (Cursor, Hermes, Codex, Claude, etc.) working in `bot-trading`. Prefer this over inventing ad-hoc flows.

## 1. Issues before substantial work

Create a GitHub issue **before** non-trivial implementation (more than a tiny typo/docs fix).

| Prefix | Use for | Label |
|---|---|---|
| `[Correção]` | Bugs, broken behavior, incorrect docs that mislead operators | `Correção` (+ `bug` if applicable) |
| `[Melhoria]` | Improve an existing path (CI, UX, hardening, refactors with clear win) | `Melhoria` |
| `[Nova função]` | New capability / integration | `Nova função` |

Issue bodies should include: **context**, **acceptance criteria** (checkboxes), and **related paths** when known.

```bash
gh issue create --title "[Melhoria] …" --label Melhoria --body "…"
```

Foundation backlog for observability / quality / tests / motion starts at issues **#118–#135**.

## 2. Feature branches + PRs (deploy management)

- Do **not** push feature work straight to `master` (default branch).
- Branch from an up-to-date `master`: `fix/<issue>-short-slug` or `feat/<issue>-short-slug`.
- Open a PR for review and for deploy gating (`.github/workflows/ci.yml` on PR/push; deploy quality + GHCR via `.github/workflows/deploy.yml`).
- Production images deploy from **GitHub Releases** / controlled workflow dispatch — not from random local pushes.

### Local commitlint (Windows / PowerShell)

Repo-root tooling (does **not** replace `frontend/` deps):

```powershell
npm install
# husky install via prepare; commit-msg runs commitlint
git commit -m "fix: describe the change"
```

CI remains the source of truth — local hooks are optional quality; remote merges are not blocked solely because a developer skipped husky.

## 3. Always link the issue in the PR

PR description **must** mention the issue:

- `Fixes #N` / `Closes #N` when the PR fully completes the issue
- `Refs #N` when partial

Use `.github/PULL_REQUEST_TEMPLATE.md`. Do not open “anonymous” PRs without an issue for substantial work.

## 4. Prefer Hermes (forge) for cheap survey/draft

Forge root: `C:\Users\Danie\Projects\daniel-hermes-forge`

```powershell
$Forge = "C:\Users\Danie\Projects\daniel-hermes-forge"
Set-Location $Forge
python scripts/hermes_delegate.py --tier simple "<survey / README summary>"
python scripts/hermes_delegate.py --tier medium "<issue draft / patch sketch>"
python scripts/hermes_delegate.py --model hermes-agent "<multi-step survey>"
```

- Read captures under `$Forge\data\delegations\` and **validate** before applying.
- If bot-server / Hermes is offline, say so and continue with Cursor — do **not** pretend Hermes ran.
- Parent Cursor keeps planning, tradeoffs, apply/commit/PR (commits only when Daniel asks).

Skill: `~/.cursor/skills/cursor-orchestrator/SKILL.md`.

## 5. Safety defaults

- Keep **`PAPER_TRADING=true`** (and Java **`DRY_RUN=true`**) unless explicitly validating broker paper/live paths.
- Never commit secrets (`.env`, tokens, API keys, TOTP seeds).
- Do not hardcode venue checks outside `BrokerageService.get_venue()`.
- Preserve `signal_id` through reasoning, journal, ledger, and close paths.
- Do not bypass dashboard session / 2FA for operator controls.

## 5b. GitHub Copilot custom agents

Minimal profiles in [`.github/agents/`](../.github/agents/README.md): **Trading Safety**, **Code Reviewer**, **Test Engineer**, **Ops / SRE**. Shared instructions: [`.github/copilot-instructions.md`](../.github/copilot-instructions.md).

Do not add agents that restate this workflow or Speckit skills. Prefer consolidating responsibilities. Runtime trading ensemble docs remain in [`docs/agents.md`](agents.md) (different domain).

## 6. Target platform standards (gaps → issues)

These are the **target** stack. Implement via linked issues; do not invent parallel tools without updating this table.

| Area | Target | Status (foundation audit) | Tracking |
|---|---|---|---|
| Tracing / metrics | OpenTelemetry (OTLP) | Opt-in Python SDK + OTLP/HTTP (`otel_service`); dashboard WS telemetry is real (#122) | #118, #122 |
| Errors | Sentry | Opt-in Python + React SDKs; fail-closed when DSN empty | #119 |
| APM / ops | Datadog | **Not planned** — use OTel + Sentry (see #120 close rationale) | #120 |
| APM (optional) | New Relic | **Not planned** — duplicate APM vs OTel + Sentry | #121 |
| Frontend lint | Biome (+ current ESLint until migrated) | ESLint CI gate + Biome warn-first (`frontend/biome.json`) | #123 |
| Python lint | Ruff via `pyproject.toml` | Baseline E9/F821/F822 in `ci.yml` + `deploy.yml` quality_python | #128 |
| Commit messages | commitlint + husky (local) | Root `package.json` + `.husky/commit-msg` (CI remains source of truth) | #124 |
| Dead code | Knip (frontend) | Warn-first `npm run knip` + `frontend/knip.json` (cleanup PR later) | #125 |
| Mutation testing | Stryker (frontend) | Scaffolded (`stryker.config.json` + optional workflow_dispatch) | #126 |
| Architecture tests | ArchUnit (Java) + Python arch-contract | Python `tests/unit/test_arch_contracts.py` + Java ArchUnit smoke | #127 || Coverage | Codecov | `codecov.yml` + fail-soft uploads in `ci.yml`/`deploy.yml` | #129 |
| E2E | Playwright | Missing (Vitest unit/component only) | #130 |
| CI on PR | Dedicated `ci.yml` | `.github/workflows/ci.yml` on PR/push | #131 |
| UI loading | Global skeletons | Text/spinner only | #132 |
| Code split | `React.lazy` + `Suspense` | Missing | #133 |
| Motion | framer-motion + [design-motion-principles](https://github.com/kylezantos/design-motion-principles) | Partial (`PairsPanel`, `IntelligenceHub`) | #134 |

### What already exists

- **Tests:** pytest unit (~132) + integration (~20); Java JUnit/Testcontainers; frontend Vitest (~16 tests); CI quality jobs in `deploy.yml`.
- **Lint:** ESLint 9 on frontend (`npm run lint`).
- **Telemetry (internal):** `src/services/telemetry_service.py` + dashboard `/ws/telemetry` (not vendor APM).
- **Motion:** `framer-motion` dependency; limited `AnimatePresence` usage; startup progress UI in `App.tsx`.

### UI motion rules (summary)

For dashboard work, treat the console as a **SaaS dashboard**: Emil Kowalski primary, Jakub Krehel secondary ([design-motion-principles](https://github.com/kylezantos/design-motion-principles)).

- Skeletons that match final layout; shimmer optional; respect `prefers-reduced-motion`.
- Lazy-load heavy panels; Suspense fallbacks = skeletons.
- Enter/exit for panels/modals (~180–300ms); **do not** animate high-frequency telemetry ticks.
- Progress for long startup/refresh; avoid AI-slop (hover-scale-everywhere, stagger spam).

## 7. Suggested implementation order

1. Process scaffolding (PR/issue templates) — #135  
2. Dedicated PR CI — #131  
3. Ruff + Codecov — #128, #129  
4. OpenTelemetry foundation — #118 (+ #122 stub cleanup)  
5. Sentry — #119  
6. UI skeletons → lazy → motion polish — #132, #133, #134  
7. Playwright e2e — #130  
8. Biome / commitlint / Knip / Stryker / Arch — #123–#127  
9. Datadog / New Relic only after OTel decision — #120, #121  

## Related docs

- `AGENTS.md` — Cursor Cloud / runtime gotchas  
- `docs/CLAUDE.md` — assistant repo map  
- `README.md` — quick start  
- `docs/OPERATIONS.md` — runbook  
