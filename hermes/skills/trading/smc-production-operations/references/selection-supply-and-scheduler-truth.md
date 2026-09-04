# Selection-supply and scheduler-truth audit

Use when a trading UI has shown no executable selections for many sessions, especially after a strategy gate revocation. The key mistake is treating `picks=[]` as one diagnosis.

## Four separate states

| State | Evidence | Correct interpretation |
|---|---|---|
| Stale/invalid legacy selection | selector emits rows after failed or fragmented refresh; later chronology audit rejects the lineage | Not current supply; quarantine it. Never use it as a fallback. |
| Healthy scan, no current setup | committed epoch passes; current raw scanner returns zero rows; strategy is licensed | A legal no-signal session. |
| Healthy scan, admission blocked | committed epoch passes; raw scanner may be zero or nonzero; release/registry says blocked | Policy/economic closure prevents production picks. Do not mislabel it as a scanner outage. |
| Scheduler/control-plane drift | displayed scheduler state names a retired job, while actual cron/service runs a different command—or no command | Repair observability and scheduler ownership before interpreting no-pick duration. |

## Required evidence chain

1. Read registry and committed epoch; record strategy, buy permission, current data date, and current count.
2. Inspect current scanner output **before** the release gate: record raw/current candidate count, pending count, and gate blocker separately.
3. Enumerate scheduler owners: `crontab -l`, `/etc/cron.d/*`, Hermes cron job state, in-process scheduler environment flags, and live process command lines. Job labels and a dashboard state JSON are not evidence.
4. Parse actual observer logs by market date. For each run record refresh outcome, committed epoch ID, raw/pending count, release state, controller return code, and any failure state.
5. Directly verify `/api/summary`, `/api/picks`, and `/api/live-prices`. A correct empty state must show zero current picks with no legacy fallback.
6. If a completed background controller is sleeping forever while holding a lock, verify terminal state and audit first, then stop it and confirm the lock is released. This is source-cache hygiene only; do not portray it as a strategy repair.

## Selection-supply SLO

A fail-closed empty book is legitimate; an unexplained extended empty book is not acceptable operationally. Maintain an explicit daily report that distinguishes:

- `NO_CURRENT_SETUP`: current scanner zero while a strategy is licensed;
- `CURRENT_SETUP_BLOCKED`: raw/current scanner found rows but release gate prevents admission;
- `NO_LICENSED_STRATEGY`: no strategy may create pending or BUY rows;
- `REFRESH_NOT_COMMITTED`: data plane failed closed;
- `SCHEDULER_NOT_EXECUTING`: expected observer did not run.

After a configurable consecutive-session threshold, escalate the state to a root-cause review. Escalation must not lower gates, revive historical picks, or reopen a closed ontology. Its purpose is to prevent silent user-facing starvation and force an explicit decision: new source qualification, an independently preregistered ontology, or continued empty-book operation.

## Pitfalls

- Do not say “the scanner ran” based only on a cron exit code: verify its market-date-specific artifact and candidate counts.
- Do not say “there were no signals” when the release gate stopped a nonempty scan; report `CURRENT_SETUP_BLOCKED` instead.
- Do not say “scheduler stopped” solely because an old state file is stale; identify the actual scheduler owner and its logs.
- Do not repair selection supply by re-enabling a rejected historical engine, lowering the frozen replay gate, or relabelling shadow rows as BUYs.
