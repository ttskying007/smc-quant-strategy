# V17 Multi-TF Design (60min + Daily)

## Status: Framework Ready, Needs Data

V17 multi-timeframe resonance is designed but **cannot be tested** from this server because:
- Hubble API (primary data source) only supports daily/weekly/monthly
- akshare/eastmoney.com requires a Chinese IP or working proxy
- Sina finance also blocked from this DigitalOcean IP

## Architecture

```
60min Data (pre-cached)
    │
    ▼
60min Signal Detection ──► TF Score ──► Resonance Boost
    │                                        │
    ▼                                        ▼
Daily Signal Detection ──► Entry Decision    │
    │                                        │
    ▼                                        ▼
Weekly Trend (synthetic) ──► Trend Filter ──► Final Decision
```

## Core Algorithm

```python
def check_multi_tf_resonance(daily_bar_date, min60_data, daily_sigs):
    if no 60min data: return 0.5, 'no-60min'
    
    # Last 8 60min bars (2 trading days)
    recent_60 = get_last_60min_bars(min60_data, daily_bar_date, 8)
    
    # Detect FVG/Sweep/OB on 60min
    fvg_count = count_60min_fvg(recent_60)
    sweep_count = count_60min_sweep(recent_60)
    ob_count = count_60min_ob(recent_60)
    
    score = 0.5
    if fvg_count >= 2:  score += 0.20  # multiple FVG confirmations
    elif fvg_count >= 1: score += 0.10
    if sweep_count >= 1: score += 0.15  # liquidity grab on 60min
    if sweep_count >= 1 and fvg_count >= 1: score += 0.10  # bonus
    if ob_count >= 2: score -= 0.10  # OB noise on 60min
    
    return score, detail
```

## Resonance Threshold Adjustment

| TF Score | Daily Resonance Required | Effect |
|----------|-------------------------|--------|
| >= 0.7 | 0.55 (was 0.65) | 60min confirms → easier entry |
| 0.5-0.7 | 0.65 (standard) | Neutral |
| < 0.5 | 0.70 (stricter) | 60min against → require more daily confirmation |

## Data Format

```json
// 60min cache file: <symbol>_60min_500.json
// Source: akshare stock_zh_a_hist_min_em(period="60")
// Format:
{
    "t": "2026-03-20 10:30:00",  // datetime
    "o": 10.87,                    // open
    "h": 10.94,                    // high
    "l": 10.85,                    // low
    "c": 10.87,                    // close
    "v": 274621.0                  // volume
}
```

## Integration with V16 Swing Strategy

1. **Daily signals** remain the primary entry decision (V16 proven)
2. **60min signals** provide:
   - Early warning: FVG appears 1-2 daily bars before daily FVG
   - Confirmation: when both 60min and daily show FVG = stronger entry
   - Filter: when 60min is against daily direction → skip
3. When 60min data is unavailable, fall back to V16 daily-only strategy (proven WR=76.2%)

## How to Enable

1. Download 60min data via akshare (on a server with Chinese IP):
   ```python
   import akshare as ak
   df = ak.stock_zh_a_hist_min_em(symbol="000001", period="60",
                                   start_date="20260101", end_date="20260508", adjust="")
   # Cache to kline_cache/<symbol>_<exch>_60min_500.json
   ```
2. Use rolling_backtest_v17.py with `USE_60MIN = True`
3. Set `os.environ['HTTP_PROXY'] = 'http://127.0.0.1:7890'` if behind GFW
