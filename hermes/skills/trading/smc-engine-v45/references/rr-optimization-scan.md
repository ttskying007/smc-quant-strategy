# RR Optimization: MIN_PROJECTED_RR Filter (2026-05-10)

## Background

V463 (Strategy C) achieved WR=98.0% and RR=10.05x on 200 stocks, full 4800: WR=98.8%, RR=9.64x. User felt RR was below SMC theory expectations (should be 25-40x).

## Four Bottlenecks Diagnosed

| # | Bottleneck | Current | Problem | SMC Theory |
|---|-----------|---------|---------|-----------|
| 1 | swing_high detection | 5-bar local peak | misses 20-bar+ structures | 20-50bar structure |
| 2 | trailing locking | BE 0.2%, lock 1%/1.5%/3%/6% | trades at 4% forced out at 3% | 2-3x looser |
| 3 | TP layers | single nearest swing_high | no multi-layer extension | 1:1→1:3→1:6+ |
| 4 | SL distance | full boundary (0.5-1%) | ob_lower WR=100% means too wide | 0.1-0.15% |

## Attempted Fixes

### Attempt A: SL×0.5 + Trailing×2 + Multi-level TP
- WR dropped from 98.0% to 80.6%, RR from 10.05x to 6.27x
- Cause: SL×0.5 too tight for daily gap volatility, Trailing×2 leaves trades unprotected until 1% gain

### Attempt B: SL×0.7 + Trailing×1.2
- WR=92.7%, RR=7.32x (still regression)
- avgWin dropped from 4.076% to 2.365% — SL tightening cutting winners short

### Attempt C: Original SL + V463 tight trailing + Multi-level TP + TP1→Loosen
- WR=98.0%, RR=9.95x (basically identical to V463)
- Multi-level TP had no effect — avg hold=1.0 bars means price never reaches TP2/TP3/fib targets
- Trailing after TP1 never triggered because trades exit in 1 bar

### Key Discovery: Trailing Tightness Paradox
In A-stock daily data:
- Tight trailing (BE=0.2%) = better risk management — immediate BE protection prevents gap losses
- Loose trailing (BE=0.5%) = worse — trades exposed to pullbacks longer, no compensating upside

V463 got trailing parameters exactly right. The tight trailing acts as "instant breakeven" protection that lets the wide SL survive volatility.

### Attempt D: MIN_PROJECTED_RR Filter
Instead of changing SL/trailing/TP, filter out trades where projected RR (swing_high distance / SL distance) is below threshold.

## 4-Threshold Scan Results (200 stocks)

| MIN_RR | WR | RR | Trades | Stocks | avgWin | TP hit RR | P&L |
|--------|:--:|:--:|:-----:|:-----:|:-----:|:---------:|:---:|
| None (V463) | 98.0% | 9.64x | 247 | 88 | 4.076% | 9.51x | +3.67% |
| 3.0x | 97.5% | **11.32x** (+18%) | 202 (-18%) | 75 | 4.070% | **12.44x** | +3.97% |
| **5.0x** | **97.1%** | **12.39x** (+29%) | **174 (-30%)** | **70** | **4.369%** | **14.98x** | **+4.24%** |
| 7.0x | 96.6% | **13.47x** (+40%) | 145 (-41%) | 61 | 4.475% | **18.24x** | +4.32% |
| 10.0x | 95.7% | **14.42x** (+50%) | 115 (-53%) | 48 | 4.585% | **22.37x** | +4.38% |

## Fundamental Constraint: A-share Daily Data

avg hold = 1.0 bars. 84.5% of trades exit within 3 bars. This is structural — cannot be changed.

RR formula: RR = |exit_price - entry_price| / |entry_price - initial_sl|

For 1-bar holds:
- Max achievable avgWin: ~4-5% (limited by daily gap + swing_high distance)
- avgLoss: ~0.13-0.26% (limited by tight trailing)
- Theoretical max RR: 4.5% / 0.13% = ~35x (but this requires ALL trades to be perfect)
- Realistic max RR: ~14-15x (accounting for losses and early exits)

Per-stock outliers do reach 30-40x RR (000603.SZ RR=34x, 000422.SZ RR=33x, 000551.SZ RR=43x) but these are <5% of trades.

## Full 4800 Scan: V464-RR5 vs V464-RR7

Both thresholds run on full 4800 stock universe (2026-05-10, 127s each):

