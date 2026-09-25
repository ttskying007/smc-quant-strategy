# -*- coding: utf-8 -*-
"""R122: 二次测试磁区统计 + s22/s23 年度稳定性。

A) 二次测试磁区 (SMC: sweep→reverse 最可靠):
   对每 symbol 的 EQH/EQL 池 (auto pivot, 0.8% 容差):
   - 找影线假扫回收的池 → 首次影线触及bar (sweep bar)
   - 之后 N=20 bar 内: 价格回到池位且 close 收回池内侧 → retest_win
     close 实破池位 → retest_fail
   - 汇总 retest 胜率 (全部 + 分 EQH/EQL)
B) s22/s23 毒性桶年度稳定性 (combo_v23_shadow_v3 × combo_v22_trades):
   每年 (2023/2024/2025/2026) 的 s22/s23 腿数与 PF。
输出: research/handover/_r122_retest_stats.json
"""
import csv, json, os, sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from core.structure import is_swing_high, is_swing_low, pick_pivot_by_density

ROOT = Path(r'E:\test\smc_project')
KLINE = ROOT / 'hermes/kline_cache_tencent'
N_RETEST = 20


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


def retest_stats(ks, tol_ratio=0.008, lookback=250):
    """对每池统计: 影线假扫回收 → 二次测试胜/败。"""
    n = len(ks) - 1
    pv, _ = pick_pivot_by_density(ks, n)
    cph = [(j, ks[j]['h']) for j in range(pv, len(ks) - pv) if is_swing_high(ks, j, pv)]
    cpl = [(j, ks[j]['l']) for j in range(pv, len(ks) - pv) if is_swing_low(ks, j, pv)]
    cut = n - lookback
    out = {'eqh': [], 'eql': []}

    def pools(pivs, side):
        cand = sorted([(j, p) for j, p in pivs if j >= cut], key=lambda x: -x[0])
        used = [False] * len(cand)
        res = []
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
                # 找首次影线触及 (sweep bar), 之后是否 close 实破 → 状态
                sweep_i = -1
                wick = False
                state = '未扫'
                for k in range(pj + 1, len(ks)):
                    if side == 'eqh':
                        if ks[k]['h'] > pp:
                            wick = True
                            if sweep_i < 0:
                                sweep_i = k
                        if ks[k]['c'] > pp:
                            state = '实收穿越'
                            break
                    else:
                        if ks[k]['l'] < pp:
                            wick = True
                            if sweep_i < 0:
                                sweep_i = k
                        if ks[k]['c'] < pp:
                            state = '实收穿越'
                            break
                else:
                    state = '影线假扫回收' if wick else '未扫'
                res.append({'price': pp, 'sweep_i': sweep_i, 'state': state,
                            'last_j': pj})
        return res

    # A) 二次测试: 对 影线假扫回收 的池, sweep bar 后 N bar 内回测胜/败
    for side, key in (('eqh', 'eqh'), ('eql', 'eql')):
        for q in pools(cph if side == 'eqh' else cpl, side):
            if q['state'] != '影线假扫回收' or q['sweep_i'] < 0:
                continue
            pp = q['price']
            si = q['sweep_i']
            verdict = 'no_retest'
            for k in range(si + 1, min(si + N_RETEST, len(ks))):
                if side == 'eqh':
                    if ks[k]['c'] > pp:
                        verdict = 'retest_fail'; break
                    if ks[k]['h'] > pp and ks[k]['c'] <= pp:
                        # 回到池位且收回 → bounce (取 sweep 后首次回测)
                        verdict = 'retest_win'; break
                else:
                    if ks[k]['c'] < pp:
                        verdict = 'retest_fail'; break
                    if ks[k]['l'] < pp and ks[k]['c'] >= pp:
                        verdict = 'retest_win'; break
            out[key].append({'symbol_t': ks[q['last_j']]['t'], 'price': round(pp, 2),
                             'sweep_date': ks[si]['t'], 'verdict': verdict})
    return out


def main():
    # R122b: 扩样本 — 前120只股票 (假扫池稀缺, 8只不够)
    files = sorted(KLINE.glob('*_daily_800.json'))[:120]
    syms = [f.name.replace('_daily_800.json', '').replace('_SH', '.SH').replace('_SZ', '.SZ').replace('_BJ', '.BJ')
            for f in files]
    tot = {'eqh': [], 'eql': []}
    detail = {}
    for s in syms:
        ks = load_klines(s)
        if not ks:
            continue
        r = retest_stats(ks)
        detail[s] = r
        for k in ('eqh', 'eql'):
            tot[k].extend(r[k])

    print('=== R122 二次测试磁区 (sweep→reverse, N=%d bar) ===' % N_RETEST)
    jout = {}
    for k in ('eqh', 'eql'):
        rows = tot[k]
        w = sum(1 for r in rows if r['verdict'] == 'retest_win')
        f = sum(1 for r in rows if r['verdict'] == 'retest_fail')
        nr = sum(1 for r in rows if r['verdict'] == 'no_retest')
        wr = (w / (w + f) * 100) if (w + f) else 0
        print(f'{k.upper()}: 假扫回收池 n={len(rows)} | 二测win={w} fail={f} 无二测={nr} | 二测胜率 {wr:.1f}%')
        jout[k] = {'n': len(rows), 'win': w, 'fail': f, 'no_retest': nr, 'win_rate': round(wr, 1)}

    # B) s22/s23 年度稳定性
    try:
        sh3 = {r['symbol'] + '|' + r['entry_date']: r
               for r in csv.DictReader(open(ROOT / 'research/combo_v23_shadow_v3.csv', encoding='utf-8-sig'))}
        trades = list(csv.DictReader(open(ROOT / 'research/combo_v22_trades.csv', encoding='utf-8-sig')))
        print('\n=== s22/s23 毒性桶年度稳定性 ===')
        yr = {}
        for r in trades:
            key = r['symbol'] + '|' + r['entry_date']
            fl = (sh3.get(key) or {}).get('v23_flags_v2') or ''
            fls = fl.split(';')
            tag = None
            if 's22' in fls:
                tag = 's22'
            elif 's23' in fls:
                tag = 's23'
            if not tag:
                continue
            y = str(r['entry_date'])[:4]
            yr.setdefault((tag, y), []).append(float(r['net_pnl_pct']))
        jout['yearly'] = {}
        for (tag, y) in sorted(yr.keys()):
            p = yr[(tag, y)]
            gp = sum(x for x in p if x > 0)
            gl = -sum(x for x in p if x < 0)
            pf = (gp / gl) if gl > 0 else 99.0
            print(f'{tag} {y}: n={len(p)} avg={sum(p)/len(p):+.2f}% PF={pf:.2f}')
            jout['yearly'][f'{tag}_{y}'] = {'n': len(p), 'avg': round(sum(p)/len(p), 2), 'pf': round(pf, 2)}
    except Exception as e:
        print('yearly fail:', e)

    jout['detail'] = detail
    json.dump(jout, open(ROOT / 'research/handover/_r122_retest_stats.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1, default=str)
    print('\n写出 research/handover/_r122_retest_stats.json')


if __name__ == '__main__':
    main()
