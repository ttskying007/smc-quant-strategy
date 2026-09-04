#!/usr/bin/env python3
"""Ultimate test - find the exact int"""
import json, os, sys
sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))
for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
    os.environ.pop(k, None)
from smc_engine_v4 import detect_entries_v4, backtest_v4, get_volatility_profile

cache = os.path.expanduser('~/.hermes/kline_cache/920163_BJ_daily_300.json')
with open(cache) as f:
    bars = json.load(f)

params = {'fvg_threshold': 0.26, 'score_threshold': 1.7, 'sl_mult': 2.5, 'tp_mult': 2.1}
entries = detect_entries_v4(bars, params)

for mode in ['loose', 'total', 'strict']:
    for e in entries.get(mode, []):
        idx = e.get('idx', 0)
        fvg_idx = e.get('fvg_idx', 0)
        print(f"{mode}: idx={idx} fvg_idx={fvg_idx} dir={e.get('dir')} sc={e.get('sc')}")
        
        # Check bars around idx
        for offset in range(-2, 3):
            bi = idx + offset
            if 0 <= bi < len(bars):
                b = bars[bi]
                t = b.get('t', '')
                print(f"  bar[{bi}]: t={t} type={type(t).__name__} o={b['o']} c={b['c']}")
            else:
                print(f"  bar[{bi}]: OUT OF RANGE")

# Now test the EXACT code from gen_v4_signals.py that fails
print("\n=== Replicating gen_v4_signals.py code ===")
for mode_name, mode_entries in [('strict', entries.get('strict', [])), ('total', entries.get('total', []))]:
    for e in mode_entries:
        idx = e.get('idx', 0)
        print(f"idx={idx} type={type(idx)}")
        if 0 <= idx < len(bars):
            t_val = bars[idx].get('t', '')
            print(f"  t_val={t_val} type={type(t_val)}")
            entry_time = str(t_val)[:10] if t_val else ''
            print(f"  str(t_val)[:10]={entry_time}")
        else:
            print(f"  idx OOR! bars={len(bars)} idx={idx}")
            
        # test: could the bars[idx] be something else?
        print(f"  bars[{idx}] = {type(bars[idx])}")