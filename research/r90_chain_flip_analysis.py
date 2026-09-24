# -*- coding: utf-8 -*-
r"""R90 补: chain v1→v2 翻转 × PnL 分析
- 各翻转型 (trend/last_event/retrace) 的净利差
- last_event 混合矩阵: 几对翻转的是真正语义反 (例 CHoCH↓→BOS↑) 还是并列代码不同
"""
import csv, sys, io
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(r'E:\test\smc_project')
rows = list(csv.DictReader(open(ROOT / 'research/combo_v22_chain_v2_norm.csv', encoding='utf-8-sig')))
print(f'chain v2 rows: {len(rows)}')

# ── 1. 各翻转的净利差
print('\n=== trend_state 翻转 × pnl ===')
g_ok, g_fl = [], []
for r in rows:
    pnl = float(r['pnl'] or 0)
    if r['old_trend'] == r['new_trend']:
        g_ok.append(pnl)
    else:
        g_fl.append(pnl)
if g_ok and g_fl:
    print(f'  未翻转 n={len(g_ok)} avg={sum(g_ok)/len(g_ok):+.2f}%')
    print(f'  翻转  n={len(g_fl)} avg={sum(g_fl)/len(g_fl):+.2f}%  (翻%n={len(g_fl)})')

# ── 2. last_event_kind 混合矩阵
print('\n=== last_event_kind 翻转矩阵 (old → new, n/avs) ===')
from collections import defaultdict
mtx = defaultdict(list)
for r in rows:
    o, n_ = r['old_last_event'], r['new_last_event']
    if o == n_:
        continue
    mtx[(o, n_)].append(float(r['pnl'] or 0))
top = sorted(mtx.items(), key=lambda kv: -len(kv[1]))
for (o, n_), pnls in top[:12]:
    if pnls:
        print(f"  {o:8s} → {n_:8s}: n={len(pnls)} avg={sum(pnls)/len(pnls):+.2f}%")

# ── 3. retrace_state 翻转: 以 retrace_ok ↔ no_retrace 为主
print('\n=== retrace_state 翻转矩阵 ===')
mtx2 = defaultdict(list)
for r in rows:
    o, n_ = r['old_retrace_state'], r['new_retrace_state']
    if o == n_:
        continue
    mtx2[(o, n_)].append(float(r['pnl'] or 0))
for (o, n_), pnls in sorted(mtx2.items(), key=lambda kv: -len(kv[1]))[:8]:
    if pnls:
        print(f"  {o:12s} → {n_:12s}: n={len(pnls)} avg={sum(pnls)/len(pnls):+.2f}%")

# ── 4. v24 影子 id (例 s7 = trend=='up') 在 v2 下命中的变化
print('\n=== v24 s1-s14 在 v2 下命中变化预判 ===')
s7_flip = sum(1 for r in rows if (r['old_trend'] == 'up') != (r['new_trend'] == 'up'))
s8_flip = 0  # sweep——不会 跳不出, 但 sweep_dir 都是 v23 shadow 的 chain json_不上
print(f'  s7 (up_trend): 命中变化腿数 {s7_flip}')
# CHoCH 加持(s1): 转 flip 了多少
choch_flip = sum(1 for r in rows if ('CHoCH' in str(r['old_last_event'])) != ('CHoCH' in str(r['new_last_event'])))
print(f'  s1 (CHoCH): 命中变化腿数 {choch_flip}')
print(f'\n总腿趋势架构控制度: {s7_flip}/{len(rows)}={(s7_flip/len(rows)*100):.1f}% 受在策略决策拉新 — 需 Mo 二轮 v24 重打栈判定"')
