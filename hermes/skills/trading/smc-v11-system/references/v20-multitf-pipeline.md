# V20 Multi-Timeframe Pipeline

## Architecture
```
Weekly K-line (Hubble API) → Trend Filter (MA20)
    ↓ bullish only
Daily K-line (cached 4800 stocks) → V19 Signal Detection (LuxAlgo leg(20))
    ↓ FVG_Bull / OB_Bull entries
60min K-line (Tencent ifzq API, 4552 cached) → Entry Refinement (lowest low in first 4 hours)
    ↓
T+1 Backtest (multi-source TP/SL, RR≥1.0, MAX_TP=5%)
```

## Data Sources

| Timeframe | Source | Count | Format |
|-----------|--------|-------|--------|
| Weekly | Hubble API `interval=weekly` | 191 stocks | Same as daily |
| Daily | Hubble API `interval=daily` | 4800 stocks | `/root/.hermes/kline_cache/` |
| 60min | Tencent `ifzq.gtimg.cn` | 4552 stocks | `/root/.hermes/kline_cache_60min/` |

## 60min API (Tencent ifzq)

Correct URL format:
```
http://ifzq.gtimg.cn/appstock/app/kline/mkline?param=sh600519,m60,,200
```

Response format: `data['sh600519']['m60']` → `['202605111400', '1361.75', '1362.21', '1365.00', '1361.30', '11728.17', {}, '9.3655']`
Fields: [datetime, open, close, high, low, volume, {}, extra]

Symbol format: `600519.SH` → `sh600519`, `000001.SZ` → `sz000001`

## Weekly Trend Filter

```python
closes = last_20_weekly_closes
ma20 = mean(closes)
if current > ma20 * 1.02: 'bullish'
elif current < ma20 * 0.98: 'bearish'
else: 'neutral'
```

Only long entries when weekly is NOT bearish. Removes ~22% of stocks, ~24% of trades.

## Results (191 stocks with full multi-TF data)

| Metric | V19 Daily | V20 Multi-TF |
|--------|----------|-------------|
| Trades | 759 | 575 |
| WR | 99.7% | 99.7% |
| P&L | +4.02% | +4.01% |
| Bearish filtered | 0 | 42 stocks |
