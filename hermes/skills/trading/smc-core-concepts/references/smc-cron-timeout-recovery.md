# SMC cron / morning push timeout recovery

When the daily SMC cron or morning push fails with `subprocess.TimeoutExpired` while the underlying stages succeeded or are expected to run long:

1. Check live processes first, do not start duplicate daily scans:
   ```bash
   ps -eo pid,ppid,etime,stat,pcpu,pmem,cmd | grep -E 'smc_morning_push|smc_daily_ops|smc_closed_loop_ops|smc_unified.py' | grep -v grep || true
   ```
2. Inspect `/root/.hermes/smc_monitor/cron.log` and `/root/.hermes/smc_monitor/ops_latest.json`.
3. Normal daily ops can exceed 15 minutes because it runs:
   - `refresh_daily_750.py` (~2-3 min)
   - `v90_daily_full_market_scanner.py` (~4 min)
   - shadow gates V98/V99/V100/V101 (V98+V101 can exceed 12 min)
4. Outer wrappers must use a timeout larger than the total audited stages. Current safe value: `2400s`.
   - `/root/.hermes/scripts/v25/smc_closed_loop_ops.py::run_daily`
   - `/root/.hermes/scripts/v25/smc_morning_push.py::run_daily_preflight`
5. Handle `subprocess.TimeoutExpired` explicitly and write structured `returncode=124` / `timeout_sec` instead of crashing with a Python traceback.
6. When rebuilding a recovery report, `/api/picks` returns a list, not `{picks: [...]}`. Do not treat it as a dict or it will incorrectly report `0` picks.
7. If `/api/picks` has only `WATCH_ONLY` and `/api/live-prices.tradableLiveCount=0`, report that there is no current production tradable pick; do not promote stale V101/V100 historical candidates into live picks.

Verification:
```bash
python3 -m py_compile /root/.hermes/scripts/v25/smc_closed_loop_ops.py /root/.hermes/scripts/v25/smc_morning_push.py
python3 /root/.hermes/scripts/v25/smc_closed_loop_ops.py live --force
```
