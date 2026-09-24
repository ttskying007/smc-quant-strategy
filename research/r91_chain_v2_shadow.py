# -*- coding: utf-8 -*-
r"""R91 — v24 影子用 chain v2 重打栈 (s1/s7 两枚受链字段影响)
gen_v23_shadow.py 不动 (保生产), 这份是纯研究对照.
输出 combo_v23_shadow_v2.csv: v23_weight(=旧 formula) + v23_weight_v2(=v2 chain 重打) + flip 标记
"""
import csv, os, json, sqlite3, sys
from collections import defaultdict
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.stdout = __import__('io').TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import config as CFG
from core.events import classify_title

W_CHOCH = 0.5
W_RANK2 = 0.5
W_RISK_LT5 = 0.6
W_WHALE_3PLUS = 1.2
W_WHALE_ONCE = 0.7
W_UP_TREND = 0.7
W_SWEEP_BEAR = 0.6
W_BSL_TIGHT = 0.7
W_IN_OB = 0.8
W_MSS_BULL_FRESH = 0.7
W_IN_OTE = 0.7
W_RANK_VR2_VC = 0.7
W_MKT_WEAK = 0.5

# ── whale 计数 + idx20 同旧版 ──
def whale_counts(rows):
    conn = sqlite3.connect(CFG.ANNOUNCE_DB)
    by_code = defaultdict(list)
    for d, c, t in conn.execute("SELECT date, stock_code, title FROM announce"):
        is_ev, kind, pol, amt, pct = classify_title(t)
        if is_ev and pol > 0:
            by_code[c].append((d, kind))
    m = {}
    for r in rows:
        code = r['symbol'].split('_')[0].split('.')[0]
        d0 = datetime.strptime(r['entry_date'], '%Y%m%d')
        lo, hi = (d0 - timedelta(days=90)).strftime('%Y-%m-%d'), d0.strftime('%Y-%m-%d')
        m[r['symbol'] + '|' + r['entry_date']] = sum(1 for a in by_code.get(code, []) if lo <= a[0] <= hi)
    return m

IDX = json.load(open(os.path.join(ROOT, 'idx_sh000001.json'), encoding='utf-8'))
def idx20(d):
    d = str(d).replace('-', '')
    j = -1
    for i in range(len(IDX) - 1, -1, -1):
        if str(IDX[i]['t']) <= d:
            j = i
            break
    if j < 20:
        return None
    return (float(IDX[j]['c']) / float(IDX[j - 20]['c']) - 1) * 100

ENR = {r['symbol'] + '|' + r['entry_date']: r
       for r in csv.DictReader(open(os.path.join(ROOT, 'combo_v22_smc_full.csv'), encoding='utf-8-sig'))}
CH2 = {r['symbol'] + '|' + r['entry_date']: r
       for r in csv.DictReader(open(os.path.join(ROOT, 'combo_v22_chain_v2_norm.csv'), encoding='utf-8-sig'))}

rows = list(csv.DictReader(open(os.path.join(ROOT, 'combo_v22_trades.csv'), encoding='utf-8-sig')))
whale = whale_counts(rows)


