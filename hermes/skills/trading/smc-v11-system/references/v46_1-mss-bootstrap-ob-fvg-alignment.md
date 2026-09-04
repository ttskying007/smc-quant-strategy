# V46.1 Pine/LuxAlgo MSS, bootstrap, OB/FVG alignment session note

## Trigger
Use this reference when SMC BOS/CHOCH/MSS counts look too sparse or when chart-level MSS labels and trading entries disagree.

## Key lessons

### 1. Split display MSS from trading MSS
Pine/LuxAlgo-style MSS is often an early-warning visual label. Do not consume it directly as a high-confidence reversal trade trigger.

Recommended semantics:
- `is_mss`: chart/display early-warning, usually `CHOCH + recent same-direction sweep`.
- `is_mss_confirmed`: trading-quality MSS, requires the stricter displacement/confirmation gate.

Downstream trading code should use `is_mss_confirmed` for reversal entries, while K-line/chart layers should display `is_mss`.

Concrete patch pattern:
```python
if ev.get('type') == 'BOS':
    # BOS is continuation context, not reversal/MSS trigger.
    continue
if ev.get('type') == 'CHOCH' and not ev.get('is_mss_confirmed'):
    continue
```

In actual V46.1 chain, `v46_1_layered_3y.py` consumes `v45_1_recall_repair.build_symbol()` before `v41.backtest_v34_setups()`. So patching only `v34c_next_open.py` is insufficient; synchronize the actual recall-repair path too.

### 2. bootstrap_cutoff must not over-filter confirmed pivots
For Swing Length 5, `bootstrap_cutoff = size * 2` swallowed an extra confirmed pivot range and reduced BOS/CHOCH/MSS counts. Pine/LuxAlgo leg logic only needs to avoid the unstable first leg state.

Use:
```python
bootstrap_cutoff = size
```

Validation from this session:
- before: structure events around `201501`
- after: structure events `206608`
- bad events stayed `0`

### 3. Align Pine/LuxAlgo parameters before trading optimization
From the user-provided screenshots/OCR:
- Swing Length: `5`
- OB Swing Detection Length: `7`
- OB Lookback: `10`
- OB Displacement Multiplier: `1.5`
- EQH/EQL Pivot Length: `4`
- EQH/EQL Threshold: `0.1`
- Minimum Strength Filter: `3`

Keep these parameter fixes separate from WR/RR tuning. Structure correctness comes first.

### 4. FVG raw boundary vs executable zone
Pine raw bullish FVG is the three-candle gap:
```python
gap_low = high[i-2]
gap_high = low[i]
```
Do not move raw boundaries to midpoint/display/executable zones. If trades fail, add trading-layer filters such as width, mitigation touch, confirmation, and liquidity target; do not silently redefine the raw FVG.

### 5. Frontend/K-line synchronization checklist
After structure changes, verify all layers:
1. `python3 v46_1_structure_audit.py`
2. rebuild full backtest: `python3 v46_1_layered_3y.py --rebuild-base`
3. restart `smc_unified.py` on 8890
4. hit `/api/reload`
5. hit `/api/picks`
6. hit `/monitor`
7. hit `/api/kline_full?symbol=<symbol>&tf=daily&ver=V46_1`
8. confirm `signals_list` contains `bos`, `choch`, `mss`, `ob`, `fvg`, `sweep`

Frontend chart labels must include both bull and bear variants:
```js
BOS_Bull -> BOS
BOS_Bear -> BOS
MSS_Bull -> MSS
MSS_Bear -> MSS
FVG_Bull -> FVG
FVG_Bear -> FVG
CHOCH_Bull -> CH
CHOCH_Bear -> CH
```

### 6. Interpreting post-fix metrics
After the MSS/bootstrap/parameter fixes, one full rebuild produced:
- structure files: `4649`
- structure events: `206608`
- bad_events: `0`
- kept trades: `825`
- kept WR: `81.6%`
- kept SL rate: `18.1%`
- weighted WR: `84.2%`
- weighted SL rate: `15.4%`
- weighted avg pnl: `6.53`

Do not treat these as permanent targets. The durable lesson is that structure correctness improved without breaking trade quality.

### 7. Remaining problem domains after structure repair
Once BOS/CHOCH/MSS audit passes, stop over-tuning structure. Continue with:
- `OB_NOT_VISUAL_SMC2026_ZONE`
- `FVG_NOT_PINE_PARAM_OR_BOUNDARY_SHIFT`
- `FVG_TOO_WIDE`
- `LIQUIDITY_TARGET_TOO_CLOSE_OR_MISSING`
- weak C-layer quality

In this session the main remaining issue shifted from “SMC structure wrong” to “tradeable zone quality and liquidity target space.”
