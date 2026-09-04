#!/usr/bin/env python3
"""Test signals_vPine on 200 stocks — compare signal quality vs V11 baseline"""
import sys, json, time
from pathlib import Path
sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_vPine import detect_all_signals_vPine
from v11.signals_v11 import detect_all_signals_v11

CACHE_DIR = '/root/.hermes/kline_cache_60min'

# Load symbol list
symbols = []
fpath = '/root/.hermes/kline_cache_60min/symbols_4552.json'
if not Path(fpath).exists():
    import glob
    files = sorted(glob.glob(f'{CACHE_DIR}/*_60min_200.json'))
    symbols = [f.replace(f'{CACHE_DIR}/', '').replace('_60min_200.json', '').replace('_', '.') for f in files]
else:
    symbols = json.loads(Path(fpath).read_text())

print(f"Total symbols: {len(symbols)}")

# Test first 200 symbols
test_syms = symbols[:200]

from pathlib import Path

def load_ohlcv(symbol):
    fname = f"{symbol.replace('.','_')}_60min_200.json"
    fpath = Path(CACHE_DIR) / fname
    if not fpath.exists():
        return None
    data = json.loads(fpath.read_text())
    if not data or len(data) < 60:
        return None
    for bar in data:
        if 'date' not in bar and 't' in bar:
            bar['date'] = str(bar['t'])
    return data

import collections

print(f"\n{'='*80}")
print(f"Testing signals_vPine vs signals_v11 on {len(test_syms)} stocks")
print(f"{'='*80}")

# Signal type stats
v11_stats = collections.Counter()
vPine_stats = collections.Counter()
ob_v11 = 0
ob_vPine = 0
fvg_v11 = 0
fvg_vPine = 0
choch_v11 = 0
choch_vPine = 0
swing_v11_h = 0
swing_v11_l = 0
swing_vPine_h = 0
swing_vPine_l = 0
displacement_detected = 0
total_ob_vPine = 0

t0 = time.time()

for idx, sym in enumerate(test_syms):
    ohlcv = load_ohlcv(sym)
    if not ohlcv:
        continue

    try:
        v11_result = detect_all_signals_v11(ohlcv)
        vPine_result = detect_all_signals_vPine(ohlcv)
    except Exception as e:
        print(f"  [{idx:3d}] {sym:12s} ERROR: {e}")
        continue

    v11_sigs = v11_result['all']
    vPine_sigs = vPine_result['all']

    # Count signal types
    for s in v11_sigs:
        st = s.get('type', 'unknown')
        key = st.split('_')[0] if '_' in st else st
        v11_stats[key] += 1

    for s in vPine_sigs:
        st = s.get('type', 'unknown')
        key = st.split('_')[0] if '_' in st else st
        vPine_stats[key] += 1

    n_ob_v11 = sum(1 for s in v11_sigs if 'OB' in s.get('type', ''))
    n_ob_vPine = sum(1 for s in vPine_sigs if 'OB' in s.get('type', ''))
    ob_v11 += n_ob_v11
    ob_vPine += n_ob_vPine

    n_fvg_v11 = sum(1 for s in v11_sigs if 'FVG' in s.get('type', '') and 'Mitigated' not in s.get('type', '') and 'IFVG' not in s.get('type', ''))
    n_fvg_vPine = sum(1 for s in vPine_sigs if 'FVG' in s.get('type', '') and 'Mitigated' not in s.get('type', '') and 'IFVG' not in s.get('type', ''))
    fvg_v11 += n_fvg_v11
    fvg_vPine += n_fvg_vPine

    n_choch_v11 = sum(1 for s in v11_sigs if 'CHOCH' in s.get('type', ''))
    n_choch_vPine = sum(1 for s in vPine_sigs if 'CHOCH' in s.get('type', '') or 'BOS' in s.get('type', ''))
    choch_v11 += n_choch_v11
    choch_vPine += n_choch_vPine

    # Check OB displacement ratios
    for s in vPine_sigs:
        if 'OB' in s.get('type', ''):
            total_ob_vPine += 1
            dr = s.get('metadata', {}).get('displacement_ratio', 0)
            if dr >= 1.3:
                displacement_detected += 1

    if (idx + 1) % 20 == 0:
        print(f"  [{idx+1:3d}/{len(test_syms)}] done ({time.time()-t0:.0f}s)")

t_total = time.time() - t0
print(f"\n{'='*80}")
print(f"RESULTS ({t_total:.0f}s)")
print(f"{'='*80}")

print(f"\nSignal Count Comparison (200 stocks):")
print(f"  {'Type':15s} {'V11':>8s} {'V-Pine':>8s} {'Δ%':>8s}")
print(f"  {'-'*15} {'-'*8} {'-'*8} {'-'*8}")

all_keys = set(v11_stats.keys()) | set(vPine_stats.keys())
for key in sorted(all_keys):
    v11n = v11_stats.get(key, 0)
    vPinen = vPine_stats.get(key, 0)
    delta = (vPinen - v11n) / max(v11n, 1) * 100
    print(f"  {key:15s} {v11n:8d} {vPinen:8d} {delta:+7.1f}%")

print(f"\nKey Signals:")
print(f"  OB (V11):    {ob_v11:6d}")
print(f"  OB (V-Pine): {ob_vPine:6d} (swing-scan + displacement >= 1.3x)")
print(f"  OB w/ disp>=1.3: {displacement_detected}/{total_ob_vPine} ({displacement_detected/max(total_ob_vPine,1)*100:.1f}%)")
print(f"  FVG (V11):    {fvg_v11:6d}")
print(f"  FVG (V-Pine): {fvg_vPine:6d}")
print(f"  CHOCH (V11):    {choch_v11:6d}")
print(f"  CHOCH/BOS (VP): {choch_vPine:6d}")