def compute(track):
    """track: 'v1' 用原链字段 / 'v2' 用 v2 链字段"""
    for r in rows:
        r['_w'] = 1.0
        r['_flags'] = []
        bk = 'CHoCH' in ((r.get('breakout_kind') or '') if track == 'v1' else (CH2.get(r['symbol'] + '|' + r['entry_date'], {}).get('new_breakout_kind') or ''))
        if bk:
            r['_w'] *= W_CHOCH; r['_flags'].append('s1')
        if str(r.get('rank')) == '2':
            r['_w'] *= W_RANK2; r['_flags'].append('s4')
        try:
            if float(r.get('risk_pct') or 0) < 5:
                r['_w'] *= W_RISK_LT5; r['_flags'].append('s5')
        except Exception:
            pass
        if r.get('src') == 'EVENT':
            n_ev = whale.get(r['symbol'] + '|' + r['entry_date'], 1)
            if n_ev >= 3:
                r['_w'] *= W_WHALE_3PLUS; r['_flags'].append('s6x3')
            elif n_ev <= 1:
                r['_w'] *= W_WHALE_ONCE; r['_flags'].append('s6x1')
        trend = (r.get('trend_state') or '') if track == 'v1' else (CH2.get(r['symbol'] + '|' + r['entry_date'], {}).get('new_trend') or '')
        if trend == 'up':
            r['_w'] *= W_UP_TREND; r['_flags'].append('s7')
        enr = ENR.get(r['symbol'] + '|' + r['entry_date'])
        if enr:
            if enr.get('sweep_dir') == 'bear':
                r['_w'] *= W_SWEEP_BEAR; r['_flags'].append('s8')
            try:
                if float(enr.get('dist_to_bsl') or 99) < 5:
                    r['_w'] *= W_BSL_TIGHT; r['_flags'].append('s9')
            except Exception:
                pass
            if str(enr.get('in_ob')) == 'True':
                r['_w'] *= W_IN_OB; r['_flags'].append('s10')
            try:
                if enr.get('mss_dir') == 'bull' and int(enr.get('mss_bars_ago') or 999) <= 2:
                    r['_w'] *= W_MSS_BULL_FRESH; r['_flags'].append('s11')
            except Exception:
                pass
            if str(enr.get('in_ote')) == 'True':
                r['_w'] *= W_IN_OTE; r['_flags'].append('s12')
        try:
            rc = json.loads(r.get('rank_components') or '{}')
            if rc.get('vr2') == 1 or rc.get('vol_cont') == 1:
                r['_w'] *= W_RANK_VR2_VC; r['_flags'].append('s13')
        except Exception:
            pass
        m20 = idx20(r['entry_date'])
        if m20 is not None and m20 < -2:
            r['_w'] *= W_MKT_WEAK; r['_flags'].append('s14')


def stat(rs, wkey='_w'):
    tw = sum(r[wkey] for r in rs)
    p = [float(r['net_pnl_pct'] or 0) * r[wkey] for r in rs]
    avg = sum(p) / tw
    wr = sum(r[wkey] for r, v in zip(rs, p) if v > 0) / tw * 100
    pos = sum(v for v in p if v > 0)
    neg = -sum(v for v in p if v < 0)
    return len(rs), round(tw, 1), round(avg, 2), round(wr, 1), round(pos / neg, 2) if neg else 999


compute('v1')
for r in rows:
    r['v23_weight_v1'] = r['_w']
_STATS_V1 = stat(rows, 'v23_weight_v1')
compute('v2')
for r in rows:
    r['v23_weight_v2'] = r['_w']
    r['weight_flip'] = abs(r['_w'] - r['v23_weight_v1']) > 1e-6

# 写对照 CSV
out = os.path.join(ROOT, 'combo_v23_shadow_v2.csv')
sec_cols = ['symbol', 'entry_date', 'src', 'net_pnl_pct', 'v23_weight_v1', 'v23_weight_v2', 'weight_flip', '_flags']
with open(out, 'w', encoding='utf-8-sig', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=sec_cols, extrasaction='ignore')
    w.writeheader()
    w.writerows(rows)
print(f'输出 {os.path.basename(out)} 翻转腿数 {sum(1 for r in rows if r.get("weight_flip"))}')

# 汇总
print(f'翻转腿数 {sum(1 for r in rows if r.get("weight_flip"))}')
# 真等权等差(不带任何权): 先 set _w=1
for r in rows:
    r['_unit'] = 1.0
print(f" baseline(等权): {stat(rows, '_unit')} (n/Σw/avg%/WR/PF)")
print(f" v23_weight_v1(原链): {_STATS_V1}")
print(f" v23_weight_v2(v2链): {stat(rows, 'v23_weight_v2')}")

# 翻转腿 vs 未翻转腿
rs_fl = [r for r in rows if r.get('weight_flip')]
rs_ok = [r for r in rows if not r.get('weight_flip')]
print(f'\n未翻转(占 {len(rs_ok)}): 等权 {stat(rs_ok, "_unit")}')
print(f'翻转腿 {len(rs_fl)}: 等权 {stat(rs_fl, "_unit")}')
if rs_fl:
    print(f'翻转腿 v2 加权: {stat(rs_fl, "v23_weight_v2")}')

# 逐年
for y in ('2023', '2024', '2025', '2026'):
    rs = [r for r in rows if r['entry_date'][:4] == y]
    if rs:
        base = stat(rs, '_unit')
        v1 = stat(rs, 'v23_weight_v1')
        v2 = stat(rs, 'v23_weight_v2')
        print(f"  {y}: 等权 {base[2]}%/PF{base[4]} | v1 {v1[2]}%/PF{v1[4]} | v2 {v2[2]}%/PF{v2[4]}")
