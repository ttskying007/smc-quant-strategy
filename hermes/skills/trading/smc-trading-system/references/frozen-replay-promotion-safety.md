# Frozen Replay Promotion Safety

## Trigger
Use before promoting any research replay to automated simulated production, and whenever a user clicks manual backtest/reselect after promotion.

## Required sequence
1. Run the exact frozen replay script from the current source seed/K-line inputs.
2. Run the independent metric audit against that fresh replay output.
3. Compare fresh metrics and gates with the previously recorded release snapshot.
4. Promote only if the fresh replay and independent audit both pass every declared gate.
5. Only then enable scanner → pending-next-open → BUY_VALID automation.

## Fail-closed rule
A rerun that changes the gate outcome is evidence that the prior release snapshot is not reproducible. Immediately:

- set registry state to a fail-closed state;
- set `production_strategy=null`, `buy_enabled=false`, and active BUY count to zero;
- disable entry/monitor cron jobs;
- quarantine legacy positions rather than mixing them with the new lineage;
- show the fresh replay result in the frontend/API;
- never fall back to V88/V175/V185 or another historical engine.

## Manual backtest route
The manual reselect/backtest endpoint must be strategy-aware. It must either:

- execute the currently promoted strategy’s canonical replay and return its current gate result; or
- return an explicit fail-closed result with the fresh replay decision.

It must never infer a runner from static `ACTIVE_VERSION`, because UI defaults can point to legacy artifacts while the production registry has a different lineage.

## Verification checklist
- Canonical replay and independent audit exit successfully.
- Fresh metrics match gate requirements, including every annual slice.
- T+1 violations are zero.
- `/api/reselect` never launches a legacy engine when registry state is not live.
- Dashboard, monitor, live API, and cron all show the same registry strategy/state.
- Automated entry cron is absent/disabled while the registry is fail-closed.
