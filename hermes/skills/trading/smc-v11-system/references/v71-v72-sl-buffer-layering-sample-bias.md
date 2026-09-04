# V71/V72 SL Buffer Layering and Sample-Bias Lesson

## Trigger

Use this note when a high-quality SMC candidate version reaches excellent WR/RR/SL metrics by applying hard pre-entry gates, but trade count collapses enough to create sample bias.

## Session Lesson

V71 applied strict live-SL protection on V66 trades:

- Source: V66 production trades, `137` rows.
- Strict gate: `SL must be at least 1.0% below raw_zone_low`, plus entry/risk/gap guards.
- Result: `62` trades, WR `98.39%`, SL `0%`, RR `15.2`.
- Problem: `62` trades over ~3 years is too small for production and risks severe sample bias.

The user correctly rejected treating this as a production upgrade. Excellent metrics from a collapsed sample are not enough.

## Root Cause

The dominant rejection source was not entry distance, risk, or gap logic. It was the `SL buffer below zone_low` hard gate.

On V66:

| Scenario | n | WR | SL Rate | SL n | Avg PnL | RR |
|---|---:|---:|---:|---:|---:|---:|
| V66 base | 137 | 90.51% | 8.76% | 12 | 20.65% | 6.31 |
| slbuf >= 0.25% | 85 | 96.47% | 2.35% | 2 | 15.15% | 6.21 |
| slbuf >= 0.50% | 79 | 97.47% | 1.27% | 1 | 15.50% | 7.71 |
| slbuf >= 0.75% | 70 | 98.57% | 0.00% | 0 | 16.00% | 15.10 |
| slbuf >= 1.00% | 66 | 98.48% | 0.00% | 0 | 15.93% | 15.05 |

Most V66 SL/GAP_SL losses had `slbuf` near zero, so the mechanism is real, but the 1.0% cutoff is too aggressive as a single production filter.

## Correct Pattern

Do not replace production with the strict sub-sample.

Use layered output:

| Layer | Meaning | Rule |
|---|---|---|
| Base | production/reference population | no strict `slbuf` cut |
| QualityA | high-quality layer | `slbuf >= 0.25%` |
| QualityB | stronger quality layer | `slbuf >= 0.50%` |
| Strict | anti-SL strict layer | `slbuf >= 0.75%` or `1.0%` |

Then expand upstream rather than slicing the already-small production pool:

1. Keep V66 production untouched.
2. Go back to V65/V64 or broader full-market candidate source.
3. Apply the same `slbuf` tiers on the expanded pool.
4. Publish tiers in parallel on the frontend; do not silently promote strict tier to production.

## V72 Example

V72 used V64 source trades instead of only V66:

- Source: `smc_opt_v65/v65_source_v64_trades.json`, `269` rows.
- Reapplied V66 REENTRY risk overlay: rejected `19`, retained `250` Base rows.
- Layer metrics:
  - Base: `250`, WR `84.4%`, SL `14.8%`, RR `5.715`.
  - QualityA `slbuf>=0.25%`: `148`, WR `88.51%`, SL `10.14%`, RR `5.585`.
  - QualityB `slbuf>=0.50%`: `140`, WR `89.29%`, SL `9.29%`, RR `5.654`.
  - Strict `slbuf>=0.75%`: `126`, WR `88.89%`, SL `9.52%`, RR `5.762`.

Conclusion: V72 fixed the V71 sample-size collapse, but did not beat V66 production quality. Treat it as a parallel observation/candidate pool, not a production replacement.

## Implementation Checklist

When a gate improves metrics while cutting sample size:

1. Report retained percentage and trades/year before claiming improvement.
2. Run gate-contribution analysis: each gate alone, then combinations.
3. Identify the dominant rejection gate.
4. Convert dominant hard gate into tier/score if it is useful but too aggressive.
5. Expand upstream candidate source before slicing production further.
6. Keep production version untouched until the expanded tier passes WR, SL, RR, T+1, field-contract, and frontend checks.
7. Frontend must expose the tier (`Base`, `QualityA`, `QualityB`, `Strict`) and fields such as `sl_buffer_below_zone_pct`, not hide the distinction.

## Pitfalls

- Do not call a 60-trade strict subset a production upgrade just because WR/RR look excellent.
- Do not optimize only aggregate metrics; verify whether the sample collapsed by year, signal type, setup family, or market regime.
- Do not replace a validated production version if the new expanded candidate has worse WR/SL, even if it has more trades.
- Do not keep applying tighter gates to the same small pool; go upstream and broaden the candidate source first.
