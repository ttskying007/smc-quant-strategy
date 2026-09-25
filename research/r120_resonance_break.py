# -*- coding: utf-8 -*-
"""R120: 共振破位 vs 普通破位 历史胜率 — 加权因子证据链。

定义 (因果安全: 只用破位日前已确认信息):
  - 每腿的 breakout 价位 (chain_json.breakout.price, 平铺字段 breakout_price)
  - 破位日前已确认且仍活跃的 EQH/EQL 池
  - 共振破位: breakout 价位与活跃池 0.5% 内重合 (扫池→破位强信号)
输出: research/combo_v22_resonance_break.csv + 分桶 PnL (handover)
"""
import csv, json, os, sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from core.structure import is_swing_high, is_swing_low, pick_pivot_by_density

ROOT = Path(r'E:\test\smc_project')
KLINE = ROOT / 'hermes/kline_cache_tencent'
OUT = ROOT / 'research/combo_v22_resonance_break.csv'


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


def active_pools_at(ks, d8, tol_ratio=0.008, lookback=250):
    """d8 日之前已确认且 d8 时刻仍活跃的 EQH/EQL 池。"""
    di = next((i for i, k in enumerate(ks) if k['t'] == d8), None)
    if di is None:
        return None
    pv, _ = pick_pivot_by_density(ks, di)
    cph = [(j, ks[j]['h']) for j in range(pv, di - pv + 1) if is_swing_high(ks, j, pv)]
    cpl = [(j, ks[j]['l']) for j in range(pv, di - pv + 1) if is_swing_low(ks, j, pv)]
    cut = di - lookback

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
                for kk in ks[pj + pv + 1:di + 1]:
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

    return {'eqh': cluster(cph, 'eqh'), 'eql': cluster(cpl, 'eql')}


def main():
    rows = list(csv.DictReader(open(ROOT / 'research/combo_v22_trades.csv', encoding='utf-8-sig')))
    out_rows = []
    kcache = {}
    for r in rows:
        sym = r['symbol']
        if sym not in kcache:
            kcache[sym] = load_klines(sym)
        ks = kcache[sym]
        bk_price = r.get('breakout_price') or ''
        bk_date = str(r.get('breakout_date') or '').replace('-', '')
        res = ''
        side = ''
        try:
            bp = float(bk_price)
            pools = active_pools_at(ks, bk_date) if (ks and bp > 0 and bk_date) else None
            if pools:
                for q in pools['eqh']:
                    if q['active'] and abs(q['price'] - bp) / bp <= 0.005:
                        res = 'True'; side = 'EQH'; break
                if not res:
                    for q in pools['eql']:
                        if q['active'] and abs(q['price'] - bp) / bp <= 0.005:
                            res = 'True'; side = 'EQL'; break
                if not res:
                    res = 'False'
        except Exception:
            res = ''
        out_rows.append({'symbol': sym, 'entry_date': r['entry_date'], 'src': r['src'],
                         'net_pnl_pct': r['net_pnl_pct'],
                         'resonance_break': res, 'resonance_side': side,
                         'breakout_price': bk_price, 'breakout_date': bk_date})
    with open(OUT, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['symbol', 'entry_date', 'src', 'net_pnl_pct',
                                           'resonance_break', 'resonance_side',
                                           'breakout_price', 'breakout_date'])
        w.writeheader()
        w.writerows(out_rows)

    def bucket(name, sel):
        b = [r for r in out_rows if sel(r)]
        if not b:
            print(f'{name}: n=0')
            return
        p = [float(r['net_pnl_pct']) for r in b]
        gp = sum(x for x in p if x > 0)
        gl = -sum(x for x in p if x < 0)
        pf = (gp / gl) if gl > 0 else float('inf')
        print(f'{name}: n={len(b)} avg={sum(p)/len(p):+.2f}% WR={sum(1 for x in p if x>0)/len(b)*100:.1f}% PF={pf:.2f}')

    print('\n=== R120 共振破位分桶 (combo_v22 1858腿) ===')
    bucket('共振破位 True (扫池→破) ', lambda r: r['resonance_break'] == 'True')
    bucket('普通破位 False           ', lambda r: r['resonance_break'] == 'False')
    bucket('共振-EQH (上方池)        ', lambda r: r['resonance_side'] == 'EQH')
    bucket('共振-EQL (下方池)        ', lambda r: r['resonance_side'] == 'EQL')
    print(f'\n写出 {OUT.name}: {len(out_rows)} 行')


if __name__ == '__main__':
    main()
