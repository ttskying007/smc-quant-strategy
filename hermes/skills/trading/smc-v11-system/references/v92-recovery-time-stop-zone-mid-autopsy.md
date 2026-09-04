# V92 Recovery / TIME_STOP / Zone-Mid Entry Autopsy Lessons

Session context: after the V85/V86 signal layer → V87 entry/SL/TP matrix → V88 production contract → V90 daily scanner → V91 shadow scanner chain was built, the user asked for repeated full-flow autopsy focused on RECOVERY losses, TIME_STOP high-MFE rows, and whether V91 `zone_mid` entry can become production.

## Durable findings

### 1. Confirm full-market scope before claiming a version result

For this chain, the correct scope check was:

| Layer | Durable verification target |
|---|---:|
| Daily K cache | `kline_cache/*_daily_750.json` should be full market scale (~4.6k A-share files) |
| V85 generator raw candidates | `v85_candidates.json` should contain tens of thousands of rows and >4.5k symbols |
| V91 matrix | rows should equal raw V85 candidates expanded across entry/TP variants, not just V88 production rows |

Do not answer production questions from the 532-row V88 baseline alone when the question is about V85/V86 signal-layer coverage or V91 entry-position transformation.

### 2. Entry position can be the SL root cause

The important comparison is not just total WR/RR. Compare original confirmation/chase entry vs zone-position entries by the same signal population:

- `orig_v85_entry` one-bar SL bucket was materially worse than `zone_mid_limit`.
- `zone_mid_limit` reduced one-bar SL substantially while preserving high WR.

Interpretation: when chase-confirmation entry is too high, widening SL/TP first is the wrong repair. Validate `zone_high`, `zone_mid`, `zone_low` entry positions before changing exits.

### 3. RECOVERY can remain a weak bucket after entry repair

In the V92 autopsy, `RECOVERY + zone_mid` remained below production quality while `RISK`/`MIXED` performed strongly. Durable rule:

- Treat RECOVERY as its own market-state bucket.
- If RECOVERY losses are nearly all `SL_HIT`, do not merge them into the successful zone-mid production-like layer.
- Quarantine RECOVERY from active production-like picks until a RECOVERY-specific subgate proves itself across full years.

Good regression: active shadow picks should fail if `market_state == RECOVERY` appears after the RECOVERY quarantine decision.

### 4. TIME_STOP high-MFE is an exit-capture issue, not automatically signal failure

If `TIME_STOP` rows have high MFE and high/100% win rate, the signal is doing its job. The issue is capture horizon / runner design.

Required split:

- all `TIME_STOP`
- `TIME_STOP` with `mfe_r >= 1.5`
- `TIME_STOP` with `mfe_r >= 3.0`
- by `market_state`, gate, and year

Do not fix high-MFE TIME_STOP by changing signal gates. Treat it as runner/exit-capture research.

### 5. 1-bar exits identify model horizon

A large 1-bar exit share means the model is a short-horizon liquidity-capture model, not a trend-eating model. This can be valid. Do not force trend-runner assumptions onto it without a separate high-MFE runner experiment.

## Recommended loop for future SMC sessions

1. Verify source scope: symbols, rows, years, and whether the file is raw signal layer, production baseline, scanner picks, or matrix expansion.
2. Bucket by mechanism before changing code: `market_state`, gate, entry mode, exit reason, MFE, MAE, hold bars, and year.
3. Prove entry-position effects with a matrix before changing TP/SL.
4. If a weak bucket is isolated, add a regression test that prevents it from entering production-like active picks.
5. Regenerate scanner outputs, run field/T+1 tests, restart frontend, and verify `/api/picks` plus `/api/live-prices` field completeness.

## Output artifacts pattern

A good autopsy artifact contains:

- JSON report under a versioned output directory.
- CSV of the problem bucket for manual inspection.
- tests proving: full-market scope, entry-position effect, weak-bucket quarantine, high-MFE TIME_STOP classification, and production/non-production decision.
