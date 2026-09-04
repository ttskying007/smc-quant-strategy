# V46.1 SMC signal-accuracy repair: independent MSS, OB anchors, frontend trace fields

## Trigger
Use this reference when SMC K-line labels look visually wrong even after BOS/CHOCH/MSS labels are direction-aware, especially when the user says OB/MSS/CHOCH/BOS are still inaccurate compared with Pine/LuxAlgo screenshots.

## Durable lesson
Do not treat signal label rendering as signal correctness. The repair path must audit the definition chain:

1. `pivot -> structure break -> MSS/OB/FVG -> setup -> trade -> frontend drawing`
2. If any upstream anchor is wrong, frontend label changes only hide the defect.

## Pine/LuxAlgo alignment corrections learned

### 1. Pivot confirmation must be two-sided for swing structure
A one-sided leg/confirmation implementation can place BOS/CHOCH pivots in trend middles. For Pine-like visual structure, swing pivots should require both sides:

- pivot high: current high is highest over `[i-size, i+size]`
- pivot low: current low is lowest over `[i-size, i+size]`
- preserve HH/LH/HL/LL labels versus previous confirmed pivot

Keep hierarchy separated:

- `swing_len = 5` for BOS/CHOCH
- `internal_len = 3` for internal micro-structure/MSS

Never set `swing_len == internal_len`; it collapses layers and creates repeated or semantically confused structure labels.

### 2. MSS must be independent internal micro-shift, not a CHOCH attachment
Bad pattern:

```text
MSS = swing CHOCH with sweep flag
```

Correct repair pattern:

```text
recent liquidity sweep
+ internal structure break in same direction
+ displacement/body evidence
+ emit independent event type MSS
```

Recommended MSS event fields for frontend/audit:

```text
index, date, direction, level='internal', type='MSS'
pivot_idx, pivot_date, pivot_price, pivot_label
sweep_idx, sweep_date, sweep_price, sweep_type
displacement_ratio, body_ratio
pine_rule='independent_internal_shift_after_sweep'
```

Frontend should render swing BOS/CHOCH and internal MSS as separate events. Do not duplicate MSS as an extra tag on CHOCH.

### 3. OB anchor should be nearest opposite candle before break
Bad pattern:

```text
OB = extreme candle in pivot-to-break window
```

This causes 1-3 bar or larger visual offset versus Pine screenshots.

Better pattern:

```text
Bullish OB: nearest bearish candle before bullish structure break
Bearish OB: nearest bullish candle before bearish structure break
```

Use displacement only as quality metadata, not as a hard anchor filter. Required OB audit/frontend fields:

```text
created_by_event_index, created_by_event_date, created_by_event_type
created_by_pivot_label, created_by_pivot_price
bars_before_break
anchor_method='nearest_opposite_candle'
displacement_ratio, body_ratio
pine_rule='nearest_opposite_candle_before_structure_break'
```

## Frontend synchronization rule
After signal-core changes, update K-line API/drawing payloads with diagnostic fields so the user can visually judge accuracy. K-line markers should include direction and class:

```text
BOS↑ / BOS↓
CHOCH↑ / CHOCH↓
MSS↑ / MSS↓
LIQ
OB
FVG
```

Also expose trace fields in `/api/kline_full` so a browser console or tooltip can inspect pivot/sweep/OB anchor provenance.

## Verification recipe
1. Pick a user-visible reference symbol first, usually `600519.SH`.
2. Generate a per-bar trace CSV with at least:

```text
layer, kind, dir, idx, date, break_price,
pivot_idx, pivot_date, pivot_price, pivot_label,
old_trend, new_trend, mss,
sweep_idx, sweep_date,
ob_idx, ob_date, bars_before_break
```

3. Verify K-line API counts and trace integrity before full backtest:

```text
signals count by type
structure duplicates = 0
MSS events are independent `type == MSS`
OB events have `anchor_method == nearest_opposite_candle`
```

4. Restart frontend and verify HTTP entry points, not just code compile.
5. Run full-market rebuild only after K-line provenance is sane.
6. Trade audit must check both signal-source continuity and execution accounting:

```text
source_event_idx exists in current structure signals
entry/exit fields present
entry_price/exit_price/pnl_pct are on the same accounting basis
```

## Important pitfall from V46.1 full rebuild
A high WR after signal repair can still hide execution-log defects. In the V46.1 rebuild, many trades had:

```text
exit_price / entry_price implied pnl != recorded pnl_pct
```

This was not necessarily a signal error; it indicated mixed accounting basis:

- `exit_price` may represent final/last/trailing exit point
- `pnl_pct` may represent blended partial-exit realized PnL

Before claiming per-trade audit is clean, add explicit fields such as:

```text
exit_price_final
exit_price_effective
partial_exit_prices
partial_exit_weights
realized_pnl_pct
display_exit_price
```

Then ensure frontend/backtest/detail pages use the same fields.

## Files touched in the session that produced this reference
- `/root/.hermes/scripts/v25/smc_core_luxalgo_v34.py`
- `/root/.hermes/scripts/smc_unified.py`
- `/root/.hermes/smc_signal_audit/600519_signal_trace.csv`
- `/root/.hermes/smc_opt_v46_1_layered_3y/`

These paths are examples from the active environment; future sessions should rediscover paths if they changed.
