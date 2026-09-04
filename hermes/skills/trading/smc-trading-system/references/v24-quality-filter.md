# V24 Quality Filter Cascade

## Constraint loss between V22→V23

When copying V22 code to build V23, three critical quality constraints were accidentally dropped:

1. **Market regime filter**: `if regime in ('TREND_DOWN', 'WEAK_DOWN'): return []`
2. **Zone max_age**: `if age > max_age_map[regime]: continue`
3. **ctx_score threshold**: `if ctx_score < min_ctx: continue` (later removed as hard filter)

These were not intentional removals — they were simply omitted when rewriting the engine loop.

## Final V24 parameter set (after 4 iterations)

```python
MIN_BARS = 80
MAX_HOLD = 30
MIN_PRICE = 5.0           # Skip zombie stocks
MIN_ATR_PCT = 1.0         # Allow low-vol stocks (CMB 1.1%)
MIN_BREAKOUT_DIST = 1.0   # BOS ≥1% above zone
MAX_BOS_ZONE_DIST = 80.0  # BOS ≤80% above zone (prevents false breakouts)
MIN_SL_DIST = 2.5         # Structural SL ≥2.5% below entry
MAX_SL_DIST = 7.0         # SL ≤7%
MIN_TP_DIST = 1.0         # TP ≥1% above entry
MAX_GAP_PCT = 3.0         # Refuse gap >3%
MIN_HOLD_BARS = 2         # Respect T+1

MAX_ZONE_AGE_TREND = 150  # Zone valid 150 bars in trend
MAX_ZONE_AGE_RANGING = 80 # Zone valid 80 bars in ranging
```

## Filter cascade (V24 → 184 trades from 4905 stocks)

```
4905 stocks
  → price < 5 yuan → skip (zombie stocks)
  → ATR% < 1.0% → skip (dead stocks like CMB at 1.1%)
  → TREND_DOWN (from_high>20% AND close<MA20) → skip (strong downtrend)
  → zone_age > max_age → skip (stale demand zones)
  → No BOS/CHOCH above zone → skip
  → BOS distance outside [1%, 80%] → skip
  → No retrace into zone within 25 bars → skip
  → No IDM/PB confirmation → skip
  → Entry gap > 3% → skip
  → No structural SL (2.5-7% below entry) → skip
  → No structural TP (≥1% above entry) → skip
  = 184 trades / 159 stocks
```

## Key pitfalls during V23→V24 migration

1. **`detect_all_signals_v22` returns tuple, not dict**: Returns `(all_signals, stats, swings, swings_dict)`. Using `.get('all', [])` fails silently → 0 trades.

2. **K-line date field is `t`, not `date`**: Using `b.get('date', ...)` on Tencent kline data returns empty string → all picks fail 45-day recency filter → "无近期选股(45天内)".

3. **Symbol format mismatch**: Trade symbols use `000027.SZ`, kline filenames use `000027_SZ_daily_300.json`. Must convert: `f"{parts[0]}.{parts[1]}"`.

4. **Frontend version update requires 15+ string replacements**: Every HTML template in `smc_unified.py` has a hardcoded version string in nav+branding+title+h2. Use `replace_all=true` with care to avoid substring clashes.

5. **`from_high` and `close_vs_ma` out of scope**: When filtering by `from_high > 20 and close_vs_ma < 0`, these variables are computed inside `classify_trend()` but needed in `backtest_stock()`. Must extract from `trend_info` dict.
