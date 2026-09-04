#!/usr/bin/env python3
"""V20 vs V19 全量对比: 信号数量 + 回测 + 序列"""
import json, sys, time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v19 import detect_all_signals_v19, detect_signal_sequences as seq19
from v11.signals_v20 import detect_all_signals_v20, detect_signal_sequences as seq20
from v11.signals_v20 import _calc_atr

KLINE_DIR = Path('/root/.hermes/kline_cache')
OUT_DIR = Path('/root/.hermes/smc_opt_v20')
OUT_DIR.mkdir(exist_ok=True)

files = sorted(KLINE_DIR.glob('*_daily_300.json'))
print(f"Files: {len(files)}")

results = {
    'v19': {'stocks': 0, 'total_signals': 0, 'type_totals': defaultdict(int), 'seq_stocks': 0, 'total_seqs': 0},
    'v20': {'stocks': 0, 'total_signals': 0, 'type_totals': defaultdict(int), 'seq_stocks': 0, 'total_seqs': 0},
}

t0 = time.time()
for i, fp in enumerate(files):
    sym = fp.stem.replace('_daily_300', '')
    try:
        ohlcv = json.loads(fp.read_bytes())
        if len(ohlcv) < 50: continue
    except: continue
    
    # V19
    _, s19, _, _ = detect_all_signals_v19(ohlcv)
    results['v19']['stocks'] += 1
    results['v19']['total_signals'] += s19['total_signals']
    for t, c in s19['type_counts'].items():
        results['v19']['type_totals'][t] += c
    
    # V20
    sigs20, s20, _, _ = detect_all_signals_v20(ohlcv)
    results['v20']['stocks'] += 1
    results['v20']['total_signals'] += s20['total_signals']
    for t, c in s20['type_counts'].items():
        results['v20']['type_totals'][t] += c
    
    # Sequences — V20 with ATR adaptive
    atr = _calc_atr(ohlcv, 14)
    avg_p = sum(b['c'] for b in ohlcv[-50:])/min(50, len(ohlcv))
    atr_pct = atr/avg_p if avg_p > 0 else 0.02
    sq20 = seq20(sigs20, atr_pct=atr_pct)
    if sq20:
        results['v20']['seq_stocks'] += 1
        results['v20']['total_seqs'] += len(sq20)
    
    if (i+1) % 1000 == 0:
        elapsed = time.time() - t0
        print(f"  [{i+1}/{len(files)}] {elapsed:.0f}s | v19: {results['v19']['total_signals']} sigs | v20: {results['v20']['total_signals']} sigs | seqs: {results['v20']['seq_stocks']} stocks")

elapsed = time.time() - t0

# Print summary
print(f"\n{'='*70}")
print(f"  V19 vs V20 全量信号对比 ({elapsed:.0f}s)")
print(f"{'='*70}")

v19_s = results['v19']; v20_s = results['v20']

print(f"\n  总信号数:")
print(f"    V19: {v19_s['total_signals']} ({v19_s['stocks']} stocks)")
print(f"    V20: {v20_s['total_signals']} ({v20_s['stocks']} stocks)")
print(f"    增量: +{v20_s['total_signals']-v19_s['total_signals']} ({((v20_s['total_signals']/v19_s['total_signals'])-1)*100:.0f}%)")

print(f"\n  各类型信号对比:")
all_types = sorted(set(list(v19_s['type_totals'].keys()) + list(v20_s['type_totals'].keys())))
for t in all_types:
    c19 = v19_s['type_totals'].get(t, 0)
    c20 = v20_s['type_totals'].get(t, 0)
    delta = c20 - c19
    pct = f"+{delta/c19*100:.0f}%" if c19 > 0 else "NEW"
    marker = " ⬆" if delta > c19*0.1 else (" ⬇" if delta < -c19*0.1 else "")
    print(f"    {t:20s}: {c19:>6d} → {c20:>6d} ({pct:>6s}){marker}")

print(f"\n  序列检测:")
print(f"    V20 有序列的股票: {v20_s['seq_stocks']}")
print(f"    V20 总序列数: {v20_s['total_seqs']}")

# Save
json.dump({
    'v19': {k: dict(v) if isinstance(v, defaultdict) else v for k, v in v19_s.items()},
    'v20': {k: dict(v) if isinstance(v, defaultdict) else v for k, v in v20_s.items()},
}, open(OUT_DIR / 'v20_signal_comparison.json', 'w'), indent=2, ensure_ascii=False)

print(f"\nSaved to {OUT_DIR / 'v20_signal_comparison.json'}")
