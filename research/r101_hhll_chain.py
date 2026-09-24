# -*- coding: utf-8 -*-
r"""R101 — HH/HL/LH/LL 显式摆动结构在 v2 自适应链下的腿级审计

输出:
  research/combo_v22_chain_v2_hhll.csv  (1858 腿 + structure_state 列)
  桶位统计: 按 structure_state / last_high_label / last_low_label 分 PnL, 看是否新伤桶露出
"""
import csv, io, json, sys, time
from pathlib import Path
sys.path.insert(0, r'E:\test\smc_project\research')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(r'E:\test\smc_project')

from core.chain import build_chain

KC = ROOT / 'hermes' / 'kline_cache_tencent'

def bars_of(code6):
    p = KC / (code6 + ('_SH' if code6.startswith('6') else '_SZ') + '_daily_800.json')
    if not p.exists():
        return []
    raw = json.loads(p.read_text(encoding='utf-8'))
    bs = []
    for r in raw:
        t = ''.join(x for x in str(r.get('t') or '') if x.isdigit())[:8]
        if t:
            try:
                bs.append({'t': t, 'o': float(r['o']), 'h': float(r['h']),
                           'l': float(r['l']), 'c': float(r['c']),
                           'v': float(r.get('v') or 0)})
            except Exception:
                continue
    bs.sort(key=lambda b: b['t'])
    return bs


def st(rs):
    n = len(rs)
    if not n:
        return (0, 0, 0, 0)
    p = [float(r['pnl'] or 0) for r in rs]
    avg = sum(p) / n
    wr = sum(1 for v in p if v > 0) / n * 100
    pos = sum(v for v in p if v > 0)
    neg = -sum(v for v in p if v < 0)
    return n, round(avg, 2), round(wr, 1), round(pos / neg, 2) if neg else 999


