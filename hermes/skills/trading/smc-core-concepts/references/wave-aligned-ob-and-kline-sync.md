# Wave-aligned OB and K-line synchronization pitfalls

Use this reference when the user reports that SMC signals look inaccurate on the K-line chart, especially when OB appears in the middle of a trend leg or wave lines/HH-HL-LH-LL labels are missing.

## Core lesson

Reducing OB count with displacement filters is not enough. For this user, OB correctness is visual/structural: an Order Block must be anchored at a wave turning point / pullback reversal, not at any arbitrary opposite-color candle before a BOS/CHOCH.

Valid long-side OB shape:

1. A confirmed Waves-style pivot low exists (`HL`, `LL`, or initial `L`).
2. The OB candle is an opposite-color bearish candle within a small window around that pivot, typically `±3` bars.
3. A later bullish structure break confirms the area (`BOS`/`CHOCH`).
4. The confirming break has displacement evidence, e.g. break-bar range >= `ATR * 1.5`.
5. The trade/backtest stores the wave anchor metadata, not just the zone bounds.

Valid short-side OB shape:

1. A confirmed Waves-style pivot high exists (`HH`, `LH`, or initial `H`).
2. The OB candle is an opposite-color bullish candle within `±3` bars around that pivot.
3. A later bearish structure break confirms the area.
4. The confirming break has displacement evidence.

## Fields to add/verify on OB signals

OB records should include enough metadata for cross-surface audit:

- `anchor_method` = e.g. `wave_turn_opposite_candle_near_HH_HL_LH_LL`
- `wave_turn_idx`
- `wave_turn_date`
- `wave_turn_label`
- `wave_turn_price`
- `wave_turn_confirm_idx`
- `wave_turn_confirm_date`
- `wave_turn_distance`

Audit rule:

```text
Bull OB must have wave_turn_label in {HL, LL, L} and wave_turn_distance <= 3.
Bear OB must have wave_turn_label in {HH, LH, H} and wave_turn_distance <= 3.
```

If a historical `trades.json` was generated before this rule, treat it as stale. Rebuild the base trades/watchlist before using WR/RR/SL statistics.

## Pine/LuxAlgo/Waves comparison warning

Do not claim "all SMC signals are Pine-aligned" unless each family is separately audited.

Typical real-world mixed engine shape:

- Structure/BOS/CHOCH may be LuxAlgo `currentLevel`-style close crossover.
- FVG may be Pine-like 3-candle imbalance with custom ATR/gap thresholds.
- OB may be custom wave-aligned OB, which is stricter than generic "last opposite candle before break".
- Sweep/MSS/EQL/OTE/BPR/Breaker often contain local system rules and are not automatically equivalent to any Pine script.

Report this distinction explicitly. A high WR from a mixed engine does not prove signal correctness.

## K-line frontend synchronization checklist

When wave lines are missing on the frontend, verify all of these surfaces:

1. Signal core returns `wave_swings` or equivalent HH/HL/LH/LL pivot list.
2. K-line API returns both:
   - `swings` for existing compatibility
   - `wave_swings` for explicit wave rendering
3. Frontend prefers `d.wave_swings || d.swings || []`.
4. ECharts is forced to redraw when toggles/data change (`chart.clear()` before `setOption` if old overlays remain).
5. Wave line series uses `markLine` with visible symbols/labels; labels must use actual pivot labels (`HH`, `HL`, `LH`, `LL`, `H`, `L`).
6. OB tooltips/markers display `wave_turn_label` and `wave_turn_date`, so visual audit can trace each OB back to its wave anchor.

## Backtest/autopsy sequence after changing signal definitions

After changing signal semantics, do not use old trade metrics. Run the sequence:

1. Rebuild base trades and active watchlist from the new signal core.
2. Verify every OB trade still maps to a current OB with matching zone/date and wave anchor.
3. Bucket exits by reason (`SL_HIT`, `GAP_SL_HIT`, `TRAILING_STOP`, etc.).
4. For each trade compute:
   - entry position inside zone (`entry_zone_pos`)
   - SL distance and whether structural SL was capped into a fixed percentage SL
   - MFE before exit
   - post-exit MFE window (e.g. +30 bars) to detect early exits
   - whether SL was followed by reclaim/continuation, indicating possible fake-breakdown or second-entry need
5. Only then compare WR/RR/avgPnL.

Common diagnosis patterns:

- `entry_zone_pos` near 1.0 across most trades means entries are at zone high / execution-zone high; WR may be high but RR is compressed.
- Many SL trades with high post-exit MFE means SL may be structurally too tight or capped by a fixed percent before the structure actually failed.
- High trailing-stop win rate plus high post-exit MFE means runner exits are too early and should be structure-based (e.g. recent HL/market-structure invalidation), not only fixed-R trailing.

## Reporting standard for this user

When the user says SMC signals are inaccurate, answer with code-level and chart-level evidence, not only aggregate metrics:

- Actual active code path: which engine produces each signal family.
- Pine/LuxAlgo/Waves differences by signal family with severity.
- Whether current backtest files are stale relative to the code.
- Per-trade or per-bucket entry/exit autopsy: SL cause, TP reasonableness, early-exit evidence.
- Frontend synchronization proof from API fields and chart rendering contract.
