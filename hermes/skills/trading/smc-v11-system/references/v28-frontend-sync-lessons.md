# V28 Frontend Sync Lessons — Field Mapping & Signal Alignment

## Critical Learnings (2026-05-20)

### 1. V22 vs V27 Signal Detection Mismatch
**Root cause**: K-line page used V22 (`detect_all_signals_v22`) for chart markers, but trade data used V27/V28.
Result: BOS/CHOCH/MSS positions had **zero overlap** between the two engines.

**Fix**: Switch K-line `_api_kline_full` to use `smc_core_v27.detect_all_signals_v27()`
and map the V27 signal format to the frontend-expected format.

**Pitfall check**: After any signal detection change, verify:
```python
v22_sigs = detect_all_signals_v22(klines)
v27_sigs = v27.detect_all_signals_v27(klines)
overlap = set(s.idx for s in v22_bos) & set(e['index'] for e in v27_bos)
# Must be > 0 or signals are from different detection systems
```

### 2. Frontend Field Mapping for V28
V28 trades/picks use different field names than legacy V11–V25:

| Frontend JS expects | V28 data has | Fix |
|---------------------|-------------|-----|
| `t.entry_type` (入场) | `t.conf_type` | Change JS to `t.conf_type \|\| t.entry_type` |
| `t.signal_type` | `t.zone_type` | Fallback chain: `t.signal_type \|\| t.zone_type` |
| `t.signal_price` | None in V28 | Fallback: `t.signal_price \|\| t.entry_price` |
| `t.retrace_pct` | None in V28 | Fallback: `t.retrace_pct \|\| t.risk_pct` |
| `t.sl_pct` | `t.risk_pct` or computed | Compute from `(entry - sl) / entry * 100` |

**Golden rule**: Every JS field reference needs a fallback chain for V28 compatibility.

### 3. Picks Must Have Flat TP Fields
V28 picks used nested `tp_tiers: [{name, alloc, price}, ...]` but frontend
rendering code expected flat `tp1`, `tp2`, `tp3` fields.

**Fix in `v28_full_scan.py` `generate_picks()`**:
```python
tiers = t.get('tiers', [])
tp1 = tiers[0]['price'] if len(tiers) > 0 else 0
tp2 = tiers[1]['price'] if len(tiers) > 1 else 0
tp3 = tiers[2]['price'] if len(tiers) > 2 else 0
```

### 4. Live/Real-Time Page Field Mapping
`_api_live_prices` expected V25 fields (`v25_sl_price`, `v25_tp_tiers`).
V28 picks have different structure.

**Fix**: Add V28 fallback in the else branch:
- `sl_pct` → `p.risk_pct` or compute from `sl`
- `tp_price` → `p.tp1` or `p.tp_tiers[0].price`
- `cost_line` → `p.smart_money_cost`
- `vol_class` → `p.market_state`

**V100 task rerun extension (2026-06-16)**: if the user provides a "task ID" that fails with `Job with ID or name ... not found`, do not assume the SMC task is blocked. It may be a Hermes conversation/session ID rather than a cron job ID. Rerun the actual SMC daily ops pipeline, restart `smc_unified.py`, then verify `/api/picks`, `/api/live-prices`, `/monitor`, and `/live` for zero blanks. See `references/v100-task-rerun-monitor-live-verification.md` for the compact procedure.

### 5. Sweep Signal Drawing Fix
V27 sweep signals have different fields by direction:
- **Bull (SSL)**: `wick_low` — the low wick that swept below swing low
- **Bear (BSL)**: `wick_high` — the high wick that swept above swing high

**Fix in K-line signal building**:
```python
if sw['direction'] == 'bull':
    sw_price = sw.get('wick_low', sw.get('close', 0))
else:
    sw_price = sw.get('wick_high', sw.get('close', 0))
```

Signal type names: `Sweep_SSL` (green dashed) and `Sweep_BSL` (orange dashed).

### 6. Trade List Contract for K-line
`_api_kline_full` trades must include these fields for frontend rendering:
- `conf_type` — shows in "入场" column
- `zone_type` — shows in "信号" column
- `signal_type` — same as zone_type for compatibility
- `entry_type` — same as conf_type for compatibility
- `quality_score` — for tooltips

### 7. Signal Ranking Analysis
Built into `smc_diagnostics_v28.py` — 8 analysis dimensions:
- `by_ctx_seq` — full signal chain ranking
- `by_zone_conf` — zone type × confirmation
- `by_ob_grade` / `by_ote_grade` — grade effectiveness
- `by_resonance_zone` — MTF alignment impact
- `by_market_conf` — market state × confirmation
- `by_structure` — structure completeness
- `by_weekly` — weekly trend alignment

Key finding: ALIGNED resonance WR=79.3% vs CONFLICT WR=52.6% — single biggest differentiator.
