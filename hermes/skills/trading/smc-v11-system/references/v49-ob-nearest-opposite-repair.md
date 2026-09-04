# V49 OB nearest-opposite-candle repair

- Trigger: user pointed out the OB implementation still contradicted the accepted SMC rule: displacement is quality, not a hard filter; OB should be the nearest opposite-color candle before the swing/structure break.
- Changed `/root/.hermes/scripts/v25/smc_core_pine_like.py::ob_signals_pine_like` only.
- Before: backward scan skipped opposite candles when `displacement_ratio < ob_displacement_mult` (default 1.5), so low-displacement but structurally nearest OBs were dropped or replaced by older candles.
- After: backward scan takes the first/nearest opposite-color candle that passes the existing body/doji guard. `displacement_ratio` remains metadata and new `displacement_quality = clamp(displacement_ratio / ob_displacement_mult, 0..1)` slightly contributes to confidence.
- Verification: targeted sample symbols showed nearest-rule violations = 0 and low-displacement OBs are retained (e.g. 600130.SH idx=182 disp=0.79 quality=0.527; 300097.SZ idx=111 disp=1.25 quality=0.833).
- Rebuilt pipeline after fix: V47.1 -> V47.2 -> V48 -> V48.1 -> V49. Current V49 remains 132 trades / WR 88.64% / SL 10.61% / AvgPnL 15.11% / 3 picks; full trade exit audit PASS.
- GitNexus impact for `Function:v25/smc_core_pine_like.py:ob_signals_pine_like`: HIGH risk, direct caller `detect_all_signals_pine_like`, many historical/research engines and `smc_unified.py` kline raw markers affected. This was accepted because the user explicitly requested the signal-core correction.
