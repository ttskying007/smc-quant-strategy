# -*- coding: utf-8 -*-
"""R125: sweep→reverse 2.0 反向信号候选 (方向修正版)。

背景 (R122b 证伪): 二测反弹 bar 入场"顺池侧方向"做多是错的 (EQH avg −10.9%)。
正确解读: EQH(上方池)二测反弹 = 拒绝→做空; EQL(下方池)二测反弹 = 拒绝→做多。

本脚本 (扩到 300 只股票, 双向):
  对每 symbol 的 EQH/EQL 池 (auto pivot, 0.8% 容差, 近250 bar):
  - 影线假扫回收的池 → 首次影线触及 (sweep bar)
  - 20 bar 内回测反弹 (触及池位且 close 收回池内侧) → 信号 bar = 反弹 bar
  - 入场: 反弹 bar close, 方向 = 反池侧 (EQH→short, EQL→long)
  - 10 bar 远期收益 (按方向取符号)
对比基准: 全样本同期平均 10 bar 收益。
输出: research/combo_reverse_candidates.csv + handover/_r125_reverse_stats.json
"""
import csv, json, os, sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from core.structure import is_swing_high, is_swing_low, pick_pivot_by_density

ROOT = Path(r'E:\test\smc_project')
KLINE = ROOT / 'hermes/kline_cache_tencent'
N_RETEST = 20
N_FUND = 10


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


def reverse_candidates(ks, tol_ratio=0.008, lookback=250):
    n = len(ks) - 1
    pv, _ = pick_pivot_by_density(ks, n)
    cph = [(j, ks[j]['h']) for j in range(pv, len(ks) - pv) if is_swing_high(ks, j, pv)]
    cpl = [(j, ks[j]['l']) for j in range(pv, len(ks) - pv) if is_swing_low(ks, j, pv)]
    cut = n - lookback
    out = []

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
                res.append({'price': pp, 'sweep_i': sweep_i, 'state': state})
        return res

    for side, key in (('eqh', 'EQH'), ('eql', 'EQL')):
        for q in pools(cph if side == 'eqh' else cpl, side):
            if q['state'] != '影线假扫回收' or q['sweep_i'] < 0:
                continue
            pp, si = q['price'], q['sweep_i']
            for k in range(si + 1, min(si + N_RETEST, len(ks))):
                bounce = (side == 'eqh' and ks[k]['h'] > pp and ks[k]['c'] <= pp) or \
                         (side == 'eql' and ks[k]['l'] < pp and ks[k]['c'] >= pp)
                broke = (side == 'eqh' and ks[k]['c'] > pp) or (side == 'eql' and ks[k]['c'] < pp)
                if broke:
                    break
                if bounce and k + N_FUND < len(ks):
                    # 反向入场: EQH→short, EQL→long; 收益按方向取符号
                    raw = (ks[k + N_FUND]['c'] / ks[k]['c'] - 1) * 100
                    ret = -raw if side == 'eqh' else raw
                    out.append({'symbol': ks[0]['t'] and (os.path.basename(KLINE.name) or ''),  # placeholder
                                'side': key, 'pool_price': round(pp, 2),
                                'sweep_date': ks[si]['t'], 'signal_date': ks[k]['t'],
                                'entry_price': round(ks[k]['c'], 2),
                                'ret_10b_signed': round(ret, 2)})
                    break
    return out


def main():
    files = sorted(KLINE.glob('*_daily_800.json'))[:300]
    rows_out = []
    for f in files:
        sym = f.name.replace('_daily_800.json', '').replace('_SH', '.SH').replace('_SZ', '.SZ').replace('_BJ', '.BJ')
        ks = load_klines(sym)
        if not ks:
            continue
        for r in reverse_candidates(ks):
            r['symbol'] = sym
            rows_out.append(r)
    with open(ROOT / 'research/combo_reverse_candidates.csv', 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['symbol', 'side', 'pool_price', 'sweep_date',
                                           'signal_date', 'entry_price', 'ret_10b_signed'])
        w.writeheader()
        w.writerows(rows_out)

    print(f'=== R125 sweep→reverse 2.0 反向候选 ({len(files)}只股票) ===')
    print(f'信号总数: {len(rows_out)}')

    def bucket(name, sel):
        b = [r for r in rows_out if sel(r)]
        if not b:
            print(f'{name}: n=0')
            return
        p = [r['ret_10b_signed'] for r in b]
        gp = sum(x for x in p if x > 0)
        gl = -sum(x for x in p if x < 0)
        pf = (gp / gl) if gl > 0 else 99.0
        print(f'{name}: n={len(b)} avg={sum(p)/len(p):+.2f}% WR={sum(1 for x in p if x>0)/len(b)*100:.1f}% PF={pf:.2f}')

    bucket('EQH 二测拒绝→空 ', lambda r: r['side'] == 'EQH')
    bucket('EQL 二测拒绝→多 ', lambda r: r['side'] == 'EQL')
    bucket('全部              ', lambda r: True)

    json.dump({'total': len(rows_out),
               'eqh': [r for r in rows_out if r['side'] == 'EQH'][:30],
               'eql': [r for r in rows_out if r['side'] == 'EQL'][:30]},
              open(ROOT / 'research/handover/_r125_reverse_stats.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1, default=str)
    print('\n写出 research/combo_reverse_candidates.csv + handover/_r125_reverse_stats.json')


if __name__ == '__main__':
    main()