def main():
    rows = list(csv.DictReader(open(ROOT / 'research' / 'combo_v22_trades.csv', encoding='utf-8-sig')))
    print(f'legs: {len(rows)}')
    t0 = time.time()
    out_rows = []
    cache = {}
    for idx, row in enumerate(rows):
        code6 = row['symbol'][:6]
        if code6 not in cache:
            cache[code6] = bars_of(code6)
        bs = cache[code6]
        if not bs:
            continue
        dates = [b['t'] for b in bs]
        ed = str(row['entry_date'])
        if ed not in dates:
            continue
        ei = dates.index(ed)
        i = ei - 1
        if i < 60:
            continue
        try:
            ch = build_chain(bs, i, mode='auto')
        except Exception:
            continue
        out_rows.append({**row,
                         'structure_state': ch.get('structure_state') or 'none',
                         'trend_v2': ch.get('trend_state') or '',
                         'breakout_kind_v2': (ch.get('breakout') or {}).get('kind') or '',
                         'retrace_state_v2': (ch.get('retrace') or {}).get('state') or '',
                         'pnl': float(row.get('net_pnl_pct') or 0)})
        if idx % 400 == 399:
            print(f'  {idx+1}/{len(rows)} t={time.time()-t0:.0f}s')

    out_path = ROOT / 'research/combo_v22_chain_v2_hhll.csv'
    cols = ['symbol', 'entry_date', 'src', 'net_pnl_pct', 'pnl', 'structure_state',
            'trend_v2', 'breakout_kind_v2', 'retrace_state_v2']
    with open(out_path, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        w.writerows(out_rows)
    print(f'\n写 {out_path.name}: {len(out_rows)}')

    print('\n=== structure_state 桶 (v2 自适应) ===')
    from collections import defaultdict
    g = defaultdict(list)
    for r in out_rows:
        g[r['structure_state']].append(r)
    for k, rs in sorted(g.items(), key=lambda kv: -len(kv[1])):
        s = st(rs)
        print(f"  {k:22s}: n={s[0]:4d} avg={s[1]:+6.2f} WR={s[2]:5.1f} PF={s[3]:6.2f}")

    # ── 交互: structure × breakout × retrace (找新伤桶) ──
    print('\n=== structure_state × breakout_kind_v2 × retrace_state_v2 (n≥30) ===')
    g2 = defaultdict(list)
    for r in out_rows:
        g2[(r['structure_state'], r['breakout_kind_v2'], r['retrace_state_v2'])].append(r)
    for k, rs in sorted(g2.items(), key=lambda kv: -len(kv[1])):
        s = st(rs)
        if s[0] >= 30:
            mark = '⚠' if s[3] < 2.5 else ''
            print(f"  {k[0]:22s} × {k[1]:8s} × {k[2]:12s}: n={s[0]:4d} avg={s[1]:+6.2f} PF={s[3]:6.2f} {mark}")

    # ── 把 structure_state 合成回不带括号的 key, 供与 R93 狠打表组合 ──
    def sst_key(s):
        if s.startswith('bull'):
            return 'bull'
        if s.startswith('bear'):
            return 'bear'
        if s.startswith('expansion'):
            return 'expansion'
        if s.startswith('compress'):
            return 'compress'
        return 'none'
    for r in out_rows:
        r['_sst'] = sst_key(r['structure_state'])

    #  R94 狠打公式 (base): s1v2=0.4 s7v2=0.5 + s15-s21
    def w_v2h(r):
        w = 1.0
        bk = r['breakout_kind_v2'] or ''
        rt = r['retrace_state_v2'] or ''
        tr = r['trend_v2'] or ''
        if 'CHoCH' in bk:
            w *= 0.4
        if tr == 'up':
            w *= 0.5
        if bk == 'CHoCH↑' and rt == 'no_retrace':
            w *= 0.35
        if bk == 'CHoCH↑' and rt == 'retrace_fail':
            w *= 0.35
        if bk == 'CHoCH↓' and rt == 'retrace_fail':
            w *= 0.35
        if bk == 'BOS↑' and rt == 'retrace_fail':
            w *= 0.4
        if bk in ('BOS↓', 'CHoCH↓') and rt == 'retrace_fail':
            w *= 0.5
        if tr == 'up' and rt == 'no_retrace':
            w *= 0.6
        if tr == 'down' and rt == 'retrace_ok':
            w *= 1.1
        return w

    # s22/s23 候选
    def w_s22(r, w_heavy):
        w = 1.0
        if r['_sst'] == 'bull' and r['breakout_kind_v2'] == 'BOS↑' and r['retrace_state_v2'] == 'retrace_ok':
            w *= w_heavy
        return w

    def w_s23(r, w_heavy):
        w = 1.0
        if r['_sst'] == 'bear' and r['breakout_kind_v2'] == 'CHoCH↑' and r['retrace_state_v2'] == 'no_retrace':
            w *= w_heavy
        return w


    def stw(rs, wk):
        tw = sum(r[wk] for r in rs)
        if not tw:
            return (0, 0, 0, 0)
        p = [float(r['pnl'] or 0) * r[wk] for r in rs]
        avg = sum(p) / tw
        wr = sum(r[wk] for r, v in zip(rs, p) if v > 0) / tw * 100
        pos = sum(v for v in p if v > 0)
        neg = -sum(v for v in p if v < 0)
        return len(rs), round(avg, 2), round(wr, 1), round(pos / neg, 2) if neg else 999

    print('\n=== 在 v2狠打之上 ^ s22/s23 微网 ===')
    print(f"{'w_s22':>6} {'w_s23':>6} {'avg%':>7} {'WR%':>6} {'PF':>6}")
    results = []
    for w22 in (1.0, 0.5, 0.35, 0.25):
        for w23 in (1.0, 0.5, 0.35, 0.25):
            for r in out_rows:
                r['_w'] = w_v2h(r) * w_s22(r, w22) * w_s23(r, w23)
            s = stw(out_rows, '_w')
            results.append((w22, w23, s))
            print(f"{w22:6.2f} {w23:6.2f} {s[1]:7.2f} {s[2]:6.1f} {s[3]:6.2f}")
    best = max(results, key=lambda t: t[2][3])
    print(f'\n最优: s22={best[0]} s23={best[1]} avg={best[2][1]:+.2f} PF={best[2][3]}')
    print('(参考: R94 本狠打原 = PF 6.98, 等权 3.36, v1 5.89)')

    # ── 全套分： R94 base(链无关) + s1v2/s7v2 + s15-s21 + s22/s23 组合 ──
    import sqlite3, datetime, json as _j
    import config as CFG
    from core.events import classify_title
    ENR2 = {r['symbol'] + '|' + r['entry_date']: r
            for r in csv.DictReader(open(ROOT / 'research/combo_v22_smc_full_v2.csv', encoding='utf-8-sig'))}
    conn = sqlite3.connect(CFG.ANNOUNCE_DB)
    BY = {}
    for d, c, t in conn.execute("SELECT date, stock_code, title FROM announce"):
        is_ev, knd, pol, *_ = classify_title(t)
        if is_ev and pol > 0:
            BY.setdefault(c, []).append(d)
    conn.close()
    IDX = _j.load(open(ROOT / 'research/idx_sh000001.json', encoding='utf-8'))

    def idx20(d):
        d = str(d).replace('-', '')
        j = -1
        for i in range(len(IDX) - 1, -1, -1):
            if str(IDX[i]['t']) <= d:
                j = i; break
        if j < 20:
            return None
        return (float(IDX[j]['c']) / float(IDX[j - 20]['c']) - 1) * 100

    def w_common(r, w):
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
        try:
            rc = _j.loads(r.get('rank_components') or '{}')
            if rc.get('vr2') == 1 or rc.get('vol_cont') == 1:
                w *= 0.7
        except Exception:
            pass
        m20 = idx20(r['entry_date'])
        if m20 is not None and m20 < -2:
            w *= 0.5
        return w

    def w_enrich_v2(r, w):
        enr = ENR2.get(r['symbol'] + '|' + r['entry_date'])
        if not enr:
            return w
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
        return w

    print('\n=== R94 全套基线 + s22/s23 微网 (真参考: R94 狠打 PF 6.98) ===')
    print(f"{'w_s22':>6} {'w_s23':>6} {'avg%':>7} {'WR%':>6} {'PF':>6}")
    combos = []
    for w22 in (1.0, 0.5, 0.35, 0.25, 0.15):
        for w23 in (1.0, 0.5, 0.35, 0.25, 0.15):
            for r in out_rows:
                w = w_v2h(r) * w_s22(r, w22) * w_s23(r, w23)
                w = w_enrich_v2(r, w)
                w = w_common(r, w)
                r['_w2'] = w
            s = stw(out_rows, '_w2')
            combos.append((w22, w23, s))
            print(f"{w22:6.2f} {w23:6.2f} {s[1]:7.2f} {s[2]:6.1f} {s[3]:6.2f}")
    best2 = max(combos, key=lambda t: t[2][3])
    print(f'\n全套最优: s22={best2[0]} s23={best2[1]} avg={best2[2][1]:+.2f} PF={best2[2][3]}')


if __name__ == '__main__':
    main()
