# -*- coding: utf-8 -*-
r"""R94 终版: v2 全链 (chain v2 + enrich v2) × R93 狠打手术包 评估对照 v24 v1 (PF5.89)

路径: v2 chain 打 s1/s7 + s18/s19/s20 R93 重打; v2 enrich 打 s8-s12; s4/s5/s6/s13/s14 不变.
权衡: 狠打版 (s18=s19=s20 ×0.35, s15 ×0.5, s16 ×0.6, s21 ×0.4, s17 ×1.1 不变)
"""
import csv, sys, io, json, sqlite3, datetime
from pathlib import Path
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'E:\test\smc_project\research')
ROOT = Path(r'E:\test\smc_project')

import config as CFG
from core.events import classify_title

CH2 = {r['symbol'] + '|' + r['entry_date']: r
       for r in csv.DictReader(open(ROOT / 'research/combo_v22_chain_v2_norm.csv', encoding='utf-8-sig'))}
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

def st(rs, wk):
    tw = sum(r[wk] for r in rs)
    if not tw:
        return (0, 0, 0, 0, 0)
    p = [float(r['net_pnl_pct'] or 0) * r[wk] for r in rs]
    avg = sum(p) / tw
    wr = sum(r[wk] for r, v in zip(rs, p) if v > 0) / tw * 100
    pos = sum(v for v in p if v > 0)
    neg = -sum(v for v in p if v < 0)
    pf = pos / neg if neg else 999
    return len(rs), round(tw, 1), round(avg, 2), round(wr, 1), round(pf, 2)


def run(w_s1=0.4, w_s7=0.5, w_hench=(0.35, 0.35, 0.35, 0.4, 0.5, 0.6, 1.1)):
    """w_hench = (s18, s19, s20, s21, s15, s16, s17)"""
    for r in rows:
        sy = r['symbol'] + '|' + r['entry_date']
        ch2 = CH2.get(sy) or {}
        enr = ENR2.get(sy) or {}
        w = 1.0
        bk = ch2.get('new_breakout_kind') or ''
        # s1 v2
        if 'CHoCH' in bk:
            w *= w_s1
        if str(r.get('rank')) == '2':
            w *= 0.5
        try:
            if float(r.get('risk_pct') or 0) < 5:
                w *= 0.6
        except Exception:
            pass
        if r.get('src') == 'EVENT':
            code = r['symbol'].split('.')[0]
            d0 = datetime.datetime.strptime(r['entry_date'], '%Y%m%d')
            lo = (d0 - datetime.timedelta(days=90)).strftime('%Y-%m-%d')
            hi = d0.strftime('%Y-%m-%d')
            n_ev = sum(1 for a in BY.get(code, []) if lo <= a <= hi)
            if n_ev >= 3:
                w *= 1.2
            elif n_ev <= 1:
                w *= 0.7
        # s7 v2
        if (ch2.get('new_trend') or '') == 'up':
            w *= w_s7
        # s8-s12 用 v2 enrich
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
            rc = json.loads(r.get('rank_components') or '{}')
            if rc.get('vr2') == 1 or rc.get('vol_cont') == 1:
                w *= 0.7
        except Exception:
            pass
        m20 = idx20(r['entry_date'])
        if m20 is not None and m20 < -2:
            w *= 0.5
        # s15-s21 R93 狠打
        rt_f = (ch2.get('new_retrace_state') or '')
        if bk == 'CHoCH↑' and rt_f == 'no_retrace':
            w *= w_hench[0]
        if bk == 'CHoCH↑' and rt_f == 'retrace_fail':
            w *= w_hench[1]
        if bk == 'CHoCH↓' and rt_f == 'retrace_fail':
            w *= w_hench[2]
        if bk == 'BOS↑' and rt_f == 'retrace_fail':
            w *= w_hench[3]
        if bk in ('BOS↓', 'CHoCH↓') and rt_f == 'retrace_fail':
            w *= w_hench[4]
        if (ch2.get('new_trend') or '') == 'up' and rt_f == 'no_retrace':
            w *= w_hench[5]
        if (ch2.get('new_trend') or '') == 'down' and rt_f == 'retrace_ok':
            w *= w_hench[6]
        r['_w'] = w
    return st(rows, '_w')


print('=== v24 v2 全链+新手术表 ===')
print(f"{'变体':<40s} {'Σw':>8} {'avg%':>7} {'WR%':>6} {'PF':>6}")
variants = [
    ('v1原版 (s1=0.5 s7=0.7 + s8-s14 v1 enrich)', 0.5, 0.7, (0.5, 0.5, 0.5, 0.6, 0.6, 0.7, 1.1)),  # 注意这个变体其实是v2 语义重出。不是原v1.
    ('R92最优 (0.4/0.5, 无新伤桶)', 0.4, 0.5, (1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.1)),
    ('R93狠打 (0.4/0.5 +伤桶0.35/0.35/0.35)', 0.4, 0.5, (0.35, 0.35, 0.35, 0.5, 0.5, 0.6, 1.1)),
    ('R93狠打+轻 s21', 0.4, 0.5, (0.35, 0.35, 0.35, 0.4, 0.5, 0.6, 1.1)),
    ('重狠: 伤桶全×0.25', 0.35, 0.4, (0.25, 0.25, 0.25, 0.4, 0.45, 0.5, 1.15)),
]
for name, ws1, ws7, wh in variants:
    s = run(ws1, ws7, wh)
    print(f"{name:<40s} {s[1]:>8.1f} {s[2]:>7.2f} {s[3]:>6.1f} {s[4]:>6.2f}")
print('(基线: 等权 4.07/64.0/3.36; v1链v24 +5.89/74.2/5.89)')

# 导出最优变体"R93狠打+轻s21"的影子 — combo_v23_shadow_v3.csv (生产候选观察对象)
run(0.4, 0.5, (0.35, 0.35, 0.35, 0.4, 0.5, 0.6, 1.1))
outp = ROOT / 'research/combo_v23_shadow_v3.csv'
cols = ['symbol', 'entry_date', 'src', 'net_pnl_pct', 'tp', 'sl', '_w']
with open(outp, 'w', encoding='utf-8-sig', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=cols, extrasaction='ignore')
    w.writeheader()
    w.writerows(rows)
print(f'\n已写 {outp.name} (1858 腿 v2 shadow 狠打+轻s21 变体)')
