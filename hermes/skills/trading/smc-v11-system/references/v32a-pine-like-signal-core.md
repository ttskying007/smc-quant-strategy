# V32A Pine-like SMC Signal Correctness Core

## Trigger
Use this reference when the user reports high SL rate, noisy K-line markers, or asks whether the issue is signal definition, entry point, SMC combination, or "not reaching entry price". Before optimizing SL/TP or WR, audit raw SMC signal correctness.

## Durable lesson
A high stop-loss rate can be a symptom of invalid raw SMC signals. Do **not** start by tuning SL/TP, RTO thresholds, or filters if BOS/CHOCH/Sweep/OB/BPR counts are structurally abnormal. First compare raw signal density against a Pine/LuxAlgo-like state machine.

## Root causes found in V27/V31 raw signal layer

1. **Swing scale too short**
   - Old core used `SWING_LEFT = SWING_RIGHT = 3` for everything.
   - This over-detects local pivots and cascades into BOS/OB/OTE/BPR explosion.
   - Use separate structure layers: swing structure, internal structure, EQH/EQL liquidity.

2. **BOS/CHOCH not implemented as current-pivot state machine**
   - Old core iterated all historical confirmed swings and emitted structure events whenever future price broke each old swing.
   - Pine/LuxAlgo semantics track a current pivot, mark it `crossed`, and replace it when a new pivot appears.
   - One pivot should break once; do not rescan all historical swings.

3. **MSS must not overwrite CHOCH**
   - Old core renamed qualifying CHOCH events to MSS, making CHOCH appear too scarce and MSS too high.
   - Correct model: CHOCH remains the base structure event; MSS is a qualification (`is_mss=True`) when valid sweep + displacement conditions exist.

4. **Sweep needs active liquidity state**
   - Old sweep scanned all recent swings each bar and allowed repeated sweeps of the same level.
   - Correct model: active liquidity levels have `swept` state; each bar/direction should emit at most one sweep; require wick penetration + close reclaim + rejection.

5. **OB should be generated only from valid structure breaks**
   - Old core generated OB for every structure event.
   - Correct model: generate OB from valid swing structure breaks or MSS-qualified internal CHOCH, using nearest opposite candle and high-volatility parsing.

6. **BPR cannot be broad FVG pair explosion**
   - Old BPR paired opposing FVGs within 100 bars, producing extreme density.
   - Correct model: restrict gap window and overlap width; treat BPR as a PD array, not an automatic trade source.

7. **EQH/EQL and Liquidity Void must be emitted by the core**
   - Frontend legends alone are not enough. If `detect_all_signals_*` does not return EQH/EQL/LV, the chart will show zero regardless of market structure.

## V32A implementation pattern

Files from the reference implementation:

- `/root/.hermes/scripts/v25/smc_core_pine_like.py`
- `/root/.hermes/scripts/v25/v32a_signal_audit.py`
- `/root/.hermes/smc_opt_v32a/v32a_signal_audit.json`
- `/root/.hermes/smc_opt_v32a/v32a_fix_summary_20260522.md`

Core design:

- `detect_all_signals_pine_like(klines, profile=None)` returns a V27-compatible signal dictionary.
- Adaptive profile chooses `swing_len`, `internal_len`, `eq_len` from ATR% and timeframe.
- Use current-pivot state objects with `current_level`, `bar_index`, `crossed`, and `bias`.
- CHOCH events retain `type='CHOCH'`; MSS is represented by `is_mss=True` and separately rendered for the frontend.
- Sweeps consume active liquidity levels.
- OB/FVG/BPR/EQH/EQL/LV are returned as explicit core outputs.

## Audit thresholds and expected density

Run full-market signal audit before accepting a raw-core change:

```bash
python3 /root/.hermes/scripts/v25/v32a_signal_audit.py --compare-old
```

V32A full A-share audit reference, 4649 cached stocks, latest 300 daily bars each:

| Signal | V32A avg / 300 bars | Old V27 avg / 300 bars | Reduction |
|---|---:|---:|---:|
| BOS | 2.037 | 29.278 | -93.04% |
| Structure | 3.495 | 39.541 | -91.16% |
| Sweep | 3.472 | 111.581 | -96.89% |
| OB | 3.486 | 39.469 | -91.17% |
| BPR | 1.951 | 74.351 | -97.38% |
| FVG | 25.679 | 66.229 | -61.23% |

Additional V32A expected averages / 300 bars:

- CHOCH: ~1.457
- MSS: ~0.526
- EQH/EQL: ~2.975
- LV: ~10.991

Audit should report no hard-threshold flags. If Sweep returns tens/hundreds per 300 bars, the core regressed.

## Frontend integration notes

When adding a new raw signal core to `smc_unified.py`:

- Add a version selector entry, e.g. `V32A Pine-like信号正确性核心`.
- Route `/api/kline_full?...&ver=V32A` to the new core.
- Keep trade overlays separate from raw-signal view if the new core is not yet the trading engine.
- Add style/family mappings for new signal types, e.g. `EQL_High`, `EQL_Low`, `LiquidityVoid_Bull`, `LiquidityVoid_Bear`.
- Verify with a live endpoint request after restart: `/api/kline_full?symbol=600519.SH&tf=daily&ver=V32A` should return 200 and nonzero `signal_count`.

## Workflow rule for future SMC stop-loss investigations

When SL hits are high, follow this order:

1. Audit raw signal density and correctness versus Pine-like semantics.
2. Only if raw signals pass, inspect strict RTO/entry validation.
3. Then inspect zone invalidation before entry and whether price actually reached entry.
4. Then inspect gap-through-stop, duplicate trades, BJ/extreme liquidity filters.
5. Only last tune SL/TP/WR metrics.

This order matches Lei's preference: signal correctness and mechanism verification before metric optimization.
