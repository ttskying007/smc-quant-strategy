# V26 Final State — Operational Summary

## Results
- **1,133 trades** (10yr+ span, 2015-2026) | WR=78.2% | RR=1.89x
- avgWin=+6.81% | avgLoss=-3.60% | Total=+5,147%
- **994 picks** total → 165 recent (120 days)

## Engine: `scripts/v25/v26_engine.py`

### SL Rules (critical)
- **Min SL = max(ATR×0.5, 1.5%)** — kills sub-1% stops that die in 1 bar
- SL base = `zone_bottom - ATR × sl_atr_mult`
- No quality-based SL tightening (removed — caused 0.2% stops)

### TP Rules
- **TP1 RR ≥ 1.5** — iterate structural resistances, skip if `r_pct < sl_pct × 1.5`
- Lookback: 120 bars (was 60)
- Entry threshold: > 1.03 × entry_price (was 1.02)
- TP2: next resistance > TP1 × 1.02

### Trail Rules
- Activate: 1.2-1.5R (was 0.6-0.8R)
- Tighten 1: 2.0-2.5R
- Tighten 2: 3.0-3.5R

### SMC Filters (mandatory)
1. Zone: OB_Bull only (FVG_Bull WR=65% over 10yr — excluded)
2. Liquidity sweep at entry (liq_sweep OR inducement OR turtle_soup)
3. Zone_sweep: zone formation must follow a sweep within 10 bars
4. STRONG MTF only (score ≥ 6)
5. Inducement required (idm_ok=True)
6. RANGE state excluded

### State Parameters
| State | sl_atr | tp1_atr | tp2_atr | trail_act | max_hold |
|-------|--------|---------|---------|-----------|----------|
| TREND_UP | 0.5 | 1.5 | 2.5 | 1.5R | 50 |
| TREND_DOWN | 1.0 | 1.3 | 2.0 | 1.2R | 45 |
| HIGH_VOL | 0.7 | 1.8 | 3.0 | 1.5R | 20 |
| LOW_VOL | 0.3 | 1.2 | 2.0 | 1.2R | 80 |

## Data Pipeline
- **Scan**: `scripts/v25/scan_3y.py` — generates OB_Bull picks from 750-bar klines
- **Download**: `scripts/v25/download_750.py` — fqkline API, 4649 stocks
- **API endpoint**: `web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={m}{code},day,,,750,qfq`
- **Kline**: `kline_cache/*_daily_750.json`

## Frontend
- **Monitor**: 120-day recency filter + 1 pick per symbol (most recent entry)
- **Live**: 45-day filter
- **All pages**: prefers V26 via reload_trades/reload_picks

## Cron
- `6c1768b50d8b`: Daily 09:00 auto-fix pipeline

## Picks Dedup Pitfall
Old code: `if p['symbol'] in used_syms` → 4855 picks
Fix: `sym_best = {}; if ed > sym_best[sym].entry_date` → 994 picks
Monitor: 120-day filter → 165 picks
