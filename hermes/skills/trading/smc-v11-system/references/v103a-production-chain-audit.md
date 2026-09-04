# V103A Production Chain Audit Lesson

Use this reference when an SMC production chain shows strong historical metrics but very few current picks, or when `/api/picks`, `/api/live-prices`, and `/api/summary` disagree.

## Trigger symptoms

- Full historical signal/trade pool is large, but production/current counts collapse sharply, e.g. `15k+ -> ~170 -> 2-3 -> 1`.
- `active_picks` rows contain realized fields such as `exit_reason`, `exit_date`, `pnl_pct`, `net_pnl_pct`, `mfe_r`, or `mae_r`.
- `/api/picks` shows a row whose `exit_reason` is already `TP2_MAIN_HIT`, `SL_HIT`, or `TIME_STOP`.
- `/api/live-prices` computes current PnL for a historical closed trade.
- `/api/summary` reports one version/engine while `/api/picks` uses another.
- Sequence audit shows `entry_idx < reclaim_idx`, `entry_idx == reclaim_idx`, `zone_date > entry_date`, or high `zone_before_event/zone_after_event` without explicit semantics.

## Diagnostic sequence

1. Freeze the baseline before editing:
   - current process and cwd for `smc_unified.py`
   - report JSONs for promoted versions
   - `active_picks`, `candidate_picks`, and historical trades files
   - `/api/picks`, `/api/live-prices`, `/api/summary` snapshots
2. Re-run the current generator chain once, if feasible, to separate stale artifacts from deterministic logic.
3. Count every compression layer:
   - all generated rows
   - production rows
   - active/current rows
   - frontend/API rows
4. Audit sequence fields for all rows and production rows separately:
   - `sweep_idx/event_idx/zone_idx/touch_idx/reclaim_idx/entry_idx/exit_idx`
   - `event_date/zone_date/pick_date/entry_date/exit_date`
5. Classify problems separately:
   - **Code future leak:** future highs/lows, future liquidity target, future-confirmed swing/OB, realized outcome fields used for gate decisions.
   - **Posterior/overfit gate:** whitelist or tier selected from historical winners/WR/RR after seeing outcomes.
   - **Frontend/current semantic bug:** historical closed trade is labeled active/current or live API uses closed row.
6. Before editing any function/class/method in this repo, run GitNexus impact analysis and report blast radius. Treat `smc_unified.py::_refresh_cache` as high-risk/critical and prefer minimal routing fixes.

## Hard validity contract

For a strict long setup, require:

```text
sweep_idx <= event_idx <= zone_idx <= touch_idx <= reclaim_idx < entry_idx < exit_idx
entry_date > pick_date
exit_date > entry_date
```

If `zone_idx < event_idx`, require an explicit prior-zone semantic such as `prior_ob_zone=true`; otherwise classify it as a sequence violation, not a valid event→POI→reclaim story.

## Data model repair pattern

Do not use one historical row for all surfaces. Split artifacts physically:

- `backtest_trades.json`: historical realized trades; may contain exits, PnL, MFE/MAE.
- `current_candidates.json`: latest full-market candidates; must not contain realized exit/PnL fields.
- `open_positions.json`: real monitor/ledger positions only; not derived from backtest exits.

Rules:

- Any row with `exit_reason in {TP2_MAIN_HIT, SL_HIT, TIME_STOP}` is not active/current.
- `/api/picks` must read current candidates/open positions, not historical trades.
- `/api/live-prices` must use the same rows as `/api/picks`; never compute live PnL for closed historical rows.
- `/api/summary` must report the same promoted version/source as picks/live.

## Known V103A audit pattern

A representative V103A audit found:

- Large full pool (`~15,270`) compressed to `~172` production and `2` active rows.
- Active rows were all historical `TP2_MAIN_HIT` rows.
- `/api/summary` returned V102 while `/api/picks` and `/api/live-prices` used V103A rows.
- `/api/live-prices` computed current loss on an already-closed TP2 row.
- Production sequence violations included many `entry_before_reclaim` rows and at least one `zone_date_after_entry_date` row.

Conclusion pattern: do not promote such a version even if aggregate WR is high. Label it a historical backtest/high-performance pool until current-candidate separation and sequence semantics pass.

## Monthly reporting requirement

When re-running a repaired version, output monthly rows, not only aggregate WR/RR:

| month | n | net_wr_ge_0_8 | sl_rate | avg_net | tp2 | sl | sequence_violations | t1_violations |
|---|---:|---:|---:|---:|---:|---:|---:|---:|

Flag weak months, tiny-sample high-WR months, concentration months, T+1 violations, and sequence violations explicitly.
