# K线数据前复权 — Split/Dividend Adjustment

2026-05-12. Hubble API kline data contains unadjusted split/dividend events for ~9% of stocks.

## Detection

Stock splits and large dividends create single-bar price jumps >25%:
- 002594.SZ (BYD): bar 117 ¥337.00 → ¥111.42 (66.9% change, ~3:1 split)
- 300033.SZ: ¥308.08 → ¥228.70 (25.8%)

Without adjustment: bogus MSS breaks (64.91% on BYD), corrupted swings, invalid OB/CHOCH across split boundary.

## Forward Adjustment

1. Scan for single-bar close changes >20%
2. `forward_mult = pre_price / post_price`
3. Multiply all pre-split bar OHLC by `1/forward_mult`

Usage:
```python
from split_adjuster import load_adjusted
ohlcv, was_adjusted = load_adjusted('002594.SZ')
```

500 stocks sampled: 45 (9.0%) have splits. File: `/root/.hermes/scripts/v11/split_adjuster.py`
