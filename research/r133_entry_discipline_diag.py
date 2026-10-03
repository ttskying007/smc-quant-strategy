# -*- coding: utf-8 -*-
"""R133: 入场链纪律诊断 — 全量 v22 腿违规统计 (用户 2026-10-24 投诉验证)。

投诉:
  1. 仍再创新低、未破前高就进场
  2. 入场未等"破前高→回踩POI"
  3. 趋势延续的回踩也没有

数据: combo_v22_trades.csv (1844 腿, chain_json/events/breakout/retrace 已在列, 纯因果口径)。

判定(每腿, 全部基于信号日因果链列):
  A. 破前高门控: breakout_kind ∈ {BOS↑, CHoCH↑} 才算已破前高;
     count_broken_high_miss = 缺失/BOS↓/CHoCH↓
  B. 回踩校验: retrace_state == 'retrace_ok' (回踩到突破水平 1.005 内)
  C. POI 回踩: 买入价落在近 OB(demand) 箱 或 bull FVG 箱 内 (chain_json.ob/fvg_bull,
     容差 2%) — 三者至少其一 (ob|fvg|breakout level)
  D. 创新低进场: 用 last_event_kind=='BOS↓'/'CHoCH↓' 且 trend_state in (down|bear..)
     近似; 精确用 klines 复算 20-bar 新低 (signal_date 当日 low 是否 ≤ min(l, 20bars))

输出:
  - research/combo_v22_entry_discipline.csv (逐腿违规标记)
  - research/handover/_r133_entry_discipline.json (汇总)
"""
import csv, json, sys, io, os
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(r'E:\test\smc_project')
KT = ROOT / 'hermes/kline_cache_tencent'


def load_bars(sym):
    sf = sym.replace('.SH', '_SH').replace('.SZ', '_SZ').replace('.BJ', '_BJ')
    fp = KT / (sf + '_daily_800.json')
    if not fp.exists():
        return None
    d = json.load(open(fp, encoding='utf-8'))
    raw = d if isinstance(d, list) else (d.get('klines') or d.get('bars') or [])
    if not raw:
        return None
    first = raw[0]
    if 'h' in first:
        return [{'t': str(b.get('t', b.get('date', '')))[:10].replace('-', ''),
                 'o': float(b['o']), 'h': float(b['h']), 'l': float(b['l']),
                 'c': float(b['c']), 'v': float(b.get('v', 0))} for b in raw]
    return [{'t': str(b.get('t', b.get('date', '')))[:10].replace('-', ''),
             'o': float(b.get('open', 0)), 'h': float(b.get('high', 0)),
             'l': float(b.get('low', 0)), 'c': float(b.get('close', 0)),
             'v': float(b.get('v', b.get('volume', 0)))} for b in raw]


def main():
    rows = list(csv.DictReader(open(ROOT / 'research/combo_v22_trades.csv', encoding='utf-8-sig')))
    print(f'v22 腿: {len(rows)}')

    kcache = {}
    out_rows = []
    st = {'total': len(rows), 'no_high_break': 0, 'no_retrace': 0,
          'no_poi_retrace': 0, 'new_low_entry': 0, 'all_violated': 0,
          'clean': 0}
    viol_pnl, clean_pnl = [], []

    for r in rows:
        sym = r['symbol']
        ep = float(r['buy_price'] or 0)
        ch = json.loads(r['chain_json']) if r.get('chain_json') else {}

        bk = r.get('breakout_kind') or ''
        rst = r.get('retrace_state') or ''

        # A. 破前高 (突破方向须为向上)
        high_broken = bk in ('BOS↑', 'CHoCH↑')

        # B. 回踩到突破水平
        retraced = (rst == 'retrace_ok')

        # C. POI: 入场价落在 OB demand 箱 / bull FVG 箱 / 突破水平 2% 带内
        poi_hit = False
        def _in(lx, hx, tol=0.02):
            return lx * (1 - tol) <= ep <= hx * (1 + tol)
        for ob in (ch.get('ob') or []):
            if 'demand' in str(ob.get('side', '')) and _in(float(ob['low']), float(ob['high'])):
                poi_hit = True
                break
        if not poi_hit:
            for bx in (ch.get('fvg_bull') or []):
                if _in(float(bx['low']), float(bx['high'])):
                    poi_hit = True
                    break
        if not poi_hit and r.get('breakout_price'):
            bp = float(r['breakout_price'])
            if abs(ep - bp) / bp <= 0.02:
                poi_hit = True
        if not high_broken:
            poi_hit = False  # 没破前高, POI 无从谈起

        # D. 信号日是否 20-bar 新低 (精确, 用 klines)
        if sym not in kcache:
            kcache[sym] = load_bars(sym)
        bs = kcache[sym]
        new_low = None
        if bs:
            dmap = {}
            for ix, b in enumerate(bs):
                dmap[b['t']] = ix
            sd = str(r.get('entry_date', '')).replace('-', '')
            si = dmap.get(sd)
            if si is not None and si >= 20:
                w = bs[si - 20: si + 1]
                new_low = (bs[si]['l'] <= min(b['l'] for b in w))

        viol = []
        if not high_broken:
            viol.append('NO_HIGH_BREAK')
        if not retraced:
            viol.append('NO_RETRACE')
        if not poi_hit:
            viol.append('NO_POI')
        if new_low:
            viol.append('NEW_LOW_ENTRY')

        np = float(r.get('net_pnl_pct') or 0)
        if viol:
            viol_pnl.append(np)
        else:
            clean_pnl.append(np)

        st['no_high_break'] += (not high_broken)
        st['no_retrace'] += (not retraced)
        st['no_poi_retrace'] += (not poi_hit)
        st['new_low_entry'] += bool(new_low)
        if high_broken and retraced and poi_hit and not new_low:
            st['clean'] += 1
        else:
            st['all_violated'] += 1

        out_rows.append({'symbol': sym, 'entry_date': r['entry_date'],
                         'buy_price': ep, 'net_pnl_pct': np,
                         'breakout_kind': bk, 'retrace_state': rst,
                         'last_event_kind': r.get('last_event_kind'),
                         'violations': ';'.join(viol) or 'CLEAN'})

    with open(ROOT / 'research/combo_v22_entry_discipline.csv', 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    def _avg(x):
        return round(sum(x) / len(x), 2) if x else None

    print('=== R133 入场链纪律诊断 (1844 腿) ===')
    print(f"A 未破前高进场   : {st['no_high_break']} ({st['no_high_break']/st['total']*100:.1f}%)")
    print(f"B 未回踩突破位   : {st['no_retrace']} ({st['no_retrace']/st['total']*100:.1f}%)")
    print(f"C 未回踩POI区    : {st['no_poi_retrace']} ({st['no_poi_retrace']/st['total']*100:.1f}%)")
    print(f"D 20bar新低进场  : {st['new_low_entry']} ({st['new_low_entry']/st['total']*100:.1f}%)")
    print(f"全合规(CLEAN)    : {st['clean']} ({st['clean']/st['total']*100:.2f}%)")
    print(f"违规腿 avg PnL   : {_avg(viol_pnl)}% (n={len(viol_pnl)})")
    print(f"合规腿 avg PnL   : {_avg(clean_pnl)}% (n={len(clean_pnl)})")

    json.dump({'stats': st, 'viol_avg': _avg(viol_pnl), 'clean_avg': _avg(clean_pnl),
               'viol_n': len(viol_pnl), 'clean_n': len(clean_pnl)},
              open(ROOT / 'research/handover/_r133_entry_discipline.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
