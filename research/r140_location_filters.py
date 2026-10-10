# -*- coding: utf-8 -*-
"""R140: 入场位置过滤器证伪 (R139 归纳发现的因果候选, R135 同款流程)。

R139 归纳出四个位置判别因子, 全部只用入场日及之前数据 (因果安全):
  G1 weak_day   : 事件日收盘位置 day_pos<40 (收盘弱) — R139: PF 1.58 vs 强收盘 PF 10.75
  G2 under_high : 最近确认摆动高距入场价 ±2% 内 (顶着阻力买) — R139: PF 1.27 vs 净空>5% PF 4.76
  G3 newlow_rng : 入场价在近20bar区间底部10% (loc20≤10) — R139: PF 1.67
  G4 chase_up   : 趋势up 且 loc20>60 (追高) — R139: up|high_half PF 1.27
  G5 gap_dead   : 事件日跳空 <-3% — R139: PF 1.10

流程与 R135 一致: 对同一腿池 (有位置特征的 1510 腿) 逐个测"剔除后留存"对比基线,
并测组合 G1+G2 (两个最干净的桶)。证据给用户决定晋级, 生产冻结不动。
输出: research/handover/_r140_location_filters.json
"""
import csv, json, sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(r'E:\test\smc_project')


def main():
    rows = list(csv.DictReader(open(ROOT / 'research/combo_v25_entry_location.csv', encoding='utf-8-sig')))
    pnls = {r['symbol'] + '|' + r['entry_date']: float(r.get('net_pnl_pct') or 0) for r in rows}

    def stats(sel_pnls):
        if not sel_pnls:
            return {'n': 0}
        gp = sum(x for x in sel_pnls if x > 0)
        gl = -sum(x for x in sel_pnls if x < 0)
        return {'n': len(sel_pnls), 'avg': round(sum(sel_pnls) / len(sel_pnls), 2),
                'wr': round(sum(1 for x in sel_pnls if x > 0) / len(sel_pnls) * 100, 1),
                'pf': round(gp / gl, 2) if gl > 0 else 99}

    base = list(pnls.values())
    res = {'baseline': stats(base), 'legs': len(rows)}

    def drop(pred):
        kept = [p for k, p in pnls.items() if not pred(k)]
        dropped = [p for k, p in pnls.items() if pred(k)]
        return stats(kept), stats(dropped)

    feats = {}
    for r in rows:
        feats[r['symbol'] + '|' + r['entry_date']] = r

    def f(key, name):
        return str(feats[key].get(name) or '')

    def fn_(key, name):
        try:
            return float(feats[key].get(name))
        except Exception:
            return None

    tests = {
        'G1_drop_weak_day(<40)': lambda k: (fn_(k, 'day_pos') is not None and fn_(k, 'day_pos') < 40),
        'G2_drop_under_high(±2%)': lambda k: (fn_(k, 'near_high') is not None and -2 <= fn_(k, 'near_high') <= 2),
        'G3_drop_newlow_rng(≤10)': lambda k: (fn_(k, 'loc20') is not None and fn_(k, 'loc20') <= 10),
        'G4_drop_chase_up': lambda k: (f(k, 'trend_state') == 'up' and fn_(k, 'loc20') is not None and fn_(k, 'loc20') > 60),
        'G5_drop_gap_dead(<-3%)': lambda k: (fn_(k, 'gap_pct') is not None and fn_(k, 'gap_pct') < -3),
        'G12_drop_weak_day+under_high': lambda k: ((fn_(k, 'day_pos') is not None and fn_(k, 'day_pos') < 40)
                                                   or (fn_(k, 'near_high') is not None and -2 <= fn_(k, 'near_high') <= 2)),
        'G123_drop_weak+high+newlow': lambda k: ((fn_(k, 'day_pos') is not None and fn_(k, 'day_pos') < 40)
                                                 or (fn_(k, 'near_high') is not None and -2 <= fn_(k, 'near_high') <= 2)
                                                 or (fn_(k, 'loc20') is not None and fn_(k, 'loc20') <= 10)),
    }
    for name, pred in tests.items():
        kept, dropped = drop(pred)
        res[name] = {'kept': kept, 'dropped': dropped}

    json.dump(res, open(ROOT / 'research/handover/_r140_location_filters.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    lg = open(ROOT / 'research/handover/_r140_location_filters.txt', 'w', encoding='utf-8')
    b = res['baseline']
    lg.write(f"=== R140 位置过滤器证伪 — 腿池 {len(rows)} (基线 avg={b['avg']}% PF={b['pf']}) ===\n")
    for name in tests:
        k, d = res[name]['kept'], res[name]['dropped']
        lg.write(f"  {name:32s} 留 n={k.get('n',0):5d} avg={k.get('avg','-')}% PF={k.get('pf','-')} | "
                 f"剔 n={d.get('n',0):4d} avg={d.get('avg','-')}% PF={d.get('pf','-')}\n")
    lg.write('写出 _r140_location_filters.json\n')
    lg.close()


if __name__ == '__main__':
    main()
