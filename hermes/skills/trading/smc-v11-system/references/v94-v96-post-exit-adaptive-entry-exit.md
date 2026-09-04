# V94–V96 post-exit autopsy and adaptive entry/exit contract

## Trigger

Use this note when iterating SMC systems after a user asks whether TP/SL design is wrong, whether exits sold too early, or whether entry/exit/SL should adapt across the full market instead of being tuned for individual stocks.

## Durable workflow lesson

Do **not** optimize TP/SL from aggregate WR/RR alone. Add a post-exit autopsy layer:

1. Keep the signal layer fixed first.
2. For every completed trade, locate `entry_date` and `exit_date` in daily K-line data.
3. Enforce A-share T+1: exit simulation starts from the first daily bar after `entry_date`.
4. After the historical exit, replay the next 3/5/10/20 trading days.
5. Record post-exit max high, min low, and close relative to exit price and original R.
6. Bucket by `exit_reason` before changing rules:
   - `RUNNER_TRAIL`: sold too early vs necessary trailing stop.
   - `TIME_STOP`: high MFE not captured vs no impulse.
   - `SL_HIT`: protective SL vs washout/early-entry SL.
7. Only after this autopsy, test entry-location and exit-contract matrices.

## V94 finding pattern

A robust post-exit audit should answer:

| Question | Required evidence |
|---|---|
| Did TP/runner sell too early? | % of exits where next 3/5/10/20 bars make +5%, +10%, +1R, +2R after exit |
| Was SL protective? | SL exit followed by continued downside and no recovery above entry/2R |
| Was SL a washout? | SL exit followed by reclaim and +2R within post-exit window |
| Was TIME_STOP bad? | In-trade `mfe_r` high but realized PnL low, and/or post-exit continuation strong |

Avoid the pitfall: if post-exit high and post-exit low are both large, the answer is not “hold longer”. It is “build a dynamic runner or MFE-capture rule”.

## V95/V96 adaptive-contract lesson

For full-market, non-stock-specific optimization:

- Search universal rule families, not ticker-specific exceptions.
- Explicitly audit that rule names and logic contain no `symbol` or hard-coded stock codes.
- Entry rules should be structural and market-wide, e.g. zone high/mid/low limit entries, or zone-width/risk adaptive entries.
- SL rules should anchor to invalidation structure, e.g. `structure_low_or_zone_low + buffer`, not a fixed arbitrary percentage.
- Exit rules should combine partial take-profit with MFE capture / dynamic runner, not fixed all-out TP.
- Score contracts on: yearly stability, SL rate, average PnL, post-exit sold-early rate, T+1 compliance, and coverage.

## Practical candidate rule families

### Entry

- `zone_high_touch_Nd`: fastest fill, higher washout risk.
- `zone_mid_touch_Nd`: balanced.
- `zone_low_touch_Nd`: lower SL rate, may miss some trades.
- `adaptive_width_mid_low_Nd`: wide zones require lower entry; narrow zones allow mid.
- `adaptive_risk_mid_high_Nd`: high-risk setups require lower entry; low-risk setups can enter higher.

### SL

- `zone_low_buffer`: basic zone invalidation.
- `structure_low_or_zone_buffer`: prefer actual structure invalidation if available.
- `adaptive_zone_vol_cap`: buffer scales with volatility but caps max risk.

### Exit

- `time_mfe_50pct_cap_3r`: when MFE is high, capture 50% of MFE capped at 3R.
- `adaptive_vol_runner`: giveback/activation scales with volatility.
- Fixed 1R/2R/3R exits are baselines only; they are often too early or too rigid.

## Acceptance gates for production candidate

A candidate should not be promoted only because top-line Avg/WR improved. Require:

| Gate | Requirement |
|---|---|
| Full-market coverage | Run all available production signals; no sampling-only conclusion |
| Non-specificity | No ticker-specific branches or symbol-coded logic |
| T+1 | zero violations |
| Year stability | each major year has enough trades and acceptable WR/SL |
| Field contract | each trade has entry date, exit date, entry/SL/TP, exit reason, PnL, post-exit metrics |
| Sold-early check | post-exit big-up rate does not worsen materially |
| SL diagnosis | SL bucket split into protective/washout/early-entry categories |

## Reporting format

For Lei’s SMC tasks, report in compact tables:

1. Baseline vs candidate summary.
2. Year-by-year stability.
3. Top rule combinations.
4. Exit-reason post-exit autopsy.
5. SL classification table.
6. File paths for JSON/CSV/Markdown artifacts.

Do not present the result as “TP/SL optimized” unless the post-exit autopsy and yearly stability gates are included.
