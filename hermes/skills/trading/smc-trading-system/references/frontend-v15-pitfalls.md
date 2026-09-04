# V15 Frontend Pitfalls & Patterns

## Critical: clear `__pycache__` on every restart

```bash
pkill -f "smc_unified.py"; find /root/.hermes/scripts/__pycache__ -name "smc_unified*" -delete 2>/dev/null; sleep 1; cd /root/.hermes/scripts && python3 smc_unified.py
```

Stale `.pyc` files persist across restarts and cause old bugs to reappear even when source file is fixed. ALWAYS delete cache before restarting.

## Variable Name Mixing (v12 vs v13)

Every function that references trade data must use a SINGLE variable consistently:

```python
# WRONG — mixes v12 and v13
def build_backtest():
    v13 = DEFAULT_TRADES
    pnls = [t['pnl_pct'] for t in v12]  # v12! Crash if v12 not defined
    exit_types = Counter(t.get('exit_reason') for t in v12)  # v12 again

# RIGHT
def build_backtest():
    trades = DEFAULT_TRADES
    pnls = [t['pnl_pct'] for t in trades]
    exit_types = Counter(t.get('exit_reason') for t in trades)
```

Multiple occurrences fixed in this session:
- `build_backtest()`: used `v12` in loops while `v13` for len calculation
- `build_analysis()`: same v12/v13 mixup
- `build_dashboard()`: same

## Missing `from collections import Counter`

Functions that use `Counter()` must import it locally. A top-level import does NOT protect function-level use if the function was defined after the top-level imports are gone.

```python
def build_backtest():
    from collections import Counter  # MUST be inside function
    ...
```

## pnl_pct Already in Percent

The V13/V15 engines store `pnl_pct` as raw percentage values (e.g., 11.31 means +11.31%). Do NOT multiply by 100 again. Do NOT treat as fraction (0.1131).

```python
# WRONG
avg_pnl = f"{sum(t['pnl_pct'] for t in trades)/n*100:.2f}%"  # shows 1131%

# RIGHT  
avg_pnl = f"{sum(t['pnl_pct'] for t in trades)/n:.2f}%"  # shows 11.31%
total_pnl = f"{sum(t['pnl_pct'] for t in trades):+.1f}%"  # shows +15819.9%
```

## RR Calculation with pnl_pct

Both `pnl_pct` and `sl_pct` are in percent. RR = avg_pnl / avg_sl directly, no ×100:

```python
rr = avg_pnl / (sum(t['sl_pct'] for t in trades)/n)  # RIGHT
# rr = avg_pnl / (sum(t['sl_pct'] for t in trades)/n*100)  # WRONG (0.01x)
```

## f-string Curly Brace Escaping

In f-string triple-quoted strings, `{}` are interpreted as expressions. Literal JSON/JS syntax must be escaped with `{{}}`:

```python
# CRASHES with NameError: name 'date' is not defined
docs = f"""
klines: [{date, o, h, l, c}, ...]
"""

# CORRECT
docs = f"""
klines: [{{date, o, h, l, c}}, ...]
"""
```

## Undefined Variable References in Maps

When building lookup maps, only include variables that exist:

```python
# V11_TRADES was never defined → NameError
trade_map = {'V13': V13_TRADES, 'V12': V12_TRADES, 'V11': V11_TRADES}

# FIX: remove V11
trade_map = {'V15': V15_TRADES, 'V13': V13_TRADES, 'V12': V12_TRADES}
```

## Data Source Migration (V13→V15)

When adding V15:
1. Add V15 data load: `V15_TRADES = load_json(Path('smc_opt_v15/v15_combined.json'), [])`
2. Update DEFAULT_TRADES to prefer V15
3. Add `V15_PICKS = load_json(Path('smc_opt_v15/v15_picks.json'), [])`
4. Update MONITOR to use V15 picks
5. Update trade_map in API endpoint
6. Update startup message to show V15 counts
7. Update all nav banners from "SMC V13" → "SMC V15"

## Duplicate Closing Tags from Patches

When patch inserts content near `"""` closing of f-strings, it can create duplicate `</div></body></html>"""`. Always check for doubled closing tags after patching near the end of f-strings.
