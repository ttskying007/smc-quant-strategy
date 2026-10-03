# -*- coding: utf-8 -*-
"""R135: 最小纪律过滤测试 — 只剔"创新低+结构仍向下"的腿, 保留动量主体。

背景: R134 证明严格纪律(破前高+回踩POI)证伪(avg-0.57 PF0.74)。
但 R133 诊断有 74 笔 20bar新低进场 + 大量 last_event=BOS↓ 进场的真问题。
本测试找"低风险过滤": 分层剔除后营收阻断测试:
  F1: 剔除 NEW_LOW_ENTRY (20bar新低当日) 腿
  F2: 剔除 last_event_kind ∈ {BOS↓, CHoCH↓} 的腿 (结构仍向下)
  F3: F1 ∩ F2 (最严"逆结构创新低"过滤)
  F4: 剔除 trend_state=down 且 last_event=BOS↓ (双确认逆结构)
数据源: r133 产物 combo_v22_entry_discipline.csv (逐腿违规标记) + trades CSV.
"""
import csv, json, sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(r'E:\test\smc_project')


def _stats(pnls):
    gp = sum(x for x in pnls if x > 0)
    gl = -sum(x for x in pnls if x < 0)
    return {'n': len(pnls), 'avg': round(sum(pnls) / len(pnls), 2) if pnls else None,
            'wr': round(sum(1 for x in pnls if x > 0) / len(pnls) * 100, 1) if pnls else None,
            'pf': round(gp / gl, 2) if gl > 0 else (99 if gp > 0 else 0)}


def main():
    disc = {(r['symbol'], r['entry_date']): r
            for r in csv.DictReader(open(ROOT / 'research/combo_v22_entry_discipline.csv', encoding='utf-8-sig'))}
    base = list(csv.DictReader(open(ROOT / 'research/combo_v22_trades.csv', encoding='utf-8-sig')))

    legs = []
    for r in base:
        key = (r['symbol'], r['entry_date'])
        d = disc.get(key, {})
        viol = set(str(d.get('violations', '')).split(';'))
        legs.append({'pnl': float(r.get('net_pnl_pct') or 0),
                     'new_low': 'NEW_LOW_ENTRY' in viol,
                     'ev_down': str(r.get('last_event_kind') or '') in ('BOS↓', 'CHoCH↓'),
                     'trend_down': r.get('trend_state') in ('down',)})

    all_pnl = [l['pnl'] for l in legs]
    print(f"基线 n={len(all_pnl)} avg={_stats(all_pnl)['avg']}% PF={_stats(all_pnl)['pf']}")

    tests = {
        'F1_剔新低进场': [l for l in legs if not l['new_low']],
        'F2_剔结构向下进场': [l for l in legs if not l['ev_down']],
        'F3_剔新低∧结构向下': [l for l in legs if not (l['new_low'] and l['ev_down'])],
        'F4_剔trend_down∧ev_down': [l for l in legs if not (l['trend_down'] and l['ev_down'])],
    }
    out = {}
    for name, keep in tests.items():
        pnls = [l['pnl'] for l in keep]
        dropped = len(legs) - len(keep)
        s = _stats(pnls)
        drop_pnls = [l['pnl'] for l in legs if l not in keep]
        ds = _stats(drop_pnls)
        print(f"{name}: 留 {s['n']} avg={s['avg']}% WR={s['wr']}% PF={s['pf']} | 剔 {dropped} 腿 avg={ds['avg']}% PF={ds['pf']}")
        out[name] = {'keep': s, 'drop_n': dropped, 'drop': ds}

    json.dump(out, open(ROOT / 'research/handover/_r135_minimal_discipline.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('写出 handover/_r135_minimal_discipline.json')


if __name__ == '__main__':
    main()
