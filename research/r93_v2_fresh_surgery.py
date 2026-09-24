# -*- coding: utf-8 -*-
r"""R93 — 在 v2 自适应链下重新发现手术候选 (不拿 v1 的棺材钉钉子)

桶位统计维度 (all from v2 chain_json):
  1. breakout 方向 × 是否 CHoCH
  2. retrace_state
  3. breakout→entry 的时间距离 (推算 breakout date vs entry_date bar non-business estimate)
  4. 最后事件方向 (bear 即breakdown breakthrough, bull 即 breakout-up)
  5. breakout × retrace 交互块

筛选门槛: n>=50 且 PF < 2.5 且 avg < 全局(4.07) → 下减重重 (×w_grid in 0.4..0.9)
调参后 v2-v24' 整体 PF 目标 ≥ 5.1 (v1=5.89 参考)
"""
import csv, sys, io, json
from pathlib import Path
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(r'E:\test\smc_project')

rows = list(csv.DictReader(open(ROOT / 'research/combo_v22_chain_v2_norm.csv', encoding='utf-8-sig')))
print(f'legs: {len(rows)}')


def st(rs):
    n = len(rs)
    if not n:
        return (0, 0, 0, 0)
    p = [float(r['pnl'] or 0) for r in rs]
    avg = sum(p) / n
    wr = sum(1 for v in p if v > 0) / n * 100
    pos = sum(v for v in p if v > 0)
    neg = -sum(v for v in p if v < 0)
    pf = pos / neg if neg else 999
    return (n, round(avg, 2), round(wr, 1), round(pf, 2))


def stw(rs):
    # 加权平均以 r['_w_'] 为权重
    tw = sum(r.get('_w_', 1.0) for r in rs)
    if not tw:
        return (0, 0, 0, 0)
    p = [float(r['pnl'] or 0) * r.get('_w_', 1.0) for r in rs]
    avg = sum(p) / tw
    wr = sum(r.get('_w_', 1.0) for r, v in zip(rs, p) if v > 0) / tw * 100
    pos = sum(v for v in p if v > 0)
    neg = -sum(v for v in p if v < 0)
    pf = pos / neg if neg else 999
    return (len(rs), round(tw, 1), round(avg, 2), round(wr, 1), round(pf, 2))


GLOBAL = st(rows)
print(f'全局: n={GLOBAL[0]} avg={GLOBAL[1]} WR={GLOBAL[2]} PF={GLOBAL[3]}')

# ═══ A. breakout kind × retrace 交互 (主机会： 原 R70 成功路径) ═══
print('\n=== A. breakout_kind × retrace_state (v2) ===')
table = defaultdict(list)
for r in rows:
    key = (r['new_breakout_kind'] or '-', r['new_retrace_state'] or '-')
    table[key].append(r)
for k, rs in sorted(table.items(), key=lambda kv: -len(kv[1])):
    s = st(rs)
    if s[0] >= 10:
        mark = ' ⚠候选' if (s[0] >= 50 and s[3] < 2.5 and s[1] < GLOBAL[1] - 0.5) else ''
        print(f"  {k[0]:10s} × {k[1]:12s}: n={s[0]:4d} avg={s[1]:+6.2f} WR={s[2]:5.1f} PF={s[3]:6.2f}{mark}")

# ═══ B. 纯 last_event 方向（含无事件） ═══
print('\n=== B. last_event (v2) ===')
for ev in ('BOS↑', 'BOS↓', 'CHoCH↑', 'CHoCH↓', '-'):
    rs = [r for r in rows if (r['new_last_event'] or '-') == ev]
    if len(rs) >= 10:
        s = st(rs)
        print(f"  {ev:8s}: n={s[0]:4d} avg={s[1]:+6.2f} WR={s[2]:5.1f} PF={s[3]:6.2f}")

# ═══ C. new_breakout 陈旧度: entry - breakout 交易日差近似 (t count diff) ═══
def trad_gap(a, b):
    """近似交易日差（跳过语义， 用 count 简单制）"""
    try:
        if not a or not b:
            return None
        ya, ma, da = int(a[:4]), int(a[4:6]), int(a[6:8])
        yb, mb, db = int(b[:4]), int(b[4:6]), int(b[6:8])
        import datetime
        return (datetime.datetime(ya, ma, da) - datetime.datetime(yb, mb, db)).days
    except Exception:
        return None

