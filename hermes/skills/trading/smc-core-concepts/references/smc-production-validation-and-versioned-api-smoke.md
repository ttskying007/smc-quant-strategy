# SMC production validation and versioned API smoke

Use this when asked to verify that recent SMC改造/生产化/重物化 actually executed and did not silently break frontend/API/watchlist contracts.

## Required validation sequence

1. **Compile before running**
   - Run `python3 -m py_compile` on every touched or directly involved script before replaying research/production scripts.
   - Include materializers, research probes, rematerialize scripts, and temporary deterministic probes if they are part of the claimed workflow.

2. **Replay deterministic scripts, not just inspect files**
   - Re-run research-only scripts to confirm they still complete and write audit-only artifacts.
   - Re-run the production rematerializer if the task is to validate production artifacts.
   - Record the new artifact paths and decisions.

3. **Validate artifact metrics directly**
   - Read the actual `*_trades.json`, `*_active_picks.json`, and `*_report.json`.
   - Check: `n`, WR, AvgPnL, min-year count, all-year WR min, micro-profit %, T+1 same-day exits, active-pick count, and active outcome pollution.
   - Active picks must have no historical fields populated: `exit_date`, realized `exit_reason`, `hold_bars`, `mae/mfe`, `rr_realized`, nonzero realized `pnl_pct`, or `won=True` unless the live monitor intentionally sets a live state.

4. **Smoke actual frontend/API endpoints**
   - Hit at minimum: `/`, `/monitor`, `/live`, `/docs`, `/api/summary`, `/api/picks`, `/api/live-prices`, `/api/picks/contract`.
   - Require HTTP 200 and non-empty payloads.
   - For `/api/picks` and `/api/live-prices`, count old labels and completed-trade pollution.
   - In休市状态, live rows may have live monitor states such as `NON_TRADABLE_CONTEXT` / `WATCH_ONLY`; this is not historical-trade pollution unless `exit_date` or realized trade outcome fields are present.

## Versioned API pitfall

Do not assume query parameters are honored. In `smc_unified.py`, versioned historical requests may use `ver` rather than `version`, and missing version-specific branches can silently fall back to the active production version. Validation must explicitly compare:

- `/api/picks`
- `/api/picks?ver=<version>`
- `/api/picks?version=<version>`
- `/api/live-prices`

If a requested historical version returns the active engine’s rows, classify it as a **versioned-query compatibility bug**, not necessarily production pollution.

## Editing guard

`smc_unified.py` routing helpers such as `get_version_picks()` and `get_version_trades()` sit on critical frontend/API paths. Before modifying them, run GitNexus impact analysis and report the blast radius. If impact is HIGH/CRITICAL, do not casually patch during a validation pass; first separate:

- current production correctness,
- historical/versioned API compatibility,
- frontend/live route behavior,
- whether a restart is required after patching.

## Reporting format

For Lei, report as compact tables:

- current production status,
- simulated scripts and decisions,
- endpoint smoke status,
- pollution/T+1 checks,
- discovered issues with scope and whether they block production.

Avoid long narrative. State clearly whether the issue is production-blocking or only historical/versioned compatibility.