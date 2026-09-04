#!/usr/bin/env python3
"""Check per-stock: does V474 produce multiple trades at the same entry bar?"""
import json, sys
from collections import defaultdict
from pathlib import Path

# V474 only saves flat list (no symbol per trade) — need to rebuild
# by re-processing 1 representative stock

# Actually, let me check a specific stock's raw engine output
# The engine's backtest_stock_v45 returns per-stock trade list
# But that's not saved to disk for V474

# Let me check what's available
print("V474 output files:")
for f in Path('/root/.hermes/smc_opt_v474').iterdir():
    print(f"  {f.name} ({f.stat().st_size} bytes)")

# Check if any individual stock data exists
print("\nChecking V467 comparison stock:")
v467_data = json.loads(Path('/root/.hermes/smc_opt_v467/v467_full_stocks.json').read_bytes())
if isinstance(v467_data, list):
    v467_stocks = {s['symbol']: s for s in v467_data}
else:
    v467_stocks = v467_data
print(f"V467 stocks: {len(v467_stocks)}")
by_size = [(s, len(d.get('trades',[]))) for s,d in v467_stocks.items()]
by_size.sort(key=lambda x: -x[1])
print("V467 top 5 by trade count:")
for s, n in by_size[:5]:
    trades = v467_stocks[s]['trades']
    entry_idxs = [t.get('entry_idx') for t in trades]
    dupes = [(idx, [t for t in trades if t.get('entry_idx')==idx]) for idx in set(entry_idxs) if entry_idxs.count(idx) > 1]
    print(f"  {s}: {n} trades, {len(set(entry_idxs))} unique entry_idx", end="")
    if dupes:
        for idx, dupe in dupes[:2]:
            prices = set(round(t['entry_price'],4) for t in dupe)
            print(f"  DUPE@idx={idx}: {len(dupe)}x prices={prices}", end="")
    print()

# Now test V13 relaxed on one stock directly
print("\n--- Running V13 relaxed on 600519.SH to check for same-bar duplicates ---")
sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v12 import detect_all_signals_v13_60min

import json as j2
cache_dir = Path('/root/.hermes/kline_cache_60min')
for sym in ['600519.SH', '000858.SZ', '002415.SZ', '600036.SH']:
    cf = cache_dir / f"{sym.replace('.','_')}_60min_200.json"
    if not cf.exists():
        print(f"  {sym}: no cache")
        continue
    ohlcv = j2.loads(cf.read_bytes())
    if not ohlcv:
        continue
    
    sigs = detect_all_signals_v13_60min(ohlcv, params={'fvg_min_width': None, 'sweep_lookback': 12}, tf='60min')
    all_sigs = sigs.get('all', [])
    obs = [s for s in all_sigs if 'OB' in s.get('type','')]
    
    # Group OB by idx
    by_idx = defaultdict(list)
    for ob in obs:
        by_idx[ob.get('idx',0)].append(ob)
    
    dupes = {k:v for k,v in by_idx.items() if len(v) > 1}
    if dupes:
        print(f"\n  {sym}: {len(obs)} OB total, {len(dupes)} duplicate idx groups:")
        for idx, grp in sorted(dupes.items())[:5]:
            prices = set(round(ob.get('close',0),2) for ob in grp if 'close' in ob)
            print(f"    idx={idx}: {len(grp)} OBs")
    else:
        print(f"\n  {sym}: {len(obs)} OB total, NO duplicate idx — good")
