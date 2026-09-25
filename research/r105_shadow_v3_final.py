# -*- coding: utf-8 -*-
r"""R105 — combo_v23_shadow_v3.csv 升级为终版 (R94狠打 + R101 s22/s23 0.15)

前端 /kline 腿表与 /audit 影子池 用的是 combo_v23_shadow_v3.csv (由 R94 推出).
R101 之后 v2 公式略动 —— 现在重出以便界面和 paper_sim._v23v2_of 对齐.
输出覆盖同一文件, 字段不变, 值更新.
"""
import csv, sys, io, json, sqlite3, datetime
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'E:\test\smc_project\research')
ROOT = Path(r'E:\test\smc_project')

import config as CFG
from core.events import classify_title

CH2 = {r['symbol'] + '|' + r['entry_date']: r
       for r in csv.DictReader(open(ROOT / 'research/combo_v22_chain_v2_hhll.csv', encoding='utf-8-sig'))}
ENR2 = {r['symbol'] + '|' + r['entry_date']: r
        for r in csv.DictReader(open(ROOT / 'research/combo_v22_smc_full_v2.csv', encoding='utf-8-sig'))}
# R117: 活跃磁区因子表 (r117_eq_magnet_factor.py 产出)
EQM = {r['symbol'] + '|' + r['entry_date']: r
       for r in csv.DictReader(open(ROOT / 'research/combo_v22_eq_magnet.csv', encoding='utf-8-sig'))}
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

def enr_w(r, w, flags):
    enr = ENR2.get(r['symbol'] + '|' + r['entry_date'])
    if not enr:
        return w
    if enr.get('sweep_dir') == 'bear':
        w *= 0.6; flags.append('s8_sweep_bear')
    try:
        if float(enr.get('dist_to_bsl') or 99) < 5:
            w *= 0.7; flags.append('s9_bsl_tight')
    except Exception:
        pass
    if str(enr.get('in_ob')) == 'True':
        w *= 0.8; flags.append('s10_in_ob')
    try:
        if enr.get('mss_dir') == 'bull' and int(enr.get('mss_bars_ago') or 999) <= 2:
            w *= 0.7; flags.append('s11_mss_bull_fresh')
    except Exception:
        pass
    if str(enr.get('in_ote')) == 'True':
        w *= 0.7; flags.append('s12_in_ote')
    return w


def w_final(r):
    ch2 = CH2.get(r['symbol'] + '|' + r['entry_date']) or {}
    w, flags = 1.0, []
    bk = ch2.get('breakout_kind_v2') or ''
    rt = ch2.get('retrace_state_v2') or ''
    tr = ch2.get('trend_v2') or ''
    sst = ch2.get('structure_state') or ''
    # R117: 活跃磁区因子 — 入场价1%内下方有未扫EQL(SL扫描风险区) → 毒性桶 s24
    eqm = EQM.get(r['symbol'] + '|' + r['entry_date'])
    if eqm and eqm.get('eq_near_active') == 'True':
        try:
            _eql_n = int(eqm.get('eql_active_n') or 0)
            _eqh_n = int(eqm.get('eqh_active_n') or 0)
        except Exception:
            _eql_n = _eqh_n = 0
        if _eql_n >= 1:
            w *= 0.15; flags.append('s24_eql_risk')
        elif _eqh_n >= 1:
            w *= 1.0; flags.append('s24_eqh_target')  # 上方磁吸目标: 记录不加权
    if 'CHoCH' in bk:
        w *= 0.4; flags.append(f's1v2_{bk}')
    if tr == 'up':
        w *= 0.5; flags.append('s7v2_up')
    if bk == 'CHoCH↑' and rt == 'no_retrace':
        w *= 0.35; flags.append('s18')
    if bk == 'CHoCH↑' and rt == 'retrace_fail':
        w *= 0.35; flags.append('s19')
    if bk == 'CHoCH↓' and rt == 'retrace_fail':
        w *= 0.35; flags.append('s20')
    if bk in ('BOS↓', 'CHoCH↓') and rt == 'retrace_fail':
        w *= 0.5; flags.append('s15')
    if bk == 'BOS↑' and rt == 'retrace_fail':
        w *= 0.4; flags.append('s21')
    if tr == 'up' and rt == 'no_retrace':
        w *= 0.6; flags.append('s16')
    if tr == 'down' and rt == 'retrace_ok':
        w *= 1.1; flags.append('s17')
    if sst.startswith('bull') and bk == 'BOS↑' and rt == 'retrace_ok':
        w *= 0.15; flags.append('s22')
    if sst.startswith('bear') and bk == 'CHoCH↑' and rt == 'no_retrace':
        w *= 0.15; flags.append('s23')
    w = enr_w(r, w, flags)
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
    return w, flags


out_rows = []
for r in rows:
    w, flags = w_final(r)
    out_rows.append({
        'symbol': r['symbol'],
        'entry_date': r['entry_date'],
        'src': r['src'],
        'net_pnl_pct': r['net_pnl_pct'],
        'tp': r.get('tp'),
        'sl': r.get('sl'),
        'v23_weight_v2': round(w, 4),
        'v23_flags_v2': ';'.join(flags) if flags else 'none',
    })

outp = ROOT / 'research/combo_v23_shadow_v3.csv'
with open(outp, 'w', encoding='utf-8-sig', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=['symbol', 'entry_date', 'src', 'net_pnl_pct', 'tp', 'sl',
                                       'v23_weight_v2', 'v23_flags_v2'])
    w.writeheader()
    w.writerows(out_rows)
print(f'升级 {outp.name}: 1858 腿 (s22/s23 终版)')

# 当前r96账本二次回填 (v2 对比要新)
import shutil, os
shutil.copy(ROOT / 'research/paper_ledger.json', ROOT / 'research/paper_ledger.bak_r105.json')
print('备份完成 paper_ledger.bak_r105.json')
