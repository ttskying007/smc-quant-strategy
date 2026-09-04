# Frontend V13 Migration — Bugs Fixed 2026-05-15

## Root Cause: v12/v13 Variable Mixing

The V22→V13 migration introduced `DEFAULT_TRADES = V13_TRADES if V13_TRADES else V12_TRADES` but
multiple page builders continued to iterate the wrong variable:

### Bug 1: `build_backtest()` iterated `v12` but used `v13` for length
```python
# BROKEN:
v13 = DEFAULT_TRADES
pnls = [t['pnl_pct'] for t in v12]   # v12 undefined → NameError
f"{v/len(v13)*100}"                   # mixing v12 data with v13 length
exit_types = Counter(..., v12)         # same
```

### Bug 2: `build_analysis()` same pattern
```python
# BROKEN:
v13_won = sum(1 for t in v12 if t['won']) if v12 else 0
v13_wr = f"{v13_won/len(v13)*100:.1f}%" if v12 else "N/A"
```

### Bug 3: Missing `from collections import Counter` in `build_backtest()`

### Bug 4: `pnl_pct` already a percentage value
The V13 engine stores `pnl_pct` as raw percentage (e.g. `11.31` not `0.1131`).
Code was doing `pnl_pct * 100` and `avg_pnl * 100`, inflating values 100x.

**Fix**: Remove all `* 100` on `pnl_pct`. Use `sum(pnl_pct)/n` directly.

### Bug 5: RR calculation with inflated denominator
```python
# BROKEN:
rr = avg_pnl / (sum(sl_pct) / n * 100)  # sl_pct already percent, *100 wrong
# FIXED:
rr = avg_pnl / (sum(sl_pct) / n)        # both already in percent
```

### Bug 6: `build_docs()` f-string escaping
The docs page is an f-string. Curly braces in documentation like `{date, o, h, l, c}`
are interpreted as Python expressions → NameError. Fix: double the braces `{{date, o, h, l, c}}`.

### Bug 7: Stale __pycache__ after edit
After patching `smc_unified.py`, the old `.pyc` bytecode can survive a restart.
Always clear bytecode before restart:

```bash
pkill -f "smc_unified.py" 2>/dev/null
find /root/.hermes/scripts/__pycache__ -name "smc_unified*" -delete 2>/dev/null
sleep 1
cd /root/.hermes/scripts && python3 smc_unified.py
```

## Correct Pattern for All Page Builders

```python
v13 = DEFAULT_TRADES
n = len(v13)
won = sum(1 for t in v13 if t['won'])
wr = f"{won/n*100:.1f}%"
avg_pnl = f"{sum(t['pnl_pct'] for t in v13)/n:.2f}%"   # pnl_pct already %
total_pnl = f"{sum(t['pnl_pct'] for t in v13):+.1f}%"
rr = avg_pnl / (sum(t['sl_pct'] for t in v13)/n)        # both percent
```

## Monitor Data Source Update

Now uses `v13_today_picks.json` (daily scan of active demand zones) instead of `V12_PICKS`.
Fallback remains: `V12_PICKS` if today's scan unavailable.

Scan results: 2284 stocks with active demand zones (age≤200, unbreached), 319 with SW+CH.

## Backtest Page Enhancements

Now includes:
- Stats card (total trades, WR, avg PnL, RR, stocks, total PnL)
- PnL distribution histogram
- Zone age breakdown (≤40, 41-60, 61-80, 81-100, 101-120, >120 days)
- Exit reason breakdown with Chinese labels (TP1命中, TP2命中, 止损, 超时, 穿Zone)
