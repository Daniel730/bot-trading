## Summary

- Issue link (required): `Fixes #N` / `Closes #N` when this PR completes the issue, or `Refs #N` when partial
- Type: Correção / Melhoria / Nova função

## Changes

-

## Safety

- [ ] `PAPER_TRADING` defaults preserved (or broker-paper/live change is intentional and documented)
- [ ] No secrets / `.env` / tokens committed
- [ ] Venue checks remain behind `BrokerageService.get_venue()` when touching brokerage
- [ ] `signal_id` preserved on open/close/ledger paths when touching execution

## Test plan

- [ ] Relevant pytest / Vitest / Java tests run locally
- [ ] CI quality jobs green
- [ ] Manual check (if UI): skeleton/loading and `prefers-reduced-motion` considered
