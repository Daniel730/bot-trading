# Security policy

## Reporting

If you discover a vulnerability in Alpha Arbitrage (credential handling, auth bypass, order-path exposure, or similar), **do not** open a public issue with exploit details.

Prefer a private channel to the maintainer (`@Daniel730`) or a high-level public issue that omits secrets and reproduction that could move capital.

## Operational safety (agents and contributors)

- Never commit `.env`, API keys, tokens, TOTP seeds, or production passwords.
- Default to `PAPER_TRADING=true` and Java `DRY_RUN=true`.
- Live trading, risk-limit changes, production deploys, and safety-gate removals require explicit human approval.
- Do not bind Redis/Postgres/MCP/gRPC to non-loopback interfaces without a deliberate, reviewed design.

See `.github/copilot-instructions.md` and `docs/OPERATIONS.md`.
