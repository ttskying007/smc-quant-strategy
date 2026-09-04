# Dashboard service ownership and daily-epoch semantics

Use when maintaining the SMC dashboard on port 8890 or diagnosing a report that the UI has stopped synchronizing.

## Design rule

- A process manager (systemd) owns the dashboard process exclusively.
- Any cron task is a **health audit only**. It must never kill the port or launch a competing `nohup` process.
- The dashboard process should run with `SMC_INTERNAL_SCHEDULER=0` when post-close work is owned by a dedicated system cron job; do not create duplicate scanners/refreshes.

## Linux service contract

A minimal service has:

- `WorkingDirectory=/root/.hermes/scripts`
- `ExecStart=/usr/bin/python3 /root/.hermes/scripts/smc_unified.py`
- `Environment=SMC_INTERNAL_SCHEDULER=0`
- `Restart=always`, short `RestartSec`
- enabled at boot.

Verification must confirm all four facts:

1. service is `enabled` and `active`;
2. port 8890 has exactly the systemd-owned Python listener;
3. a real dashboard page loads after process handoff;
4. page-visible epoch agrees with `kline_epoch_current.json` and the current V521 scanner artifact.

## Time semantics: avoid a false "morning sync" diagnosis

Daily-K refresh/scanner contracts run **post-close** (currently the authoritative V523 observer is scheduled at 18:10 on trading weekdays). During market hours, the dashboard should show the last committed daily epoch. Do not materialize a current-session daily signal from an unfinished bar to make the UI look fresh: that violates closed-bar and PIT discipline.

When the UI is operational but shows yesterday's committed epoch before the daily post-close job, explain this distinction explicitly. A service outage and a correct post-close-only data contract are separate diagnoses.

## Fail-closed preservation

A repaired dashboard must not turn research or historical artifacts into selections. Verify the production registry after any service work: `buy_enabled=false`, `EMPTY_BOOK`, and the existing release gate must remain unchanged unless a separately qualified production contract changes them.
