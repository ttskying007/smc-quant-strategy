# V28 Auto-Audit Pipeline

Recurring cron-driven maintenance workflow for the V28 SMC baseline engine.

## Steps

1. **Full scan**: `cd /root/.hermes/scripts/v25 && python3 -u v28_full_scan.py > /tmp/v28_scan.log 2>&1`
   - Always use `python3 -u` (unbuffered) + file redirection for progress monitoring
   - Progress lines: `N/4905 (Ns) | trades=M` every 500 stocks
   - Full scan takes ~280s on 4905 stocks
   - Output: `/root/.hermes/smc_opt_v28/v28_{trades,picks,metrics,diagnostics}.json`

2. **Diagnostics**: `cd /root/.hermes/scripts/v25 && python3 smc_diagnostics_v28.py`
   - Reads `v28_trades.json` and produces `v28_diagnostics.json`
   - Reports WR, SL rate, worst cohorts, anomaly groups with severity

3. **Verify output files**:
   - `v28_trades.json` (~3.6 MB)
   - `v28_picks.json` (~1.3 MB)
   - `v28_metrics.json` (~0.8 KB)
   - `v28_diagnostics.json` (~21 KB)

4. **Apply fixes by severity** (only if thresholds breached):
   - **CRITICAL**: Must fix before proceeding
   - **HIGH**: Strongly recommended
   - Check diagnostics for specific cohort issues and apply targeted fixes in `smc_core_v28.py`

5. **Frontend cache refresh**: `curl -s http://localhost:8890/api/reload`

## Fix Mappings (Diagnostic → Code Change)

### Market State Filters (in `enhance_setups()`)
- `TREND_DOWN` WR < 60% → add `if ms in ('TREND_DOWN', 'TRANSITION'): continue`
- `TRANSITION` WR < 65% → same as above
- `RANGE` WR < 40% → hard-skip RANGE setups

### Resonance Filter (in `detect_build_backtest()`)
- `CONFLICT` resonance (weekly↔daily direction clash) → filter after resonance computation:
  ```python
  enhanced = [st for st in enhanced if st.get('resonance') != 'CONFLICT']
  ```

### Quality Thresholds (in `enhance_setups()`)
- `avg_quality < 6.0` → increase `MIN_QUALITY` to 6.5
- `BPR WR < 45%` → increase BPR quality threshold to 8.5

### SL Buffer
- Global SL rate > 35% → increase SL buffer in `adaptive_exit_plan()`

## Progress Monitoring Pattern

For long-running scans, use `python3 -u` (unbuffered stdout) and redirect to a log file:
```bash
python3 -u v28_full_scan.py > /tmp/v28_scan.log 2>&1
```
Check progress with: `tail -5 /tmp/v28_scan.log`

Do NOT pipe through `tail -30` in the command itself — bash pipe buffering will suppress output until process exit, making progress invisible.

## Frontend Reload

The unified frontend (`smc_unified.py` on port 8890) caches data in memory. After updating output files:
```bash
curl -s http://localhost:8890/api/reload
```
Returns `{"status": "reloaded", "trades": N, "picks": M}`.
