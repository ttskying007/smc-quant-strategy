#!/usr/bin/env python3
"""V20.1 CHOCH改进: 快速信号对比"""
import json, sys, time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20

KLINE_DIR = Path('/root/.hermes/kline_cache')
files = sorted(KLINE_DIR.glob('*_daily_300.json'))

results = {'stocks': 0, 'total': 0, 'types': defaultdict(int)}
t0 = time.time()

for i, fp in enumerate(files):
    try:
        ohlcv = json.loads(fp.read_bytes())
        if len(ohlcv) < 50: continue
    except: continue
    
    _, s, _, _ = detect_all_signals_v20(ohlcv)
    results['stocks'] += 1
    results['total'] += s['total_signals']
    for t, c in s['type_counts'].items():
        results['types'][t] += c
    
    if (i+1) % 1000 == 0:
        elapsed = time.time() - t0
        ch = results['types'].get('CHOCH_Bull',0) + results['types'].get('CHOCH_Bear',0)
        print(f"  [{i+1}/{len(files)}] {elapsed:.0f}s sigs={results['total']} CHOCH={ch}")

elapsed = time.time() - t0
tc = results['types']
choch_total = tc.get('CHOCH_Bull',0) + tc.get('CHOCH_Bear',0)
bos_total = tc.get('BOS_Bull',0) + tc.get('BOS_Bear',0)

print(f"\n{'='*60}")
print(f"V20.1 CHOCH/BOS 改进 ({elapsed:.0f}s, {results['stocks']}只)")
print(f"{'='*60}")
print(f"CHOCH: Bull={tc.get('CHOCH_Bull',0):,d} Bear={tc.get('CHOCH_Bear',0):,d} = {choch_total:,d}总")
print(f"BOS:   Bull={tc.get('BOS_Bull',0):,d} Bear={tc.get('BOS_Bear',0):,d} = {bos_total:,d}总")
print(f"CHOCH/BOS: {choch_total:,d}/{bos_total:,d} = {choch_total/bos_total:.1%}")
print(f"每只CHOCH: {choch_total/results['stocks']:.1f}")
print(f"每只BOS:   {bos_total/results['stocks']:.1f}")
print(f"总信号: {results['total']:,d}")
