# Morning push orphaned `smc_daily_ops.py` recovery — 2026-06-24

## Trigger
A morning push wrapper can exit or time out while its child `smc_daily_ops.py` continues as an orphan under PID 1. Do not treat the parent timeout as a completed failure and do not launch a duplicate daily ops run while the child is alive.

## Recovery pattern

1. Check both parent and child processes:

```bash
ps -eo pid,ppid,etime,stat,%cpu,%mem,cmd \
  | grep -E 'smc_morning_push|smc_daily_ops|v98_reachable|v99_high|v100_structural|v101_mtf' \
  | grep -v grep || true
pstree -aps <daily_ops_pid> 2>/dev/null || true
```

2. If `smc_daily_ops.py` is alive, wait for it rather than rerunning. Its slow children may include:
   - `v98_reachable_5r_probability_gate.py`
   - `v99_high_wr_production_gate.py`
   - `v100_structural_net_gate.py`
   - `v101_mtf_dna_combo_contract.py`

3. After child exit, read `/root/.hermes/smc_monitor/ops_latest.json` and verify:
   - `generated_at` advanced to the current run time.
   - K-line refresh counts recovered or still failed honestly.
   - shadow selector `returncode == 0` and each stage has `timed_out == false`.

4. Run API smoke against the live frontend:
   - `/api/summary`
   - `/api/autopsy/closed-loop`
   - `/api/picks`
   - `/api/live-prices`
   - `/api/resonance`

5. Report live-guard status from `/api/live-prices`, not just `pick_contract.tradable_active_pick_count` from `/api/summary`. A summary can report active pick rows while live guard marks all rows `NON_TRADABLE_CONTEXT` or `NO_LIVE_LAST_PRICE`; the user needs the executable status, not just row counts.

## 2026-06-24 observed values

- Parent `smc_morning_push.py` exited around the outer timeout, but orphaned `smc_daily_ops.py` continued and finished at `2026-06-24T08:51:43`.
- K-line coverage recovered from the earlier `4154/4905` incomplete refresh to `4655/4905`, with latest date `20260623` on `4639` stocks.
- Remaining failures were mostly short-history Beijing-market rows: `rows=1` 247, `rows=42` 2, `rows=0` 1.
- Shadow selector completed successfully: V98 570.3s, V99 37.5s, V100 15.4s, V101 321.9s.
- `/api/live-prices` returned 26 rows, but live guard status was `23 NON_TRADABLE_CONTEXT` + `3 NO_LIVE_LAST_PRICE`; therefore no immediately buyable candidate despite active pick rows existing.

## Reporting format
Use a compact Chinese table report with:

- process recovery conclusion,
- K-line coverage and completeness gate status,
- shadow stage durations/return codes,
- frontend/API version and metrics,
- live guard status counts,
- full candidate table when the user expects all rows.
