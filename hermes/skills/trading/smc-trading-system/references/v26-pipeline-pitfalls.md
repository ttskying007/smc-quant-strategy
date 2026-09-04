# V26 Pipeline Pitfalls (2026-05-19)

## Daily Scan vs Historical Backtest Split

V26 has TWO separate workflows:

1. **scan_3y.py** → generates historical picks (41,812 raw picks from 10y data)
2. **v26_engine.py** → samples picks, filters, simulates, saves trades + picks
3. **daily_scan.py** → scans last 30 bars for today's signals, enriches with SL/TP/state

**Critical**: engine saves picks from pre-filter stage without SL/TP computation.
Must run enrichment separately after engine completes.

## Picks Enrichment Pipeline

The engine's `save_picks` logic saves one pick per traded symbol from the pre-filter list.
These picks have placeholder SL/TP values (0, []). Must run enrichment:

```python
from daily_scan import compute_sltp
for p in picks:
    if p.get('v25_sl_pct', 0) < 0.1 or not p.get('regime', ''):
        enriched = compute_sltp(p, klines)
        p.update(enriched)
```

## RANGE State SL Explosion Bug

When `detect_state()` returns RANGE, and STATE_PARAMS has `sl_atr_mult: 999`,
the SL calculation explodes: `sl_base = dz_low - atr * 999` → negative → SL=2989%.

**Fix**: RANGE/UNDEFINED states fallback to TREND_UP params:
```python
if state in ('RANGE', 'UNDEFINED'):
    state = 'TREND_UP'
params = STATE_PARAMS.get(state, STATE_PARAMS['TREND_UP'])
```

## Picks Dedup

The engine saves picks by filtering `filtered` (pre-state/RR picks) by `trade_symbols`.
One symbol can have multiple historical picks → result is too many picks.

**Fix**: Save one pick per traded symbol (most recent entry_date):
```python
sym_best = {}
for p in filtered:
    if sym in trade_symbols:
        if sym not in sym_best or p['entry_date'] > sym_best[sym]['entry_date']:
            sym_best[sym] = p
```

## Monitor Today-Only Filter

SMC is daily selection. Monitor page must show only TODAY's picks:

```python
cutoff = (now - timedelta(days=1)).strftime('%Y%m%d')
if now.weekday() >= 5:  # weekend → Friday
    days_back = now.weekday() - 4
    cutoff = (now - timedelta(days=days_back)).strftime('%Y%m%d')
recent_picks = [p for p in picks if str(p.get('entry_date', '')) >= cutoff]
```

## Tencent fqkline API

Correct endpoint for long-history kline:
```
http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={m}{code},day,,,{bars},qfq
```
where m=sh/sz/bj. Returns qfqday key with 750+ bars from ~2015.

NOT the mkline endpoint (`ifzq.gtimg.cn/appstock/app/kline/mkline`) which returns -1/param error.

## SMC Mandatory Constraints (V26)

After extensive backtesting, these constraints converge to quality SMC signals:
1. **Zone type**: OB_Bull only (FVG_Bull WR=61-65% over 10y in A-shares, unreliable)
2. **Liquidity sweep**: Zone must form after a swing low sweep
3. **Inducement**: Required (smart money trap confirmation, WR=87% with it)
4. **MTF STRONG only**: score≥6 (price>MA20 + near 60D high + zone quality + conf bonus)
5. **Min SL**: max(ATR×0.5, 1.5%) — no sub-1.5% stops
6. **TP1 RR floor**: ≥1.5×SL — skip too-close resistances
7. **Delayed trail**: activate at 1.2-1.5R (not 0.6-0.8R) — let winners run
