# V59 → V60 Full-Market Family Gate Lessons

Use this when SMC full-market generators produce too many trades or low win-rate after moving from narrow candidate versions to all-symbol signal snapshots.

## Durable lesson

A full-market generator must separate **sample expansion** from **quality gating**:

1. First build the complete generator from the full signal snapshot so sample bias is exposed.
2. Then apply **pre-trade family-specific gates**. Do not rely on post-result filtering.
3. Treat setup families differently; equal treatment of PRIMARY / CONTINUATION / REENTRY hides the real drag.

## Observed V59 issue pattern

V59 expanded from narrow V48/V54/V58 samples into full-market 3y generation:

- Source: 4905 stocks, ~1.7M V50 signal snapshots.
- V59 result: 10,704 trades, WR ~55.4%, avg pnl ~9.7%, avg R ~2.31.
- Root cause was not sample size; sample size was now sufficient. The problem was **family mixing**:
  - PRIMARY_SETUP was noisy and dragged total WR down.
  - CONTINUATION_SETUP and REENTRY_SETUP were stronger.
  - Retest-fail / low-BQ / repeated same-symbol entries created over-trading.

## Effective V60 gate shape

Implement as a separate gate layer over the full generator, preserving provenance fields and auditability.

### PRIMARY_SETUP

Primary setups should be demoted hardest:

- Allow only `zone_type in {'OB_Bull', 'FVG_Bull'}`.
- Require `breakout_quality_score >= 60`.
- Require `breakout_quality_detail.retest_holds_raw_zone == true`.
- Use half-size (`position_size_mult_v60 = 0.5`).
- All other PRIMARY setups go to `V60_WATCH_ONLY`, not direct trades.

Reason: in full-market runs, PRIMARY can be the dominant noise source. Even after gating it may remain weaker than continuation/reentry, so do not let it dominate production picks.

### CONTINUATION_SETUP

Continuation should remain a main source but with stronger pre-entry checks:

- Require `breakout_quality_score >= 45`.
- Require `retest_holds_raw_zone == true`.
- If `zone_type == 'LiquidityVoid_Bull'`, require `quality_tier == 'A_NORMAL'`.
- Enforce same-symbol spacing from previous exit: at least 20 bars.
- Size 1.0 only when A-tier and BQ >= 55; otherwise size 0.5.

### REENTRY_SETUP

Reentry should remain a main source but avoid dense repeated trades:

- Require `breakout_quality_score >= 45`.
- Require `retest_holds_raw_zone == true`.
- Enforce same-symbol spacing from previous exit: at least 45 bars.
- Size 1.0 only when A-tier and BQ >= 55; otherwise size 0.5.

## Verification gates

After implementing a family gate, always run and report:

- total trade reduction vs prior version;
- WR / avg pnl / avg R improvement;
- per-family counts and metrics;
- `quality_metrics` audit;
- `trade_provenance_audit`;
- `signal_sequence_audit`;
- `sample_bias_audit`;
- `closed_loop_90d_review`;
- `release_gate`;
- frontend/API sync checks for summary, backtest, picks, and kline.

The successful shape from V60 was:

- trades reduced from 10,704 to about 4,450;
- WR improved from ~55.4% to ~65.7%;
- avg pnl improved from ~9.7% to ~11.7%;
- avg R improved from ~2.31 to ~2.83;
- release gate passed after 90D closed-loop review.

Do not memorize these exact numbers as future targets; use them as sanity bounds for this class of change.

## Frontend synchronization pitfall

When promoting a new SMC version after a gate layer:

- Add version directory constants.
- Update `ACTIVE_VERSION`, active trade file, active pick file.
- Add `get_version_trades(version)` and `get_version_picks(version)` branches.
- Add engine config for rerun endpoints.
- Add dropdown option.
- Verify:
  - `/api/summary`
  - `/backtest`
  - `/api/picks`
  - `/api/kline_full?symbol=...&tf=daily&ver=NEW_VERSION`

Do not claim completion if only backend JSON files changed.
