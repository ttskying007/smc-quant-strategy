# -*- coding: utf-8 -*-
r"""R92 — v2 链下重校准 s1 (CHoCH) / s7 (up_trend)

R91 结论: 直接把 v1 的 s1=0.5 / s7=0.7 套到 v2 语义→ PF 5.63 (v1 为 5.89).
本轮: 先测 v2 语义下 CHoCH 腿 vs 其余 / up 腿 vs 其余 的真实统计,
      再对 (w_s1, w_s7) 微网搜索, 看 v2 量链下是否可拽回 v1 PF ≥5.89.
"""
import csv, sys, io
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(r'E:\test\smc_project')

# 取 R91 输出: combo_v23_shadow_v2.csv 带 v2 weights (s1+s7 已重打)
rows = list(csv.DictReader(open(ROOT / 'research' / 'combo_v23_shadow_v2.csv', encoding='utf-8-sig')))
CH2 = {r['symbol'] + '|' + r['entry_date']: r
       for r in csv.DictReader(open(ROOT / 'research/combo_v22_chain_v2_norm.csv', encoding='utf-8-sig'))}


def get(row, key):
    ch = CH2.get(row['symbol'] + '|' + row['entry_date']) or {}
    return ch.get(key) or ''


def st(rs, wkey='_u'):
    tw = sum(r[wkey] for r in rs)
    if not tw:
        return len(rs), 0, 0, 0, 0
    p = [float(r['net_pnl_pct'] or 0) * r[wkey] for r in rs]
    avg = sum(p) / tw
    wr = sum(r[wkey] for r, v in zip(rs, p) if v > 0) / tw * 100
    pos = sum(v for v in p if v > 0)
    neg = -sum(v for v in p if v < 0)
    return len(rs), round(tw, 1), round(avg, 2), round(wr, 1), (round(pos / neg, 2) if neg else 999)


for r in rows:
    r['_u'] = 1.0

# ═══ 1. v2 语义下各桶的真实 PnL ═══
print('=== v2 链下分桶统计(等权) ===')
bk_key = 'new_breakout_kind'
sets_v2 = {
    'v2: breakout=CHoCH': [r for r in rows if 'CHoCH' in get(r, bk_key)],
    'v2: breakout=BOS': [r for r in rows if str(get(r, bk_key)).startswith('BOS')],
    'v2: trend=up': [r for r in rows if get(r, 'new_trend') == 'up'],
    'v2: trend=down': [r for r in rows if get(r, 'new_trend') == 'down'],
    'v2: trend=none': [r for r in rows if get(r, 'new_trend') not in ('up', 'down')],
}
for name, rs in sets_v2.items():
    print(f'  {name:26s}: n={st(rs)[0]:4d} avg={st(rs)[2]:+.2f} PF={st(rs)[4]}')

# 旧链的 for 对比(原combo_v22的trend/breakout)
rows_old = list(csv.DictReader(open(ROOT / 'research' / 'combo_v22_trades.csv', encoding='utf-8-sig')))
for r in rows_old:
    r['_u'] = 1.0
print('\n=== 旧链同样分桶(对照) ===')
old_sets = {
    'v1: breakout=CHoCH': [r for r in rows_old if 'CHoCH' in (r.get('breakout_kind') or '')],
    'v1: breakout=BOS': [r for r in rows_old if str(r.get('breakout_kind') or '').startswith('BOS')],
    'v1: trend=up': [r for r in rows_old if (r.get('trend_state') or '') == 'up'],
    'v1: trend=down': [r for r in rows_old if (r.get('trend_state') or '') == 'down'],
}
for name, rs in old_sets.items():
    print(f'  {name:26s}: n={st(rs)[0]:4d} avg={st(rs)[2]:+.2f} PF={st(rs)[4]}')

# ═══ 2. 微网搜索 (w_s1, w_s7) 下 v2 重加权 PF ═══
# 从 chain v2 take 新字段, 其它 S5/S6/S8-S14 权重不变 (不链相关)
# 读 v2 weights 然后再替换 s1/s7: 用除法然后乘新参数 — 不可分, 重打更干净.
# 我们依赖 R91 输出 combo_v23_shadow_v2._flags 看哪些已命中. 这里只对翻转过 s1/s7 的宏力调参似,
# 不过更简洁做法: full recompute 链无关项 + 挂新 s1/s7.

