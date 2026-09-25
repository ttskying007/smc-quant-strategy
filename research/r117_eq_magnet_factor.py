# -*- coding: utf-8 -*-
"""R117: 活跃磁区(EQH/EQL)因子 — 逐腿回测验证, additive-only 影子记录。

因子定义 (因果安全: 只用入场日前已确认信息):
  - 在入场日之前已确认的 EQH/EQL 池 (成员bar + pivot确认 <= 入场bar)
  - 池在入场时刻仍未被 close 实破 (未扫/影线假扫 → 活跃; 实收穿越 → 失效)
  - eq_near_active: 入场价 1% 内存在活跃池 (向上=EQH 磁吸目标, 向下=EQL 风险位)
输出: research/combo_v22_eq_magnet.csv + 分桶 PnL 对比 (handover)
"""
import csv, json, os, sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from core.structure import is_swing_high, is_swing_low, pick_pivot_by_density

ROOT = Path(r'E:\test\smc_project')
KLINE = ROOT / 'hermes/kline_cache_tencent'
OUT = ROOT / 'research/combo_v22_eq_magnet.csv'


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


def eq_pools_at_entry(ks, entry_d8, tol_ratio=0.008, lookback=250):
    """入场日之前已确认、且入场时刻仍活跃的 EQH/EQL 池。"""
    ei = next((i for i, k in enumerate(ks) if k['t'] == entry_d8), None)
    if ei is None:
        return None
    pv, _ = pick_pivot_by_density(ks, ei)  # 因果: 只用 ei 前数据标定
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
                # 入场时刻状态: pj 之后到 ei 之间 close 实破 → 失效
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

    return {'eqh': cluster(cph, 'eqh'), 'eql': cluster(cpl, 'eql'), 'entry_price': ks[ei]['c']}


def main():
    rows = list(csv.DictReader(open(ROOT / 'research/combo_v22_trades.csv', encoding='utf-8-sig')))
    out_rows = []
    kcache = {}
    for r in rows:
        sym = r['symbol']
        if sym not in kcache:
            kcache[sym] = load_klines(sym)
        ks = kcache[sym]
        eqr = eq_pools_at_entry(ks, str(r['entry_date']).replace('-', '')) if ks else None
        if eqr is None:
            out_rows.append({'symbol': sym, 'entry_date': r['entry_date'], 'src': r['src'],
                             'net_pnl_pct': r['net_pnl_pct'],
                             'eq_near_active': '', 'eqh_active_n': '', 'eql_active_n': '',
                             'eq_conflu': ''})
            continue
        ep = eqr['entry_price']
        near_h = [q for q in eqr['eqh'] if q['active'] and abs(q['price'] - ep) / ep <= 0.01]
        near_l = [q for q in eqr['eql'] if q['active'] and abs(q['price'] - ep) / ep <= 0.01]
        near = bool(near_h or near_l)
        conflu = bool(near_h and near_l)  # 上下同时有活跃磁区 = 挤压区
        out_rows.append({'symbol': sym, 'entry_date': r['entry_date'], 'src': r['src'],
                         'net_pnl_pct': r['net_pnl_pct'],
                         'eq_near_active': 'True' if near else 'False',
                         'eqh_active_n': str(len(near_h)),
                         'eql_active_n': str(len(near_l)),
                         'eq_conflu': 'True' if conflu else 'False'})
    with open(OUT, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['symbol', 'entry_date', 'src', 'net_pnl_pct',
                                           'eq_near_active', 'eqh_active_n', 'eql_active_n', 'eq_conflu'])
        w.writeheader()
        w.writerows(out_rows)

    # 分桶对比
    def bucket(name, sel):
        sel = [r for r in out_rows if sel(r)]
        if not sel:
            print(f'{name}: n=0')
            return
        pnls = [float(r['net_pnl_pct']) for r in sel]
        avg = sum(pnls) / len(pnls)
        wins = sum(1 for p in pnls if p > 0)
        gp = sum(p for p in pnls if p > 0)
        gl = -sum(p for p in pnls if p < 0)
        pf = (gp / gl) if gl > 0 else float('inf')
        print(f'{name}: n={len(sel)} avg={avg:+.2f}% WR={wins/len(sel)*100:.1f}% PF={pf:.2f}')

    print('\n=== R117 活跃磁区分桶 (combo_v22 1858腿) ===')
    bucket('近活跃磁区 True ', lambda r: r['eq_near_active'] == 'True')
    bucket('近活跃磁区 False', lambda r: r['eq_near_active'] == 'False')
    bucket('上下挤压 conflu ', lambda r: r['eq_conflu'] == 'True')
    bucket('无挤压 conflu  ', lambda r: r['eq_conflu'] == 'False')
    bucket('上方EQH磁吸     ', lambda r: r['eqh_active_n'] not in ('', '0'))
    bucket('下方EQL风险     ', lambda r: r['eql_active_n'] not in ('', '0'))
    print(f'\n写出 {OUT.name}: {len(out_rows)} 行')


if __name__ == '__main__':
    main()
