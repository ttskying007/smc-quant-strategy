# -*- coding: utf-8 -*-
r"""R129 — s23 狠打软化回测 (年度翻转修复探索)

背景 (R122/R123): s23 ×0.15 按年翻转符号 (2024 PF4.59 压错 / 2026 PF0.13 压对),
且 5 种 regime 门控无一能让桶全年<1。

方法: s23 是乘法因子且每腿至多应用一次 → 对带 s23 flag 的腿精确"未应用/重应用":
  w_variant = w_v2 / 0.15 × X   (X ∈ {0.15 现状, 0.35, 0.5, 1.0=移除})
对每变体重算组合加权 PF + 年度 PF + 块引导 P(v2var > v1)。
输出: research/handover/_r129_s23_soften.json
"""
import csv, io, json, random, sys
from collections import defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(r'E:\test\smc_project')

R1 = {r['symbol'] + '|' + r['entry_date']: float(r['v23_weight'])
      for r in csv.DictReader(open(ROOT / 'research/combo_v23_shadow.csv', encoding='utf-8-sig'))}
SH3 = {r['symbol'] + '|' + r['entry_date']: r
       for r in csv.DictReader(open(ROOT / 'research/combo_v23_shadow_v3.csv', encoding='utf-8-sig'))}
trades = list(csv.DictReader(open(ROOT / 'research/combo_v22_trades.csv', encoding='utf-8-sig')))

legs = []
for r in trades:
    k = r['symbol'] + '|' + r['entry_date']
    if k not in R1 or k not in SH3:
        continue
    has_s23 = 's23' in ((SH3[k].get('v23_flags_v2') or '').split(';'))
    legs.append({'k': k, 'y': r['entry_date'][:4], 'pnl': float(r['net_pnl_pct'] or 0),
                 'w1': R1[k], 'w3': float(SH3[k]['v23_weight_v2']), 's23': has_s23})
print(f'对齐腿: {len(legs)} | s23腿: {sum(1 for l in legs if l["s23"])}')

by_year = defaultdict(list)
for l in legs:
    by_year[l['y']].append(l)
years = sorted(by_year)


def pf_from(legs_, wk):
    pos, neg = 0.0, 0.0
    for l in legs_:
        pw = l['pnl'] * l[wk]
        if pw > 0:
            pos += pw
        elif pw < 0:
            neg += -pw
    return (pos / neg) if neg else 999


def with_s23(x):
    """返回 (w字段名, 变体权重 dict) — 对 s23 腿 w3/0.15*X。"""
    for l in legs:
        l['_wv'] = (l['w3'] / 0.15 * x) if l['s23'] else l['w3']
    return '_wv'


print(f"\n{'变体':<12} | {'PF':>6} | " + ' | '.join(f'{y}PF' for y in years))
jout = {}
for name, x in (('现状×0.15', 0.15), ('软化×0.35', 0.35), ('软化×0.5', 0.5), ('移除×1.0', 1.0)):
    wk = with_s23(x)
    pf = pf_from(legs, wk)
    ypf = {y: round(pf_from([l for l in by_year[y]], wk), 2) for y in years}
    print(f"{name:<12} | {pf:>6.2f} | " + ' | '.join(f"{ypf[y]:>5.2f}" for y in years))
    jout[name] = {'x': x, 'pf': round(pf, 3), 'yearly': ypf}

# 块引导: 每变体 P(v2var > v1)
print('\n块引导 (1000×, 块=年):')
random.seed(1729)
for name, x in (('现状×0.15', 0.15), ('软化×0.35', 0.35), ('软化×0.5', 0.5), ('移除×1.0', 1.0)):
    wk = with_s23(x)
    better = 0
    for _ in range(1000):
        boot = []
        for _ in range(len(years)):
            boot.extend(by_year[random.choice(years)])
        pf1 = pf_from(boot, 'w1')
        pfv = pf_from(boot, wk)
        if pf1 > 900 or pfv > 900:
            continue
        if pfv > pf1:
            better += 1
    jout[name]['p_beats_v1'] = round(better / 1000 * 100, 1)
    print(f"  {name}: P(v2var > v1) = {better/1000*100:.1f}%")

json.dump(jout, open(ROOT / 'research/handover/_r129_s23_soften.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
print('\n判读: 软化变体若 PF 更高且 P(v2var>v1) 不降 → s23 ×0.15 过狠, 建议软化 (影子级修改, 生产不动)。')
