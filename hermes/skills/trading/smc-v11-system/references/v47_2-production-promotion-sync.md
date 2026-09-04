# V47.2 Production Promotion / Frontend Full-Surface Sync

Session lesson: when an SMC candidate version graduates from “parallel validation” to production, do not only change the default dropdown label. Promote it through the whole runtime contract and prove every surface reads the same active version.

## Required promotion checklist

1. **Default constants**
   - `ACTIVE_VERSION`
   - `ACTIVE_TRADE_FILE`
   - `ACTIVE_PICK_FILE`
   - `_active_version_paths(version)` mapping
   - any `reload_metrics()` / summary loader that still hardcodes legacy V31/V44/V46 paths.

2. **API surfaces**
   - `/api/summary` must return `version` and `active_default` equal to the promoted version.
   - `/api/picks` must read the promoted watchlist/picks file.
   - `/api/picks/contract` must show active pick counts from the promoted version.
   - `/api/kline_full` default `ver` must use `ACTIVE_VERSION`, not stale UI state.
   - `/api/backtest/run` and `/api/reselect` must invoke the promoted engine script.

3. **HTML pages**
   - `/` dashboard title and metrics.
   - `/monitor` heading and table engine column.
   - `/backtest` title, metrics and data source.
   - `/kline` version dropdown selected option.
   - `/live`, `/analysis`, `/autopsy`, `/resonance` must not silently use old trade/pick files.
   - `/docs` must be dynamic from active paths/metrics, not stale prose.

4. **Cache invalidation**
   - After reselect/backtest rerun, clear `_TRADES_CACHE`, `_TRADES_LITE_CACHE`, `_PICKS_CACHE`, `_SUMMARY_CACHE`, plus mtime maps if present.
   - Otherwise frontend can show new labels with old data.

5. **Validation script expectations**
   - Re-run the engine directly: `python3 /root/.hermes/scripts/v25/<version_engine>.py`.
   - Generate a production validation JSON under the version output directory.
   - Check:
     - no missing required trade fields;
     - `entry_index`/`exit_index` in K-line range and ordered;
     - report metrics equal recalculated metrics from trade rows;
     - pick contract uses active candidates, not historical best trades;
     - API and pages all identify the promoted version.

## Concrete V47.2 production contract

After promotion, the intended contract was:

```text
ACTIVE_VERSION = V47_2
ACTIVE_TRADE_FILE = /root/.hermes/smc_opt_v47_2_candidate/v47_2_trades.json
ACTIVE_PICK_FILE = /root/.hermes/smc_opt_v47_2_candidate/v47_2_picks.json
Engine = /root/.hermes/scripts/v25/v47_2_high_quality.py
OutputDir = /root/.hermes/smc_opt_v47_2_candidate
```

Expected verification shape:

```json
{
  "summary_active_v472": true,
  "picks_count_11": true,
  "kline_default_v472": true,
  "backtest_v472": true,
  "monitor_v472": true,
  "docs_v472": true,
  "dashboard_v472": true
}
```

## Pitfalls

- “Candidate appears in dropdown” is not production promotion.
- “API ver parameter works” is not enough; default pages must use the promoted version without manually passing `ver`.
- Docs are part of the deliverable. If `/docs` still says candidate/parallel, the promotion is incomplete.
- Browser validation matters: inspect `/monitor`, `/kline?s=<active symbol>`, and `/docs` after restart, not just JSON files.
