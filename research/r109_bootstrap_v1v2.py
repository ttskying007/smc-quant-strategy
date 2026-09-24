# -*- coding: utf-8 -*-
r"""R109 — v2 vs v1 PF差 的块引导显著性 (真干的统计)

做法:
  1. 对 combo_v23_shadow _w (v1) 与 combo_v23_shadow_v3 _w (v2狠打) 逐腿对齐
  2. 按年分组重采样 (block bootstrap, 块=年; 年度独立性较强)
  3. 每次块重样后重算两路加权 PF, 记录 比 (v2/v1) 和差 v2-v1
  4. N=1000 次, 报 95% CI 和 P(v2>v1)
"""
import csv, sys, io, random
from pathlib import Path
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(r'E:\test\smc_project')

R1 = {r['symbol'] + '|' + r['entry_date']: float(r['v23_weight'])
      for r in csv.DictReader(open(ROOT / 'research/combo_v23_shadow.csv', encoding='utf-8-sig'))}
R3 = {r['symbol'] + '|' + r['entry_date']: float(r['v23_weight_v2'])
      for r in csv.DictReader(open(ROOT / 'research/combo_v23_shadow_v3.csv', encoding='utf-8-sig'))}
trades = list(csv.DictReader(open(ROOT / 'research/combo_v22_trades.csv', encoding='utf-8-sig')))
legs = []
for r in trades:
    k = r['symbol'] + '|' + r['entry_date']
    if k in R1 and k in R3:
        legs.append({
            'k': k, 'y': r['entry_date'][:4],
            'pnl': float(r['net_pnl_pct'] or 0),
            'w1': R1[k], 'w3': R3[k],
        })
print(f'对齐腿: {len(legs)}')
by_year = defaultdict(list)
for l in legs:
    by_year[l['y']].append(l)
years = sorted(by_year)
print('年份:', years, '| 每年腿数:', [len(by_year[y]) for y in years])

def pf_from(legs_, wk):
    pos, neg = 0.0, 0.0
    for l in legs_:
        pw = l['pnl'] * l[wk]
        if pw > 0:
            pos += pw
        elif pw < 0:
            neg += -pw
    return (pos / neg) if neg else 999

# 观测值
obs1 = pf_from(legs, 'w1')
obs3 = pf_from(legs, 'w3')
print(f'\n观测: PF_v1={obs1:.2f} PF_v2={obs3:.2f} 比={obs3/obs1:.3f} 差={obs3-obs1:+.3f}')

# 块引导: 以年为重采样单位 (独立近似)
N_BOOT = 1000
random.seed(1729)
diffs = []
better = 0
for _ in range(N_BOOT):
    boot = []
    for _ in range(len(years)):
        y = random.choice(years)
        boot.extend(by_year[y])
    pf1 = pf_from(boot, 'w1')
    pf3 = pf_from(boot, 'w3')
    if pf1 > 900 or pf3 > 900:
        continue  # 跳除无穷
    d = pf3 - pf1
    diffs.append(d)
    if d > 0:
        better += 1

diffs.sort()
lo = diffs[max(0, int(0.025 * len(diffs)))]
hi = diffs[min(len(diffs) - 1, int(0.975 * len(diffs)))]
median = diffs[len(diffs) // 2]
print(f'\n1000 次块引导 (块=年, PF差 v2-v1):')
print(f'  95% CI: [{lo:+.3f}, {hi:+.3f}]')
print(f'  中位: {median:+.3f}')
print(f'  P(v2 > v1) = {better}/{N_BOOT} = {better / N_BOOT * 100:.1f}%')
