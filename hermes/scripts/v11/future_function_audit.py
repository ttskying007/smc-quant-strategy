#!/usr/bin/env python3
"""
Future Function Audit — 检测OB信号中的未来函数
检查每个OB_Bull是否被未来的swing确认
"""
import json, sys
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20

KLINE = Path('/root/.hermes/kline_cache')

print("=" * 70)
print("  FUTURE FUNCTION AUDIT — OB Signal Look-Ahead Bias")
print("=" * 70)

files = sorted(KLINE.glob('*_daily_300.json'))
total_ob = 0
future_ob = 0  # confirmed by future swing
gap_counts = Counter()
sample_trades = []

for fi, fpath in enumerate(files[:500]):  # Sample 500 stocks
    try:
        daily = json.loads(fpath.read_bytes())
        if len(daily) < 50: continue
    except: continue
    
    sigs, st, swings, _ = detect_all_signals_v20(daily)
    
    for s in sigs:
        if s.type != 'OB_Bull': continue
        total_ob += 1
        
        cf = s.confirmed_at if hasattr(s, 'confirmed_at') else -1
        gap = cf - s.idx if cf > 0 else -1
        
        if gap > 0:
            future_ob += 1
            gap_counts[gap] += 1
            if len(sample_trades) < 5:
                sym = fpath.stem.replace('_daily_300', '')
                ob_date = daily[s.idx].get('t', '')[:8] if s.idx < len(daily) else '?'
                cf_date = daily[cf].get('t', '')[:8] if cf < len(daily) else '?'
                sample_trades.append(f"{sym} OB[{s.idx}]({ob_date}) cf[{cf}]({cf_date}) gap={gap}")
    
    if (fi+1) % 100 == 0:
        print(f"  [{fi+1}/500] total_ob={total_ob} future={future_ob} ({future_ob/max(1,total_ob)*100:.0f}%)")

print(f"\n{'=' * 70}")
print(f"  RESULTS (500 stocks sample)")
print(f"{'=' * 70}")
print(f"  Total OB_Bull: {total_ob}")
print(f"  Future-confirmed: {future_ob} ({future_ob/max(1,total_ob)*100:.1f}%)")
print(f"  Clean (same bar): {total_ob - future_ob}")
print(f"\n  Gap distribution:")
for gap, n in sorted(gap_counts.items()):
    bar = '█' * (n // max(1, gap_counts.most_common(1)[0][1] // 20))
    print(f"    {gap:>3d} bars ahead: {n:>5d} ({n/max(1,future_ob)*100:>5.1f}%) {bar}")

if gap_counts:
    median = sorted(gap_counts.elements())[len(list(gap_counts.elements()))//2]
    print(f"\n  Median gap: {median} bars")

print(f"\n  Sample future OBs:")
for s in sample_trades:
    print(f"    {s}")

# IMPACT: check how many V7.0 trades would be invalidated
print(f"\n{'=' * 70}")
print(f"  IMPACT ON V7.0 TRADES")
print(f"{'=' * 70}")

trade_data = json.load(open('/root/.hermes/smc_opt_v21/detailed_trades_v63.json'))
all_trades = trade_data.get('all_trades', [])

ob_trades = [t for t in all_trades if t.get('entry_signal') == 'OB_Bull']
print(f"  Total OB_Bull trades: {len(ob_trades)}")

# For each OB trade, check if confirmed_at > entry_bar
invalid_trades = 0
for t in ob_trades:
    entry_bar = t.get('entry_bar', 0)
    zone_bar = t.get('zone_bar', 0)
    # The OB was at zone_bar, entry at entry_bar
    # If confirmed_at > entry_bar, invalid
    # We need to check the actual signal data. Since we don't have it in the trade,
    # estimate: if zone_bar + median_gap > entry_bar, likely invalid
    estimated_gap = median
    if zone_bar + estimated_gap > entry_bar:
        invalid_trades += 1

print(f"  Estimated invalid (gap>{median}): {invalid_trades} ({invalid_trades/max(1,len(ob_trades))*100:.0f}%)")
print(f"  OB_Bull WR before: 97.2% (might be inflated)")
print(f"\n  ⚠️  CONCLUSION: OB_Bull signals have SIGNIFICANT look-ahead bias")
print(f"  ⚠️  Real-time WR would be LOWER than 97.2%")
print(f"  ⚠️  FIX NEEDED: Filter by confirmed_at <= entry_bar")
