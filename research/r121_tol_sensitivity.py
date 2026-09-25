# -*- coding: utf-8 -*-
"""R121: EQH/EQL 容差敏感性 — 毒性桶(s24 EQL风险)是否随容差稳定。

对 tol_ratio ∈ {0.5%, 0.8%, 1.2%, 1.5%} 各跑一遍 r117 因子逻辑,
对比: 近磁区腿数 / EQL毒性腿数 / 分桶 PF。若毒性桶随容差单调稳定 → 因子可信。
输出: research/handover/_r121_tol_sensitivity.json
"""
import csv, json, os, sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from core.structure import is_swing_high, is_swing_low, pick_pivot_by_density

ROOT = Path(r'E:\test\smc_project')
KLINE = ROOT / 'hermes/kline_cache_tencent'


def load_klines(sym):
    sf = sym.replace('.SH', '_SH').replace('.SZ', '_SZ').replace('.BJ', '_BJ')
    fp = KLINE / (sf + '_daily_800.json')
    if not fp.exists():
        return None
    d = json.load(open(fp, encoding='utf-8'))
    raw = d if isinstance(d, list) else (d.get('klines') or d.get('bars') or [])
    return [{'t': str(k.get('t', k.get('date', '')))[:10].replace('-', ''),
             'h': float(k.get('h', k.get('high', 0))), 'l': float(k.get('l', k.get('low', 0))),
             'c': float(k.get('c', k.get('close', 0)))} for k in raw]


def factor_at_tol(ks, entry_d8, tol_ratio, lookback=250):
    ei = next((i for i, k in enumerate(ks) if k['t'] == entry_d8), None)
    if ei is None:
        return None
    pv, _ = pick_pivot_by_density(ks, ei)
    cph = [(j, ks[j]['h']) for j in range(pv, ei - pv + 1) if is_swing_high(ks, j, pv)]
    cpl = [(j, ks[j]['l']) for j in range(pv, ei - pv + 1) if is_swing_low(ks, j, pv)]
    cut = ei - lookback

    def cluster(pivs, side):
        cand = sorted([(j, p) for j, p in pivs if j >= cut], key=lambda x: -x[0])
        used = [False] * len(cand)
        out = []
        for a in range(len(cand)):
            if used[a]:
                continue
            j1, p1 = cand[a]
            members = [a]
            for b in range(a + 1, len(cand)):
                if abs(cand[b][1] - p1) / p1 <= tol_ratio:
                    members.append(b)
                    used[b] = True
            if len(members) >= 2:
                js = [cand[m][0] for m in members]
                pp = sum(cand[m][1] for m in members) / len(members)
                pj = max(js)
                wick = False
                state = '未扫'
                for kk in ks[pj + pv + 1:ei + 1]:
                    if side == 'eqh':
                        if kk['h'] > pp:
                            wick = True
                        if kk['c'] > pp:
                            state = '实收穿越'
                            break
                    else:
                        if kk['l'] < pp:
                            wick = True
                        if kk['c'] < pp:
                            state = '实收穿越'
                            break
                else:
                    state = '影线假扫回收' if wick else '未扫'
                out.append({'price': pp, 'state': state,
                            'active': state in ('未扫', '影线假扫回收')})
        return out

    ep = ks[ei]['c']
    near_h = [q for q in cluster(cph, 'eqh') if q['active'] and abs(q['price'] - ep) / ep <= 0.01]
    near_l = [q for q in cluster(cpl, 'eql') if q['active'] and abs(q['price'] - ep) / ep <= 0.01]
    return {'near': bool(near_h or near_l), 'eql_n': len(near_l), 'eqh_n': len(near_h)}


def main():
    rows = list(csv.DictReader(open(ROOT / 'research/combo_v22_trades.csv', encoding='utf-8-sig')))
    kcache = {}
    print('=== R121 容差敏感性 (1858腿) ===')
    print(f"{'tol':>6} | {'近磁区n':>7} | {'EQL毒n':>7} | {'毒PF':>6} | {'磁区PF':>6} | {'无磁区PF':>7}")
    out = []
    for tol in (0.005, 0.008, 0.012, 0.015):
        near_rows, eql_rows = [], []
        all_flagged = []
        for r in rows:
            sym = r['symbol']
            if sym not in kcache:
                kcache[sym] = load_klines(sym)
            ks = kcache[sym]
            if not ks:
                continue
            f = factor_at_tol(ks, str(r['entry_date']).replace('-', ''), tol)
            if f is None:
                continue
            pnl = float(r['net_pnl_pct'])
            if f['near']:
                near_rows.append(pnl)
                all_flagged.append((r, f))
            if f['near'] and f['eql_n'] >= 1:
                eql_rows.append(pnl)

        def pf_of(ps):
            if not ps:
                return 0.0
            gp = sum(x for x in ps if x > 0)
            gl = -sum(x for x in ps if x < 0)
            return (gp / gl) if gl > 0 else 99.0

        rest = [float(r['net_pnl_pct']) for r in rows
                if r['symbol'] in kcache and kcache[r['symbol']]]
        print(f"{tol*100:.1f}% | {len(near_rows):>7} | {len(eql_rows):>7} | "
              f"{pf_of(eql_rows):>6.2f} | {pf_of(near_rows):>6.2f} |")
        out.append({'tol': tol, 'near_n': len(near_rows), 'eql_toxic_n': len(eql_rows),
                    'eql_toxic_pf': pf_of(eql_rows), 'near_pf': pf_of(near_rows)})
    json.dump(out, open(ROOT / 'research/handover/_r121_tol_sensitivity.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n判读: 若 EQL毒n 随容差放宽而增长但 PF 始终 <1 → 毒性稳定, 因子可信度升。')


if __name__ == '__main__':
    main()
