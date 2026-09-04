# V31 Full Audit Report — Signal Definition / Implementation / Backtest / Selection / Frontend Sync

This is the canonical reference for the V31 comprehensive audit and fix.

## Key Findings

### 1. Pinbar Cannot Be Sole Confirmation
- **Root Cause**: Pinbar/Bullish Rejection was treated as a standalone trade signal
- **Fix**: Pinbar is only allowed as the LAST step after `SSL Sweep → MSS/CHOCH → POI(OB/FVG/OTE) → RTO → Pinbar/BR`
- **Audit**: 0 standalone pinbar trades in V31 (v31_audit.py verifies)

### 2. BPR-RTO Prohibited from Generating Trades
- **Root Cause**: BPR zones are contextually valid on chart but weak/noisy for backtesting
- **Fix**: BPR retained for chart display, removed from trade generation in setup builder
- **Audit**: 0 BPR trades in V31

### 3. Selection Window Was Per-Stock (Historical Pollution)
- **Root Cause**: Picks used each stock's own latest trade as reference → January trades remained ACTIVE
- **Fix**: Global as_of_date + 30-day recency window
- **Before**: 37 picks (including Jan-Apr historicals)
- **After**: 5 picks (all within 30 days of scan end date)

### 4. Backtest Window Lacked --start/--end
- **Root Cause**: Hardcoded 2026 filter, no user-configurable window
- **Fix**: --start/--end/--update-kline CLI args; full 750-bar context loaded, only output filtered by date

### 5. Frontend Chart Noise
- **Root Cause**: All raw signals (900+) plotted as circles/diamonds
- **Fix**: Default-off noisy families (EQL/LV/PO3/RB/Pinbar); Sweep as small triangles; non-key signals hidden by default

## Final Results (20260101~20260521, 4904 stocks)

```
trades=48, wins=42, losses=6, WR=87.5%
avg_pnl=4.56%, total=218.65%, avg_rr=4.73
picks=5 (600642.SH, 002259.SZ, 002309.SZ, 300749.SZ, 600800.SH)
conf: PINBAR=35, BULLISH_REJECTION=13
arch: A1_SH_MSS_OB_PINBAR=27, A1_SH_MSS_OB_BR=10, A1_SH_MSS_FVG_RTO=8, A1_SH_MSS_OTE_PINBAR=2, A1_SH_MSS_OTE_BR=1
```

## Sync Verification

| Endpoint | Expected | Actual | Status |
|---|---|---|---|
| v31_trades.json | 48 | 48 | ✅ |
| v31_picks.json | 5 | 5 | ✅ |
| v31_metrics.json | n_trades=48 | 48 | ✅ |
| /api/picks | 5 stocks | 5 | ✅ |
| /api/kline 600642.SH | 1 trade | 1 | ✅ |
| /api/kline 300749.SZ | 2 trades | 2 | ✅ |
| /api/summary | WR=87.5% | 87.5% | ✅ |
| Frontend backtest page | 48 rows | 48 | ✅ |
| Frontend selection page | 5 stocks | 5 | ✅ |
