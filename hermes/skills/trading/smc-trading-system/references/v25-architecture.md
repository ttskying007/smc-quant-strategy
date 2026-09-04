# V25 Architecture — Dynamic SL/TP + Auto-Fix Pipeline

## Key Design Decisions

### 1. SL: Cost Line, Not Entry Price
Smart money places stops at their cost basis, not at entry.
- `sl = zone_bottom - ATR × k`  (not `entry × (1 - pct)`)
- This is the core SMC insight: if smart money bought at zone_bottom,
  they stop out below it. Our entry may be higher than zone_bottom,
  so using entry-based SL would stop us out before smart money does.

### 2. TP: V24 BOS Levels, Not Fixed %
V24 engine already computed structural TP targets (BOS_level, FVG_resist,
swing_high). V25 reuses these instead of recalculating.
- `parse_v24_tp_tiers()` converts `"BOS_level:9.4(9.3%)"` → `{'price':9.4, 'pct':9.3, 'type':'BOS_level'}`
- Multi-tier: TP1=30%, TP2=30%, TP3=40% (trailing only)

### 3. ATR-Adaptive + Regime-Tuned
SL buffer = ATR × k where k depends on:
- Volatility class (LOW/MEDIUM/HIGH/EXTREME)
- Regime (TREND_UP tightens ×0.8, RANGE widens ×1.2)

### 4. Trailing (not yet live, design ready)
- Activate after 1R profit
- Tighten after 2R
- Buffer: 1.0 ATR normal, 0.5 ATR tight

## File Layout

```
/root/.hermes/scripts/v25/
├── engine_v25.py       # Dynamic SL/TP computation
├── auto_fix.py         # Auto-fix detection pipeline
└── __init__.py

/root/.hermes/smc_opt_v25/
├── v25_picks.json      # Enhanced picks with V25 fields
└── auto_fix_report.json # Latest auto-fix run report
```

## V25 Pick Fields (added by engine_v25)

| Field | Type | Description |
|-------|------|-------------|
| v25_sl_price | float | Dynamic SL price (zone_bottom - ATR×k) |
| v25_sl_pct | float | SL as % of entry |
| v25_sl_reason | str | Human-readable SL rationale |
| v25_tp_tiers | list[dict] | 3-tier TP: {price, pct, type, alloc} |
| v25_cost_line | float | Smart money cost basis (70% zone height) |
| v25_zone_bottom | float | Zone lower edge |
| v25_zone_top | float | Zone upper edge |
| v25_atr | float | ATR(14) value at entry |
| v25_atr_pct | float | ATR as % of price |
| v25_vol_class | str | Volatility class (LOW/MEDIUM/HIGH/EXTREME) |

## Zone Type Extraction Pattern

V24 picks don't have `zone_type` field. Extract from `detail`:
```python
detail = pick.get('detail', '')  # "FVG_Bull→BOS→PB_BOUNCE [TREND_UP]"
zone_type = detail.split('→')[0].strip()  # "FVG_Bull"
is_bull = 'Bull' in zone_type
```

## tp_tiers String Parsing

V24 `tp_tiers` is a descriptive string, not a list:
```
"BOS_level:9.4(9.3%)"                           → [{type:'BOS_level', price:9.4, pct:9.3}]
"FVG_resist:6.92(1.8%),swing_high:7.43(9.3%)"  → [{type:'FVG_resist', price:6.92, pct:1.8}, {type:'swing_high', price:7.43, pct:9.3}]
```

Regex: `([^:]+):([\d.]+)\(([\d.]+)%\)`

## Frontend Integration Checklist

When updating `_api_live_prices` for new pick format:
1. Check SL/TP computation uses correct fields (v25_* vs old fields)
2. `tpTiers` sent to JS must be `[number, ...]` not string
3. `signalSeq` uses `detail` field for display
4. New columns (costLine, volClass) added to both backend and JS template

## Auto-Fix Cron Jobs

```
Job: 3a345e35dbdd  "SMC V25 Auto-Fix Pipeline"     @ 09:00 Mon-Fri
Job: d7feed9d29b0  "SMC V25 After-Market Analysis" @ 15:30 Mon-Fri
```

Manual run: `cd /root/.hermes/scripts && python3 v25/auto_fix.py [--dry-run]`
