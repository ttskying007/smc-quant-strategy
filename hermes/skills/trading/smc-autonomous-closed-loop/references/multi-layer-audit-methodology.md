# Multi-Layer SMC System Audit Methodology (2026-06-10)

## When to Use

When user reports "SL problem", "信号不准", "入场问题" — do NOT start with field audits or aggregate metrics. 
Instead, trace the full signal-to-trade pipeline through 6 layers:

## Audit Layers

### Layer 1: Signal Detection (smc_core_pine_like.py)
- Are OB/FVG/BOS/CHOCH/Sweep detected correctly?
- Compare with Pine Script/LuxAlgo reference implementations
- Check zone_low/zone_high values vs K-line OHLC data
- Verify structure state machine state transitions

### Layer 2: Strategy Entry Logic (daily_scan.py / full_scan.py)
- **Critical**: entry_idx vs conf_idx — is there a retrace wait?
- Entry price vs zone boundary — inside zone, below zone, or above zone?
- Is sweep precondition checked before allowing entry?
- Is market_state computed and used as gate?
- What signal combinations are allowed?

### Layer 3: Engine Filters (v65_engine.py, v66_engine.py, etc.)
- What are the filter rules? Are they post-hoc (based on historical loss) or pre-entry (based on signal quality)?
- Do filters modify entry logic or only reject/keep trades?
- Are there field mapping gaps (raw_zone_low → zone_low, tp1_design_price → tp1)?

### Layer 4: Monitor State Machine (smc_monitor_state.py)
- Does ingest_daily_picks validate signal quality or only field completeness?
- Is trailing SL implemented in monitor? Or only in backtest?
- How are positions classified (OPEN/WATCH_ONLY/PENDING)?

### Layer 5: Frontend / API (smc_unified.py)
- Are all fields present in API responses?
- Do monitor/live/K-line pages show the right data?
- Is entry_zone_position computed or just the raw position value?

### Layer 6: Data Persistence (JSON files)
- Do physical JSON files match API responses?
- Are standard field names used (zone_low not raw_zone_low)?
- Is tp1/tp2 present with actual values?

## Quick Diagnostic Script Pattern

```python
# Check 1: Entry timing
same_bar = sum(1 for t in trades if t.get("entry_index") == t.get("conf_index"))
after_bar = sum(1 for t in trades if t.get("entry_index", 0) > t.get("conf_index", 0))

# Check 2: Zone position
above_zone = sum(1 for t in trades
    if float(t.get("entry_price",0)) > float(t.get("raw_zone_high",0)))

# Check 3: SL buffer
sl_at_zone = sum(1 for t in trades
    if abs(float(t.get("sl",0)) - float(t.get("raw_zone_low",0))) < 0.001)

# Check 4: Market state
missing_state = sum(1 for t in trades if not t.get("market_state") or t.get("market_state") == "?")
```

## Common False Positives to Watch For

1. **High WR from over-filtering**: V64(269)→V65(143)→V66(137) looks like 90% WR but V67 full-market shows 41%
2. **Field completeness ≠ signal quality**: All 137 fields present doesn't mean the entry logic is correct
3. **PnL clustering**: If 50%+ trades have identical PnL (e.g., 13.42%), check the exit mechanism for fixed-R behavior
4. **Semantic labels vs actual semantics**: `semantic_layer=UNAUDITED` on every trade means the labels are inferred, not computed

## Lei's Preference (from session)

> "不要只修字段或只看聚合指标 — 要先定位代码级根因，再决定是参数调优还是架构重建"

Always answer these questions before reporting:
1. Is the signal detection correct?
2. Is the entry logic correct (retrace wait)?
3. Is the SL position correct (buffer)?
4. Is the market state used?
5. What % of trades fail each check?