ENR = {r['symbol'] + '|' + r['entry_date']: r
       for r in csv.DictReader(open(ROOT / 'research/combo_v22_smc_full.csv', encoding='utf-8-sig'))}
import sqlite3, datetime
from core.events import classify_title
import config as CFG
conn = sqlite3.connect(CFG.ANNOUNCE_DB)
by_code = {}
for d, c, t in conn.execute("SELECT date, stock_code, title FROM announce"):
    is_ev, kind, pol, *_ = classify_title(t)
    if is_ev and pol > 0:
        by_code.setdefault(c, []).append(d)
conn.close()
IDX = __import__('json').load(open(ROOT / 'research/idx_sh000001.json', encoding='utf-8'))
def idx20(d):
    d = str(d).replace('-', '')
    j = -1
    for i in range(len(IDX) - 1, -1, -1):
        if str(IDX[i]['t']) <= d:
            j = i; break
    if j < 20:
        return None
    return (float(IDX[j]['c']) / float(IDX[j - 20]['c']) - 1) * 100


def weight_with(w_s1, w_s7):
    other = (('s4', 0.5), ('s5', 0.6), ('s6x3', 1.2), ('s6x1', 0.7),
             ('s8', 0.6), ('s9', 0.7), ('s10', 0.8), ('s11', 0.7), ('s12', 0.7), ('s13', 0.7), ('s14', 0.5))
    for r in rows:
        sy = r['symbol'] + '|' + r['entry_date']
        ch2 = CH2.get(sy) or {}
        enr = ENR.get(sy) or {}
        w = 1.0
        # s1 用 v2 CHoCH
        if 'CHoCH' in (ch2.get('new_breakout_kind') or ''):
            w *= w_s1
        if str(r.get('rank')) == '2':
            w *= 0.5
        try:
            if float(r.get('risk_pct') or 0) < 5:
                w *= 0.6
        except Exception:
            pass
        if r.get('src') == 'EVENT':
            code = r['symbol'].split('_')[0].split('.')[0]
            d0 = datetime.datetime.strptime(r['entry_date'], '%Y%m%d')
            lo = (d0 - datetime.timedelta(days=90)).strftime('%Y-%m-%d')
            hi = d0.strftime('%Y-%m-%d')
            n_ev = sum(1 for a in by_code.get(code, []) if lo <= a <= hi)
            if n_ev >= 3:
                w *= 1.2
            elif n_ev <= 1:
                w *= 0.7
        # s7 v2
        if (ch2.get('new_trend') or '') == 'up':
            w *= w_s7
        if enr:
            if enr.get('sweep_dir') == 'bear':
                w *= 0.6
            try:
                if float(enr.get('dist_to_bsl') or 99) < 5:
                    w *= 0.7
            except Exception:
                pass
            if str(enr.get('in_ob')) == 'True':
                w *= 0.8
            try:
                if enr.get('mss_dir') == 'bull' and int(enr.get('mss_bars_ago') or 999) <= 2:
                    w *= 0.7
            except Exception:
                pass
            if str(enr.get('in_ote')) == 'True':
                w *= 0.7
        try:
            rc = __import__('json').loads(r.get('rank_components') or '{}')
            if rc.get('vr2') == 1 or rc.get('vol_cont') == 1:
                w *= 0.7
        except Exception:
            pass
        m20 = idx20(r['entry_date'])
        if m20 is not None and m20 < -2:
            w *= 0.5
        r['_w_'] = w
    return st(rows, '_w_')


print('\n=== (w_s1, w_s7) 微网 — v2 链语义下总 PF ===')
print(f"{'w_s1':>5} {'w_s7':>5} {'avg%':>7} {'PF':>6}")
grid = []
for w1 in (0.4, 0.5, 0.6, 0.7, 0.8):
    for w7 in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
        s = weight_with(w1, w7)
        grid.append((w1, w7, s))
        print(f"{w1:5.2f} {w7:5.2f} {s[2]:7.2f} {s[4]:6.2f}")
best = max(grid, key=lambda t: t[2][4])
print(f'\n最优: w_s1={best[0]} w_s7={best[1]} avg={best[2][2]:+.2f} PF={best[2][4]}')
print('(参考: v1链 v24 = avg 5.89 PF 5.89; 等权 = 4.07/3.36)')
