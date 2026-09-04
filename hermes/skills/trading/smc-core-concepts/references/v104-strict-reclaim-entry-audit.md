# V104 Strict Reclaim-Confirmed Entry Audit Pattern

Use this reference when rebuilding or auditing an SMC strategy that claims `touch -> reclaim -> entry` semantics.

## Core lesson

A strategy can show good headline WR/RR while still being semantically wrong if the executable entry happens before reclaim confirmation. Always audit the actual bar order:

`source_event_idx -> zone_idx -> touch_idx -> reclaim_idx -> entry_idx -> exit_idx`

The hard gate for reclaim-confirmed entry is:

- `touch_idx <= reclaim_idx < entry_idx`
- `entry_idx > reclaim_idx`
- `entry_price > zone_high` for a `ZONE_HIGH_RECLAIM -> NEXT_OPEN_ENTRY` contract
- `exit_idx > entry_idx`
- `entry_date != exit_date` for A-share T+1 compliance

If next open gaps back below the reclaimed zone high, the reclaim is not executable as a confirmed reclaim entry; skip it and wait for a fresh reclaim.

## V104 rebuild workflow

1. Rebuild from raw K-line cache, not V100/V102/V103A historical completed trades.
2. Detect confirmed swing points once per symbol and reuse them; repeatedly recomputing `swings_until()` inside every BOS loop can time out on full-market 4655-symbol runs.
3. Materialize reversal and continuation rows separately:
   - `REVERSAL_SSL_CHOCH_FVG_RECLAIM`
   - `CONTINUATION_BOS_FVG_RETEST_RECLAIM`
4. Simulate exits with strict T+1: first exit check starts at `entry_idx + 1`.
5. Emit full artifacts before any promotion decision:
   - `v104_trades.json`
   - `v104_picks.json`
   - `v104_report.json`
   - closure audit JSON/MD under `smc_audit/`
6. Run semantic, interval, monthly stability, family split, entry-position, risk-bin, and SL/TP audits.

## Gates to report

Minimum table fields for Lei:

| Gate | Required proof |
|---|---|
| Semantic order | `entry_before_reclaim == 0`, `semantic_fail == 0` |
| T+1 | `same_day_exit == 0`, `exit_idx > entry_idx` |
| Full-market | scanned symbol count, start date, total trades |
| Performance | net WR >= 0.8%, SL rate, avg net PnL |
| Stability | stable months / total months |
| Promotion | explicit `release_gate.pass` and decision |

## Interpretation rule

If semantic gates pass but WR/monthly stability fail, report: **semantic repair succeeded, strategy not promotable**. Do not hide a failed release gate behind a better-looking sub-bucket.

A simple ex-ante rule search may identify a research direction, but it is not production proof unless sample size and monthly stability pass. Example warning signs:

- best rule has ~50-60 trades only;
- stable months are far below threshold;
- full-pool WR remains near 55%;
- SL rate remains around 40%+.

## Reporting wording

Use the three-level closure framing:

1. Tool-proven solved: reclaim order / T+1 / pollution gates.
2. Empirically weak/strong: WR, SL, avg net, family split.
3. Not promoted: release gate failed, no frontend/live sync.

Never connect a research artifact to production/API/frontend until full-market strategy gates pass and current picks are generated from fresh scan source rather than historical completed trades.