### V464-RR5 (MIN_PROJECTED_RR=5.0)
- **1,503/4,800 stocks** (31.3%), **3,987 trades**
- **WR=98.1%, RR=11.03x, PF=955, P&L=+4.39%**
- avg hold: 1.0 bars, max: 4
- TP hit: 1,278 (32.1%) WR=100% RR=13.43x
- Trailing: 2,709 (67.9%) WR=97.3% RR=9.89x
- avgWin=4.479%, avgLoss=0.248%, W/L=18.1x
- SL: adaptive 74.6%, ob_lower 18.6%, swing_low 6.8%
- TP: swing_high 88.4%, none 7.7%, choch 3.8%, macro_20 0.1%

### V464-RR7 (MIN_PROJECTED_RR=7.0)
- **1,340/4,800 stocks** (27.9%), **3,454 trades**
- **WR=97.9%, RR=11.65x, PF=950, P&L=+4.53%**
- avg hold: 1.0 bars, max: 4
- TP hit: 950 (27.5%) WR=100% RR=15.58x
- Trailing: 2,504 (72.5%) WR=97.1% RR=10.16x
- avgWin=4.636%, avgLoss=0.229%, W/L=20.2x
- SL: adaptive 77.1%, ob_lower 17.1%, swing_low 5.8%
- TP: swing_high 88.2%, none 8.4%, choch 3.3%, macro_20 0.1%

### Comparison vs V463 Baseline

| Metric | V463 | V464-RR5 | V464-RR7 |
|--------|:----:|:--------:|:--------:|
| Tradable stocks | 1,837 | 1,503 | 1,340 |
| RR | 9.64x | **11.03x (+14%)** | **11.65x (+21%)** |
| WR | 98.8% | 98.1% | 97.9% |
| P&L/trade | +4.02% | +4.39% | +4.53% |
| avgLoss | 0.262% | **0.248%** | **0.229%** |
| TP hit RR | 9.51x | 13.43x | 15.58x |
| Avg hold | 1.0 | 1.0 | 1.0 |
| Scan time | 130s | 127s | 128s |

The MIN_PROJECTED_RR filter is the ONLY effective RR optimization for A-share daily data. All structural changes (SL tightening, trailing loosening, multi-level TP, macro swing detection) produced equal or worse results. The fundamental constraint is avg hold = 1.0 bar.

## 60-Minute Data: Path to 20x+ RR

To break the 1-bar hold constraint and reach SMC theory RR (25-40x), need 60-minute data:

Current state (2026-05-10):
- 58/4800 stocks cached in /root/.hermes/kline_cache_60min/
- Tencent API: ifzq.gtimg.cn, parameter format: sz000001,m60,,200
- 200 bars per stock (about 20 trading days at 8 bars/day)
- Rate limit: 0.5s between requests, 4800 stocks ≈ 40min full cache

V37 backtest already attempted daily+60min multi-TF confirmation but was abandoned due to limited data coverage.

To proceed:
1. `python3 klines_60min.py --batch-all` (or loop all 4800 symbols)
2. Check 60min data coverage rate (expect ~90% success)
3. Adapt V463 engine: change CACHE_DIR, MIN_BARS=50, recalibrate SL=ATR×3x
4. Run 200-stock test → compare vs daily results
|--------|------|-----------|--------|
| WR | 98.0% | 97.1% | -0.9pp |
| RR | 9.64x | **12.39x** | **+29%** |
| PF | 1,394 | 1,136 | -18% |
| Trades | 247 | 174 | -30% |
| avgWin | 4.076% | **4.369%** | +7% |
| P&L | +3.67% | **+4.24%** | +16% |
| TP hit RR | 9.51x | **14.98x** | +58% |

The MIN_PROJECTED_RR filter trades trade count for trade quality. At threshold=5.0:
- 30% fewer trades but +29% higher RR
- WR still 97.1% (vs 98.0% base)
- P&L per trade +16%

To break 20x RR on A-share daily, need 60-min data (more bars for multi-level TP to work).

## Implementation

In `evaluate_v45_entry()`, add after TP calculation:

```python
# ── 最小projected RR过滤 ──
MIN_PROJECTED_RR = 5.0
if init_sl and entry_price != init_sl:
    sl_dist = abs(entry_price - init_sl) / entry_price * 100
    if tp_price and tp_pct:
        proj_rr = tp_pct / sl_dist if sl_dist > 0 else 0
        if proj_rr < MIN_PROJECTED_RR:
            return None  # RR太低, 跳过
```

File: v464_engine.py (based on v463_engine.py + RR filter)
Output dir: smc_opt_v464/
