# -*- coding: utf-8 -*-
r"""R98 — v2 全链狠打公式的 OOS 验证 (防过拟合墙)

把 1858 腿按时间分:
  fit = entry_date <= 20251231  (拟合段)
  oos = entry_date >= 20260101  (2026 新行情段, 纯前瞻)
比较 4 个策略的 PF/avg/WR:
  base等权 / v24 v1链 / v24 v2链狠打 / v2链轻打(s18-s20=0.5)
判定标准: 狠打版在 OOS 段 PF 必须显著 > v1, 否则狠打是样本内拟合产物, 打回轻打.
"""
import csv, sys, io, json, sqlite3, datetime
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'E:\test\smc_project\research')
ROOT = Path(r'E:\test\smc_project')

import config as CFG
from core.events import classify_title

CH2 = {r['symbol'] + '|' + r['entry_date']: r
       for r in csv.DictReader(open(ROOT / 'research/combo_v22_chain_v2_norm.csv', encoding='utf-8-sig'))}
ENR1 = {r['symbol'] + '|' + r['entry_date']: r
        for r in csv.DictReader(open(ROOT / 'research/combo_v22_smc_full.csv', encoding='utf-8-sig'))}
ENR2 = {r['symbol'] + '|' + r['entry_date']: r
        for r in csv.DictReader(open(ROOT / 'research/combo_v22_smc_full_v2.csv', encoding='utf-8-sig'))}
rows = list(csv.DictReader(open(ROOT / 'research/combo_v22_trades.csv', encoding='utf-8-sig')))

conn = sqlite3.connect(CFG.ANNOUNCE_DB)
BY = {}
for d, c, t in conn.execute("SELECT date, stock_code, title FROM announce"):
    is_ev, knd, pol, *_ = classify_title(t)
    if is_ev and pol > 0:
        BY.setdefault(c, []).append(d)
conn.close()
IDX = json.load(open(ROOT / 'research/idx_sh000001.json', encoding='utf-8'))

def idx20(d):
    d = str(d).replace('-', '')
    j = -1
    for i in range(len(IDX) - 1, -1, -1):
        if str(IDX[i]['t']) <= d:
            j = i; break
    if j < 20:
        return None
    return (float(IDX[j]['c']) / float(IDX[j - 20]['c']) - 1) * 100


def base_common(r, w, flags):
    """s4/s5/s6/s13/s14 — 与版本无关"""
    if str(r.get('rank')) == '2':
        w *= 0.5; flags.append('s4')
    try:
        if float(r.get('risk_pct') or 0) < 5:
            w *= 0.6; flags.append('s5')
    except Exception:
        pass
    if r.get('src') == 'EVENT':
        code = r['symbol'].split('.')[0]
        d0 = datetime.datetime.strptime(r['entry_date'], '%Y%m%d')
        lo = (d0 - datetime.timedelta(days=90)).strftime('%Y-%m-%d')
        hi = d0.strftime('%Y-%m-%d')
        n_ev = sum(1 for a in BY.get(code, []) if lo <= a <= hi)
        if n_ev >= 3:
            w *= 1.2; flags.append('s6x3')
        elif n_ev <= 1:
            w *= 0.7; flags.append('s6x1')
    try:
        rc = json.loads(r.get('rank_components') or '{}')
        if rc.get('vr2') == 1 or rc.get('vol_cont') == 1:
            w *= 0.7; flags.append('s13')
    except Exception:
        pass
    m20 = idx20(r['entry_date'])
    if m20 is not None and m20 < -2:
        w *= 0.5; flags.append('s14')
    return w


def w_v1(r):
    w, f = 1.0, []
    if 'CHoCH' in (r.get('breakout_kind') or ''):
        w *= 0.5; f.append('s1')
    if (r.get('trend_state') or '') == 'up':
        w *= 0.7; f.append('s7')
    return base_common(r, w, f)


def enr_w(enr, w, flags):
    if not enr:
        return w
    if enr.get('sweep_dir') == 'bear':
        w *= 0.6; flags.append('s8')
    try:
        if float(enr.get('dist_to_bsl') or 99) < 5:
            w *= 0.7; flags.append('s9')
    except Exception:
        pass
    if str(enr.get('in_ob')) == 'True':
        w *= 0.8; flags.append('s10')
    try:
        if enr.get('mss_dir') == 'bull' and int(enr.get('mss_bars_ago') or 999) <= 2:
            w *= 0.7; flags.append('s11')
    except Exception:
        pass
    if str(enr.get('in_ote')) == 'True':
        w *= 0.7; flags.append('s12')
    return w


