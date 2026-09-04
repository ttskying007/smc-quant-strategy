# V66 Phase 2 + V71 Pipeline Sync Lessons (2026-06-10)

## V66 Data Pipeline Architecture

```
daily_scan.py → v26_picks.json (Phase 2 POI retrace picks)
                    ↓
sync_phase2_to_v66.py → v66_picks.json + v66_trades.json + v66_report.json
                    ↓
smc_unified.py (8890 server) reads v66_* → /api/picks, /api/kline_full, etc.
                    ↓
monitor positions.json → /api/live-prices (live SL/TP/PnL)
```

**Critical pitfall**: Modifying `daily_scan.py` alone does NOT update the frontend. You must run `sync_phase2_to_v66.py` to propagate changes to the V66 data files that the frontend actually reads.

## V71 Anti-Live-SL Gates (Deployed in daily_scan.py)

Four gates, inserted at lines 309–340 after `compute_sltp()` call:

| Gate | Condition | Reject reason tag |
|------|-----------|-------------------|
| **RISK>5%** | `v25_sl_pct > 5` | `RISK_GT_5` |
| **T+1 GAP_DOWN** | `gap_down > 2.5%` OR (`gap_down > 0` AND `open < SL`) | `T1_GAP_DOWN_{pct}PCT` |
| **OB candle** | `OB_Bull` zone bar is bullish + next bar not bullish | `OB_ZONE_NOT_BEARISH_CANDLE` |
| **SL hard floor** | `sl_price >= dz_low → sl_price = dz_low * 0.995` | Built into `compute_sltp()` |

**Pitfall**: T+1 GAP_DOWN must check `gap_down_pct > 0` before checking `open < SL`, otherwise gap-up stocks get wrongly rejected when SL happens to be below entry.

## Monitor Position Live SL Fix Pattern

Old positions in `positions.json` may have `SL >= zone_low` (created before Phase 0 hard floor).
Fix script pattern:
```python
pos_file = Path('/root/.hermes/smc_monitor/positions.json')
positions = json.loads(pos_file.read_text())
for p in positions:
    if p.get('status') != 'OPEN': continue
    sl = float(p.get('sl_price', 0))
    zl = float(p.get('zone_low') or p.get('raw_zone_low') or 0)
    if zl > 0 and sl >= zl:
        p['sl_price'] = round(zl * 0.995, 4)
        p['risk_pct'] = round((float(p.get('entry_price',0)) - zl*0.995) / float(p.get('entry_price',1)) * 100, 2)
pos_file.write_text(json.dumps(positions, ensure_ascii=False, indent=2))
```
Then restart 8890 for `/api/live-prices` to pick up the patched SL.

## End-to-End Closure Verification Checklist

After any strategy-layer change, verify ALL of these before declaring done:

1. **`/api/picks`** — active count, RETRACE ratio, empty-field count for 6 fields
2. **`/api/live-prices`** — live count, SL < zone_low ratio, field completeness
3. **`/api/kline_full?symbol=SYM&ver=V66`** — trades have zone_low/zone_high/cost_line/volatility_pct; signals have v25_vol_class
4. **`/api/summary`** — trade count, WR, version is V66
5. **`/backtest`**, **`/analysis`**, **`/autopsy`** — HTTP 200, non-trivial size
6. **Browser check** of `/monitor` and `/live` pages — no '-' in zone/cost/vol columns