print('\n=== C. breakout→entry 差景 (v2) ===')
for name, lo, hi in (('<7天', 0, 7), ('7-21天', 7, 21), ('21-60天', 21, 60), ('>60天', 61, 999)):
    rs = [r for r in rows if (lambda g: (g is not None and lo <= g < hi))(trad_gap(r['entry_date'], r['new_breakout_date']))]
    if len(rs) >= 10:
        s = st(rs)
        print(f"  {name:8s}: n={s[0]:4d} avg={s[1]:+6.2f} WR={s[2]:5.1f} PF={s[3]:6.2f}")

# ═══ D. 候选组合： 在 v2 链完网搜一点 (w_s1' 重启变成两个: breakout-方向+ retrace-fail) ═══
# 对每腿预标机 "learner":
for r in rows:
    bk = r['new_breakout_kind'] or ''
    r['_v2_choch'] = 1 if 'CHoCH' in bk else 0
    r['_v2_bos_down'] = 1 if bk in ('BOS↓', 'CHoCH↓') else 0
    r['_v2_retrace_fail'] = 1 if r['new_retrace_state'] == 'retrace_fail' else 0
    r['_v2_no_retrace'] = 1 if r['new_retrace_state'] == 'no_retrace' else 0
    r['_v2_trend_up'] = 1 if r['new_trend'] == 'up' else 0
    r['_v2_trend_down'] = 1 if r['new_trend'] == 'down' else 0

cand_defs = {
    's1v2_choch': lambda r: r['_v2_choch'],
    's15_bosdown_retrace_fail': lambda r: r['_v2_bos_down'] and r['_v2_retrace_fail'],
    's16_up_no_retrace': lambda r: r['_v2_trend_up'] and r['_v2_no_retrace'],
    's17_down_retrace_ok': lambda r: r['_v2_trend_down'] and r['new_retrace_state'] == 'retrace_ok',
    's18_chochup_noret': lambda r: (r['new_breakout_kind'] == 'CHoCH↑') and r['_v2_no_retrace'],
    's19_chochup_retfail': lambda r: (r['new_breakout_kind'] == 'CHoCH↑') and r['_v2_retrace_fail'],
    's20_chochdown_retfail': lambda r: (r['new_breakout_kind'] == 'CHoCH↓') and r['_v2_retrace_fail'],
    's21_bosup_retfail': lambda r: (r['new_breakout_kind'] == 'BOS↑') and r['_v2_retrace_fail'],
}
print('\n=== D. 候选单独桶 (等权， 交集不限) ===')
for name, fn in cand_defs.items():
    rs = [r for r in rows if fn(r)]
    if len(rs) >= 10:
        s = st(rs)
        print(f"  {name:26s}: n={s[0]:4d} avg={s[1]:+6.2f} WR={s[2]:5.1f} PF={s[3]:6.2f}")

# ═══ E. 链无关手术存在 (S4-S14) 全知, 约可迈 v2 surgery 新增包 ═══
# 同 R91: 其他 12 个手术 (非 s1/s7) 固定保持改 w
# 然后对 (choch×0.x, up×0.x = v2 s1/s7 的) 微网 + 追加 新s15/s16

import json, datetime, sqlite3
ERN = {r['symbol'] + '|' + r['entry_date']: r for r in csv.DictReader(open(ROOT / 'research/combo_v22_smc_full.csv', encoding='utf-8-sig'))}
sys.path.insert(0, str(ROOT / 'research'))
import config as CFG
from core.events import classify_title
conn = sqlite3.connect(CFG.ANNOUNCE_DB)
_BY = {}
for d, c, t in conn.execute("SELECT date, stock_code, title FROM announce"):
    is_ev, knd, pol, *_ = classify_title(t)
    if is_ev and pol > 0:
        _BY.setdefault(c, []).append(d)
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