def w_v1_full(r):
    w = w_v1(r)
    return enr_w(ENR1.get(r['symbol'] + '|' + r['entry_date']), w, [])


def w_v2_hard(r):
    """R94 狠打: s1=0.4 s7=0.5 s18-20=0.35 s15=0.5 s16=0.6 s17=1.1 s21=0.4"""
    ch2 = CH2.get(r['symbol'] + '|' + r['entry_date']) or {}
    w, f = 1.0, []
    bk = ch2.get('new_breakout_kind') or ''
    rt = ch2.get('new_retrace_state') or ''
    tr = ch2.get('new_trend') or ''
    if 'CHoCH' in bk:
        w *= 0.4; f.append('s1v2')
    if tr == 'up':
        w *= 0.5; f.append('s7v2')
    if bk == 'CHoCH↑' and rt == 'no_retrace':
        w *= 0.35; f.append('s18')
    if bk == 'CHoCH↑' and rt == 'retrace_fail':
        w *= 0.35; f.append('s19')
    if bk == 'CHoCH↓' and rt == 'retrace_fail':
        w *= 0.35; f.append('s20')
    if bk == 'BOS↑' and rt == 'retrace_fail':
        w *= 0.4; f.append('s21')
    if bk in ('BOS↓', 'CHoCH↓') and rt == 'retrace_fail':
        w *= 0.5; f.append('s15')
    if tr == 'up' and rt == 'no_retrace':
        w *= 0.6; f.append('s16')
    if tr == 'down' and rt == 'retrace_ok':
        w *= 1.1; f.append('s17')
    w = enr_w(ENR2.get(r['symbol'] + '|' + r['entry_date']), w, f)
    return base_common(r, w, f)


def w_v2_soft(r):
    """v2 轻打: s1=0.5 s7=0.7 伤桶全 0.5"""
    ch2 = CH2.get(r['symbol'] + '|' + r['entry_date']) or {}
    w, f = 1.0, []
    bk = ch2.get('new_breakout_kind') or ''
    rt = ch2.get('new_retrace_state') or ''
    tr = ch2.get('new_trend') or ''
    if 'CHoCH' in bk:
        w *= 0.5; f.append('s1v2')
    if tr == 'up':
        w *= 0.7; f.append('s7v2')
    for br, rr, ww in (('CHoCH↑', 'no_retrace', 0.5), ('CHoCH↑', 'retrace_fail', 0.5),
                       ('CHoCH↓', 'retrace_fail', 0.5), ('BOS↑', 'retrace_fail', 0.5)):
        if bk == br and rt == rr:
            w *= ww
    if bk in ('BOS↓', 'CHoCH↓') and rt == 'retrace_fail':
        w *= 0.6
    if tr == 'up' and rt == 'no_retrace':
        w *= 0.7
    if tr == 'down' and rt == 'retrace_ok':
        w *= 1.1
    w = enr_w(ENR2.get(r['symbol'] + '|' + r['entry_date']), w, f)
    return base_common(r, w, f)


def st(rs, wk):
    tw = sum(r[wk] for r in rs)
    if not tw:
        return (0, 0, 0, 0, 0)
    p = [float(r['net_pnl_pct'] or 0) * r[wk] for r in rs]
    avg = sum(p) / tw
    wr = sum(r[wk] for r, v in zip(rs, p) if v > 0) / tw * 100
    pos = sum(v for v in p if v > 0)
    neg = -sum(v for v in p if v < 0)
    return len(rs), round(tw, 1), round(avg, 2), round(wr, 1), (round(pos / neg, 2) if neg else 999)


for r in rows:
    r['_w0'] = 1.0
    r['_w1'] = w_v1_full(r)
    r['_w2h'] = w_v2_hard(r)
    r['_w2s'] = w_v2_soft(r)

fit = [r for r in rows if r['entry_date'] <= '20251231']
oos = [r for r in rows if r['entry_date'] >= '20260101']
print(f'fit段 n={len(fit)}  oos段 n={len(oos)}')
print(f"{'策略':<24s} {'fit avg':>8} {'fit PF':>7} | {'oos avg':>8} {'oos PF':>7}")
for name, wk in (('等权', '_w0'), ('v24 v1 链', '_w1'), ('v2 狠打(R94公式)', '_w2h'), ('v2 轻打(0.5档)', '_w2s')):
    sf = st(fit, wk)
    so = st(oos, wk)
    print(f"{name:<24s} {sf[2]:>8.2f} {sf[4]:>7.2f} | {so[2]:>8.2f} {so[4]:>7.2f}  (oos n={so[0]})")
