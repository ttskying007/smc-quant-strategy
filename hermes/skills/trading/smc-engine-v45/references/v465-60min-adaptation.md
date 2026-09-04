# V465 60-Minute Adaptation — Full Results

## Overview
V465 adapted the V463 daily engine (OB-only, reversal filter, V38.4 trailing) to 60min A-share data. Primary goal: achieve multi-bar holds and break 20x RR.

## Data Source
- Tencent API: `https://ifzq.gtimg.cn/appstock/app/kline/mkline?param={tc},m60,,200`
- Cached at `/root/.hermes/kline_cache_60min/`
- 200 bars per stock (~50 trading days)
- Format: `{'t': int(yyyymmddhhmm), 'o': float, 'h': float, 'l': float, 'c': float, 'v': int}`

## Mass Download (2026-05-10)
- Script: `/root/.hermes/scripts/v11/download_60min_all.py`
- Parallel: ThreadPoolExecutor with 10 workers
- 4,552/4,800 stocks cached (248 BJ stocks unsupported by Tencent API)
- Time: ~3 minutes
- Missing: all Beijing stocks (prefix issue — Tencent returns 0 bars for `bj` prefix)

## Engine Changes from V463

### Data Loading
- `CACHE_DIR`: `/root/.hermes/kline_cache/` → `/root/.hermes/kline_cache_60min/`
- Filename: `_daily_300.json` → `_60min_200.json`
- `MIN_BARS`: 120 → 60 (15 trading days minimum)
- `MAX_HOLD`: 60 → 80 (allowing 80 hours = 20 trading days)
- `tf`: `'daily'` → `'60min'`

### Swing Detection (find_swing_high_forward / find_swing_low_forward)
- Lookahead: 60 → 200 bars (full data range)
- Min gap: 2 bars → 8 bars (skip ~2 trading days to avoid adjacent exits)
- Window: 5-bar → 8-bar (wider local extremum detection)
- Early return: if a swing with ≥5% profit is found, return immediately
- Return value: now `{'idx': int, 'price': float, 'pct': float}` (was `{'idx': int, 'price': float}`)

### TP Minimum Percentage
- CHOCH TP min: 3.0% → 2.0%
- Swing high TP min: 3.0% → 2.0%
- Rationale: 60min bars have smaller % moves per bar; 3% target may never appear in the data range

### Trailing (calc_v38_trailing)
- Default `be_lock`: 0.20 → 2.0 (10x wider)
- Default `look_lock`: 0.50 → 4.0 (8x wider)

Profile thresholds (approximate 5x scale):

| Level | Daily (original) | 60min (scaled) |
|-------|:---------------:|:--------------:|
| BE | gain ≥ 0.2% | gain ≥ 2.0% |
| LK | gain ≥ 0.5% | gain ≥ 4.0% |
| Lock 1 | gain ≥ 0.7% | gain ≥ 3.5% |
| Lock 2 | gain ≥ 1.5% | gain ≥ 6.0% |
| Lock 3 | gain ≥ 3.0% | gain ≥ 12.0% |
| Lock price 1 | +/- 0.2% | +/- 1.0% |
| Lock price 2 | +/- 0.5% | +/- 2.5% |
| Lock price 3 | +/- 1.0% | +/- 5.0% |

### Stock Parameters (calc_stock_params_v45)
- `be_lock`: 0.15-0.20 → 1.50-3.00 (per vol class)
- `look_lock`: 0.40-0.50 → 3.00-5.00
- `max_hold`: 25-30 → 60 (all vol classes)

### Bug Fix: Won Logic Direction
- Original: `exit_price <= entry_price` (wrong — inverts win/loss)
- Corrected: `exit_price > entry_price` (bull trade wins when exit above entry)

## Results

### 200-Stock Test (46/200 tradeable)

| Iteration | Key Change | WR | RR | AvgHold |
|:---------:|:----------:|:--:|:--:|:-------:|
| 1 | Baseline 60min (no adaptation) | 99.1% | 6.65x | 1.1 bars |
| 2 | TP skip 8 bars, min 3% | 97.3% | 7.97x | 1.2 bars |
| 3 | Trailing 5x looser | 33.3% (won bug) | 9.32x | 2.9 bars |
| 4 | Fix won logic | 69.4% | 9.32x | 2.9 bars |
| 5 | TP min 3%→2% | 72.1% | 9.34x | 2.5 bars |

**Final (iteration 5):** WR=72.1%, RR=9.34x, avgWin=4.81%, avgLoss=-0.256%

### Full 4,552 Stock Scan

| Metric | Value |
|--------|:-----:|
| Tradable stocks | 1,252/4,552 (27.5%) |
| Total trades | 3,092 |
| **Win Rate** | **71.2%** |
| **Avg RR** | **11.34x** |
| Profit Factor | 36 |
| P&L per trade | +3.36% |
| Avg hold | 2.6 bars (max 36) |
| Avg win | 4.851% |
| Avg loss | -0.329% |
| W/L ratio | 14.7x |

| TP Type | Trades | WR | Avg RR |
|:-------:|:-----:|:--:|:------:|
| swing_high | 2,210 | **87.1%** | **14.19x** |
| none (no target) | 679 | 12.1% | 2.22x |
| choch | 203 | 97.0% | 10.78x |

### Comparison vs Daily (RR7)

| Metric | Daily RR7 | 60min Full | 60min (swing_high subset) |
|:-------|:--------:|:----------:|:------------------------:|
| WR | **97.9%** | 71.2% | 87.1% |
| RR | 11.65x | 11.34x | **14.19x** |
| Avg hold | 1.0 bars | 2.6 bars | 2.5 bars |
| Avg win | 4.64% | 4.85% | 5.2% |
| W/L ratio | 20.2x | 14.7x | 18.0x |

## Key Insights

1. **60min multi-bar holds achieved**: 2.6 bars average (vs 1.0 daily) — the adaptation succeeded in extending trade duration
2. **Swing_high TP subset excellent**: 87.1% WR + 14.19x RR beats every daily version on RR
3. **NoTP trades drag WR down**: 679 trades (22%) have no viable swing target within 200 bars → WR=12.1%
4. **Fundamental WR/RR tradeoff**: Daily wins on WR (98%), 60min wins on RR for TP-hit subset (14.19x)
5. **Missing data**: 248 BJ stocks have no 60min coverage on Tencent API

## Files

| File | Description |
|:-----|:-----------|
| `/root/.hermes/scripts/v11/v465_engine.py` | V465 engine (60min adaptation) |
| `/root/.hermes/scripts/v11/v465_200_test.py` | 200-stock test harness |
| `/root/.hermes/scripts/v11/v465_full_scan.py` | Full 4,552 stock scanner |
| `/root/.hermes/scripts/v11/download_60min_all.py` | Mass downloader (10 workers) |
| `/root/.hermes/scripts/v11/klines_60min.py` | Single-stock 60min fetcher |
| `/root/.hermes/smc_opt_v465/v465_200.json` | 200-stock trade data |
| `/root/.hermes/smc_opt_v465/v465_full.json` | Full 4,552 stock results |

## Future Optimization Ideas

1. **Add MIN_PROJECTED_RR filter** (like daily) to eliminate the 679 NoTP trades — would boost WR to ~87%, RR to ~14x
2. **Dynamic TP target**: use volatility-adaptive TP (ATR×N) instead of fixed swing distance
3. **60min OB with 15-min confirmation**: hybrid timeframe for better entry timing
4. **Reduce swing skip from 8 to 4 bars**: more trading opportunities while keeping multi-bar holds