def chain_ind_weight(r):
    """s4-s14 的净链无关权重串 (原 v24 参数)"""
    w = 1.0
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
        n_ev = sum(1 for a in _BY.get(code, []) if lo <= a <= hi)
        if n_ev >= 3:
            w *= 1.2
        elif n_ev <= 1:
            w *= 0.7
    enr = ERN.get(r['symbol'] + '|' + r['entry_date'])
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
    return w


for r in rows:
    r['_w_base_'] = chain_ind_weight(r)


def total_v24_v2(w_choch, w_up, extra_rules):
    """v24_v2 = base(链无关) × s1v2 × s7v2 × 新规则."""
    for r in rows:
        w = r['_w_base_']
        if r['_v2_choch']:
            w *= w_choch
        if r['_v2_trend_up']:
            w *= w_up
        for fn, wv in extra_rules:
            if fn(r):
                w *= wv
        r['_w_'] = w
    return stw(rows)


print('\n=== E. 完整组合变体 (基准 s1v2=0.4 s7v2=0.5 = R92 最优) ===')
for name, extras in (
        ('仅s1v2+s7v2 @ (0.4, 0.5)', []),
        ('+s15: BOS↓+retrace_fail ×0.6', [(cand_defs['s15_bosdown_retrace_fail'], 0.6)]),
        ('+s16: up+no_retrace ×0.7', [(cand_defs['s16_up_no_retrace'], 0.7)]),
        ('+s18: CHoCH↑+no_retrace ×0.5', [(cand_defs['s18_chochup_noret'], 0.5)]),
        ('+s19: CHoCH↑+retfail ×0.5', [(cand_defs['s19_chochup_retfail'], 0.5)]),
        ('+s20: CHoCH↓+retfail ×0.5', [(cand_defs['s20_chochdown_retfail'], 0.5)]),
        ('+s21: BOS↑+retfail ×0.6', [(cand_defs['s21_bosup_retfail'], 0.6)]),
        ('+s18+s19+s20 (choch×noret/fail 包)', [(cand_defs['s18_chochup_noret'], 0.5),
                                           (cand_defs['s19_chochup_retfail'], 0.5),
                                           (cand_defs['s20_chochdown_retfail'], 0.5)]),
        ('+s18+s19+s20+s15+s16 (齐全)', [(cand_defs['s18_chochup_noret'], 0.5),
                                     (cand_defs['s19_chochup_retfail'], 0.5),
                                     (cand_defs['s20_chochdown_retfail'], 0.5),
                                     (cand_defs['s15_bosdown_retrace_fail'], 0.6),
                                     (cand_defs['s16_up_no_retrace'], 0.7)]),
        ('+s15+s16+s17', [(cand_defs['s15_bosdown_retrace_fail'], 0.6),
                            (cand_defs['s16_up_no_retrace'], 0.7),
                            (cand_defs['s17_down_retrace_ok'], 1.1)]),
        ('全部 s15-s20', [(cand_defs['s15_bosdown_retrace_fail'], 0.6),
                        (cand_defs['s16_up_no_retrace'], 0.7),
                        (cand_defs['s17_down_retrace_ok'], 1.1),
                        (cand_defs['s18_chochup_noret'], 0.5),
                        (cand_defs['s19_chochup_retfail'], 0.5),
                        (cand_defs['s20_chochdown_retfail'], 0.5),
                        (cand_defs['s21_bosup_retfail'], 0.6)]),
        ('全部 s15-s20 [狠打版: 伤桶×0.35/0.4]', [(cand_defs['s15_bosdown_retrace_fail'], 0.5),
                                            (cand_defs['s16_up_no_retrace'], 0.6),
                                            (cand_defs['s17_down_retrace_ok'], 1.1),
                                            (cand_defs['s18_chochup_noret'], 0.35),
                                            (cand_defs['s19_chochup_retfail'], 0.35),
                                            (cand_defs['s20_chochdown_retfail'], 0.35),
                                            (cand_defs['s21_bosup_retfail'], 0.5)]),
):
    s = total_v24_v2(0.4, 0.5, extras)
    print(f"  {name:36s}: n={s[0]} Σw={s[1]} avg={s[2]:+.2f} WR={s[3]} PF={s[4]}")
