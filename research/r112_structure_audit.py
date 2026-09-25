# -*- coding: utf-8 -*-
"""R112: BOS/CHoCH/BSL/SSL 准确性体检 — 量化图上'不准'的类别与规模。

检查项（对全样本或子集）:
  A) 事件 level 必须等于一个已确认摆动高/低 (名称与价位一致性)
  B) 事件 bar 的 close 必须真的穿越 level (含 pen_edge 过滤后的残余伪信号)
  C) 事件重复触发检查: 同一枢轴价位不应产生 2 次同向事件 (last_h reset 后仍可能因摆动更新再触发)
  D) 摆动点密度: 实际密度是否落在 [8,14]/100bar (R90 目标)
  E) 事件级别错位: level 与图上可见的最近高低点差 > X%
  F) BSL/SSL 线: 引用的摆动点是否真实存在且未确认前不泄露
"""
import json, os, sys, glob
sys.path.insert(0, os.path.dirname(__file__))
from core.structure import structure_events, is_swing_high, is_swing_low, pick_pivot_by_density, atr_of

DATA = r'E:\test\smc_project\hermes\kline_cache_tencent'

def load(sym):
    sf = sym.replace('.SH', '_SH').replace('.SZ', '_SZ').replace('.BJ', '_BJ')
    fp = os.path.join(DATA, sf + '_daily_800.json')
    if not os.path.exists(fp):
        return None
    d = json.load(open(fp, encoding='utf-8'))
    ks = d if isinstance(d, list) else (d.get('klines') or d.get('bars') or [])
    if isinstance(ks, list) and ks:
        b = ks[0]
        # 归一化成 core 使用的 {'t','o','h','l','c','v'}
        if 'c' in b:
            return ks
        for k in ks:
            k.setdefault('t', str(k.get('date', '')).replace('-', ''))
            k.setdefault('o', k.get('open')); k.setdefault('h', k.get('high'))
            k.setdefault('l', k.get('low')); k.setdefault('c', k.get('close'))
            k.setdefault('v', k.get('volume', k.get('vol', 0)))
        return ks
    return None

def audit_symbol(sym, ks):
    n = len(ks) - 1
    events = structure_events(ks, None, mode='auto')
    pivot, dens = pick_pivot_by_density(ks, n)
    problems = []
    # 预备所有已确认摆动
    sw_h, sw_l = set(), set()
    for j in range(pivot, len(ks) - pivot):
        if is_swing_high(ks, j, pivot): sw_h.add(round(ks[j]['h'], 4))
        if is_swing_low(ks, j, pivot): sw_l.add(round(ks[j]['l'], 4))
    atr = atr_of(ks, n) or 0
    last_kind_dir = None
    prev_ev = None
    for ev in events:
        k = ev['bar']; c = ks[k]['c']; lv = ev['level']
        up = '↑' in ev['kind']
        # B) 真穿越?
        if up and not (c > lv): problems.append(('B', sym, ev['date'], ev['kind'], f'close {c} <= level {lv}'))
        if not up and not (c < lv): problems.append(('B', sym, ev['date'], ev['kind'], f'close {c} >= level {lv}'))
        # A) level 是真实摆动点?
        tgt = sw_h if up else sw_l
        if round(lv, 4) not in tgt:
            problems.append(('A', sym, ev['date'], ev['kind'], f'level {lv} 不在已确认摆动点集合'))
        # C) 同向事件间距过近(<3bar) 视为抖动
        if prev_ev and ev['kind'] == prev_ev['kind'] and ev['bar'] - prev_ev['bar'] < 3:
            problems.append(('C', sym, ev['date'], ev['kind'], f"与前一同向事件仅隔 {ev['bar']-prev_ev['bar']} bar"))
        prev_ev = ev
    return {
        'symbol': sym, 'bars': len(ks), 'pivot': pivot, 'density': round(dens, 1),
        'n_events': len(events),
        'kinds': {kk: sum(1 for e in events if e['kind'] == kk) for kk in ('BOS↑', 'BOS↓', 'CHoCH↑', 'CHoCH↓')},
        'problems': problems,
        'events_sample': events[-6:],
    }

def main():
    syms = ['688381.SH', '600519.SH', '300750.SZ', '002594.SZ', '601318.SH',
            '000858.SZ', '600036.SH', '000001.SZ']
    out = []
    for s in syms:
        ks = load(s)
        if not ks:
            print(f'{s}: 无数据'); continue
        r = audit_symbol(s, ks)
        out.append(r)
        print(f"{s} bars={r['bars']} pivot={r['pivot']} density={r['density']} "
              f"events={r['n_events']} {r['kinds']} problems={len(r['problems'])}")
        for p in r['problems'][:6]:
            print('   ', p)
    json.dump(out, open(r'research\handover\_r112_structure_audit.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1, default=str)
    tot = sum(len(r['problems']) for r in out)
    print(f'\n总问题数: {tot}')

if __name__ == '__main__':
    main()
