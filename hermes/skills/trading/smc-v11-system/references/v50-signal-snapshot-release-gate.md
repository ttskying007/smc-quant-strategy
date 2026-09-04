# V50 Signal Snapshot + Release Gate Lessons

This reference captures the durable workflow lesson from the V50 SMC repair pass: do not promote a version because raw WR looks good; first force same-source signal provenance, qualified-R accounting, 90D closed-loop review, and frontend smoke checks through a release gate.

## Trigger

Use this when SMC signal accuracy, Pine/LuxAlgo alignment, backtest trade correctness, Kline marker sync, picks/watchlist sync, or "is everything complete?" release-readiness is in scope.

## Core lesson

The important pattern is not the exact V50 numbers. The durable fix is the **gated pipeline**:

```text
full kline cache
→ unified signal snapshot
→ setup builder / trade engine
→ trade provenance audit
→ signal sequence audit
→ quality metrics with qualified wins
→ 90D closed-loop review
→ sample-bias / pick-funnel audit
→ frontend smoke test
→ release gate
```

A version is not production-ready until the release gate passes. If the gate fails, report the failed checks and continue fixing; do not claim completion.

## Required artifacts

Prefer a versioned artifact set like:

```text
/root/.hermes/smc_opt_vXX_signal/vXX_signal_snapshot.json
/root/.hermes/smc_opt_vXX_signal/vXX_signal_report.json
/root/.hermes/smc_opt_vXX_signal/vXX_pine_param_matrix.json
/root/.hermes/smc_opt_vXX/vXX_trades.json
/root/.hermes/smc_opt_vXX/vXX_picks.json
/root/.hermes/smc_opt_vXX/vXX_report.json
/root/.hermes/smc_opt_vXX/vXX_setups.json
/root/.hermes/smc_opt_vXX/vXX_monitor_journal.json
/root/.hermes/smc_audit/vXX_trade_provenance_audit.json
/root/.hermes/smc_audit/vXX_signal_sequence_audit.json
/root/.hermes/smc_audit/vXX_quality_metrics.json
/root/.hermes/smc_audit/vXX_closed_loop_90d_review.json
/root/.hermes/smc_audit/vXX_sample_bias_audit.json
/root/.hermes/smc_audit/vXX_release_gate.json
/root/.hermes/smc_audit/vXX_release_gate.md
```

## Single-source signal snapshot

Do not let the Kline page, backtest, and audit each regenerate signals differently. Build one snapshot containing normalized signals with stable IDs:

```json
{
  "signal_id": "SYMBOL:FAMILY:INDEX:TYPE:VERSION",
  "symbol": "000001.SZ",
  "idx": 123,
  "date": "20260520",
  "family": "ob|fvg|sweep|structure|swing|ote|eql|bpr|lv",
  "type": "OB_Bull",
  "price": 12.34,
  "zone_high": 12.5,
  "zone_low": 12.1,
  "source": "pine_like|luxalgo_v34"
}
```

Then force all downstream systems to reference this snapshot, especially Kline markers and trade provenance.

## Provenance audit is mandatory

Every trade must map back to snapshot signals. Validate at least:

```text
source_event_idx <= zone_idx <= retrace_index <= conf_index <= entry_index <= exit_index
zone_id/conf_id/source_event_id present when relevant
bar_diff for mapped zone/conf/source/entry/exit is zero or explicitly justified
```

If provenance fails, the system is not signal-correct even if WR is high.

## Qualified win accounting

Raw wins are not enough. Add separate fields:

```text
raw_wr
qualified_wr
invalid_small_win_count
win_rr_below_2r
small_win_below_2
loss_inside_1pct
avg_realized_r
median_realized_r
```

A qualified win should satisfy:

```python
qualified_win = pnl_pct >= max(2.0, 2.0 * risk_pct)
```

Do not count sub-2R exits as proof of strategy quality.

## 90D closed-loop review

Review each trade from entry through 90 daily bars even after exit. Compute:

```text
mfe_trade_pct
mae_trade_pct
mfe90_pct
mae90_pct
post_exit_mfe90_pct
capture90_rate
issues
```

Classify issues, not just aggregate stats:

```text
SOLD_EARLY_NEXT_90D
SOLD_EARLY_BY_STRUCTURE_STOP
SOLD_EARLY_BY_TP2_STOP
SOLD_EARLY_BY_TRAILING
LOW_90D_MFE_CAPTURE
BAD_EXIT_LOST_BUT_90D_RECOVERED
WIN_RR_BELOW_2R
WIN_BELOW_2PCT_FEE_INEFFICIENT
LOSS_BELOW_1PCT_NOISE_EXIT
```

## Sample-bias / pick-funnel audit

High WR from a tiny funnel is suspect. Compare:

```text
snapshot_symbol_count
raw_signal_count
trade_count
pick_count
ACTIVE_ENTRY count
NEAR_ZONE_WATCH count
POST_ENTRY_MONITOR count
EXPIRED_REVIEW count
```

Flag at least:

```text
ACTIVE_ENTRY_TOO_NARROW
TRADE_SAMPLE_BELOW_100
```

## Frontend sync checks

Smoke-test all relevant pages/APIs before reporting completion:

```text
/
/backtest
/analysis
/autopsy
/monitor
/live
/kline?s=SYMBOL
/api/summary
/api/picks
/api/autopsy/closed-loop
/api/kline_full?symbol=SYMBOL&tf=daily&ver=VXX
```

Every endpoint must avoid tracebacks and the Kline API must show the requested version and non-empty signal layer when applicable.

## Release gate

A release gate should fail closed. Minimum checks:

```text
trade_file_exists
pick_file_exists
signal_snapshot_exists
provenance_fatal_count == 0
sequence_violations == 0
hold_over_90 == 0
small_win_below_2 == 0
loss_inside_1pct == 0
win_rr_below_2r == 0
avg_90d_capture >= threshold
sample_not_too_narrow
frontend endpoints OK
```

If `pass=false`, leave the previous production version active and state exactly which checks failed.

## Pitfall from V50 first pass

A structure-aware stop can still be too sensitive. If `SOLD_EARLY_BY_STRUCTURE_STOP` dominates, do not assume structure exit is solved. Require stronger invalidation such as:

```text
close below structure level
+ failed reclaim / next-bar confirmation
or reverse CHOCH/MSS
or repeated demand-zone invalidation
```

Also, if many trades have `BAR_DIFF_CONF_INDEX_*`, do not keep inheriting old confirmation indices; rebuild confirmation events from the unified snapshot.
