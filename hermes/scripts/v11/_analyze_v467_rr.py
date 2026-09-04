import json, numpy as np
from collections import Counter

with open('/root/.hermes/smc_opt_v467/v467_full_trades.json') as f:
    trades = json.load(f)

rrs = [t['rr'] for t in trades if 'rr' in t]
exit_methods = [t.get('exit_method','unknown') for t in trades]
sl_pcts = [t.get('sl_pct',0) for t in trades if 'sl_pct' in t]

print(f'总交易数: {len(trades)}')
print(f'RR分布:')
print(f'  min={min(rrs):.2f}, max={max(rrs):.2f}')
print(f'  median={np.median(rrs):.2f}, mean={np.mean(rrs):.2f}')
for p in [25, 50, 75, 90, 95, 99]:
    print(f'  P{p}={np.percentile(rrs, p):.2f}x')

print(f'\nRR区间:')
for lo, hi in [(0,0.5),(0.5,1),(1,2),(2,3),(3,5),(5,10),(10,20),(20,50),(50,999)]:
    cnt = sum(1 for r in rrs if lo <= r < hi)
    print(f'  {lo}-{hi}x: {cnt} ({cnt/len(rrs)*100:.1f}%)')

print(f'\n退出方式分布:')
em_cnt = Counter(exit_methods)
for em, cnt in em_cnt.most_common():
    sub = [t['rr'] for t in trades if t.get('exit_method','')==em and 'rr' in t]
    avg_rr = np.mean(sub) if sub else 0
    print(f'  {em}: {cnt} ({cnt/len(exit_methods)*100:.1f}%), avg_RR={avg_rr:.2f}x')

print(f'\nSL_PCT分布:')
sl_arr = np.array(sl_pcts)
print(f'  min={sl_arr.min():.4f}, max={sl_arr.max():.4f}')
print(f'  median={np.median(sl_arr):.4f}, mean={np.mean(sl_arr):.4f}')
for p in [10,25,50,75,90]:
    print(f'  P{p}={np.percentile(sl_arr, p):.4f}')

print(f'\n按SL类型分RR:')
sl_types = set(t.get('sl_type','') for t in trades)
for sl_type in sorted(sl_types):
    sub = [t['rr'] for t in trades if t.get('sl_type','')==sl_type and 'rr' in t]
    if sub:
        print(f'  {sl_type}: median={np.median(sub):.2f}x, mean={np.mean(sub):.2f}x, n={len(sub)}')

print(f'\n按方向分RR:')
for d in ['bull', 'bear']:
    sub = [t['rr'] for t in trades if t.get('direction','')==d and 'rr' in t]
    if sub:
        print(f'  {d}: median={np.median(sub):.2f}x, mean={np.mean(sub):.2f}x, n={len(sub)}')

print(f'\n按entry_type分RR:')
for et in set(t.get('entry_type','') for t in trades):
    sub = [t['rr'] for t in trades if t.get('entry_type','')==et and 'rr' in t]
    if sub:
        print(f'  {et}: median={np.median(sub):.2f}x, mean={np.mean(sub):.2f}x, n={len(sub)}')

print(f'\n退出方式详情(单个):')
for em in sorted(em_cnt):
    sub = [t for t in trades if t.get('exit_method','')==em]
    sub_rrs = [t['rr'] for t in sub if 'rr' in t]
    sub_hold = [t.get('hold_bars',0) for t in sub if 'hold_bars' in t]
    if sub:
        print(f'  {em}: n={len(sub)}, RR_med={np.median(sub_rrs):.2f}x, hold_med={np.median(sub_hold):.1f}bar')
        # exit_method types breakdown
        for xm in sorted(set(t.get('exit_method_detail','') for t in sub)):
            xcnt = sum(1 for t in sub if t.get('exit_method_detail','')==xm)
            print(f'    {xm}: {xcnt}')
