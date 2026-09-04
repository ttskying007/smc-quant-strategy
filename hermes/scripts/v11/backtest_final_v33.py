#!/usr/bin/env python3
"""
最终全量回测 V3.3 — 数据完全后运行
=====================================
- 等周线数据补全后 (目标: 4800+)
- 周期: 日线 + 60min (如有)
- 窗口: full / mid(150) / recent(50)  
- 模式: L→D, S→D
- 输出: 个股top-3 × 窗口 × 周期, 全局聚合
"""
import json, time
from pathlib import Path
from collections import defaultdict
import sys

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20

KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v21')
OUT.mkdir(exist_ok=True)

CATS = {
    'L_LONG':  ['Sweep_SSL', 'EQL'],
    'S_LONG':  ['CHOCH_Bull', 'BOS_Bull', 'MSS_Bull'],
    'D_ZONE':  ['OB_Bull', 'FVG_Bull'],
}
PATTERNS = {
    'L→D': ('L_LONG', 'D_ZONE', [20], 'long'),
    'S→D': ('S_LONG', 'D_ZONE', [15], 'long'),
}

def daily_to_weekly(daily):
    w = []
    for i in range(0, len(daily), 5):
        c = daily[i:i+5]
        if len(c) >= 3:
            w.append({'o': c[0]['o'], 'h': max(b['h'] for b in c),
                      'l': min(b['l'] for b in c), 'c': c[-1]['c']})
    return w

def weekly_smc(weekly):
    if len(weekly) < 20: return 'neutral', {}
    sigs, st, _, _ = detect_all_signals_v20(weekly)
    tc = st['type_counts']
    cb = tc.get('CHOCH_Bull', 0); cbr = tc.get('CHOCH_Bear', 0)
    bb = tc.get('BOS_Bull', 0); bbr = tc.get('BOS_Bear', 0)
    last = [s for s in sigs if 'CHOCH' in s.type]
    last_dir = 'bull' if last and 'Bull' in last[-1].type else ('bear' if last and 'Bear' in last[-1].type else None)
    if last_dir == 'bull' and cb + bb >= cbr + bbr: return 'bullish', tc
    if last_dir == 'bear' and cbr + bbr > cb + bb: return 'bearish', tc
    if cb + bb > (cbr + bbr) * 1.5: return 'bullish', tc
    if cbr + bbr > (cb + bb) * 1.5: return 'bearish', tc
    return 'neutral', tc

def detect_sequences(signals):
    sbb = defaultdict(list)
    for s in signals: sbb[s.idx].append(s)
    seqs = []
    for pn, pat_data in PATTERNS.items():
        keys = list(pat_data)
        gaps = keys[-2]; stage_keys = keys[:-2]
        stages = [CATS[sk] for sk in stage_keys]
        for sb in sorted(sbb):
            for sig in [s for s in sbb[sb] if s.type in stages[0]]:
                m = [sig]; c = sig.idx; ok = True
                for si in range(1, len(stages)):
                    fnd = False
                    for bi in range(c + 1, c + gaps[si - 1] + 1):
                        if bi in sbb:
                            for cand in sbb[bi]:
                                if cand.type in stages[si] and cand not in m:
                                    m.append(cand); c = bi; fnd = True; break
                        if fnd: break
                    if not fnd: ok = False; break
                if ok and len(m) == len(stages):
                    seqs.append({'p': pn, 'd': 'long', 'bar': m[-1].idx})
    seen = set(); u = []
    for s in sorted(seqs, key=lambda x: x['bar']):
        if s['bar'] not in seen: seen.add(s['bar']); u.append(s)
    return u

def backtest(ohlcv, seqs, start=0, target=2.0, lookahead=5):
    n = len(ohlcv)
    r = defaultdict(lambda: {'hits': 0, 'total': 0, 'returns': [], 'pnls': []})
    for s in seqs:
        b = s['bar']
        if b < start or b + lookahead >= n: continue
        ep = ohlcv[b]['c']
        max_h = max(ohlcv[i]['h'] for i in range(b + 1, min(b + lookahead + 1, n)))
        ret = (max_h - ep) / ep * 100
        r[s['p']]['total'] += 1
        r[s['p']]['returns'].append(ret)
        if ret >= target: r[s['p']]['hits'] += 1
    return {k: {'hits': v['hits'], 'total': v['total'],
                'rate': round(v['hits'] / v['total'], 3),
                'avg_ret': round(sum(v['returns']) / len(v['returns']), 2)}
            for k, v in r.items() if v['total'] >= 3}

# ═══ MAIN ═══
daily_files = sorted(KLINE.glob('*_daily_300.json'))
t0 = time.time()
all_results = {}

for fi, df in enumerate(daily_files):
    name = df.stem.replace('_daily_300', '')
    parts = name.rsplit('_', 1)
    sym = f'{parts[0]}.{parts[1]}' if len(parts) == 2 else name
    try:
        daily = json.loads(df.read_bytes())
        if len(daily) < 50: continue
    except: continue

    # Weekday: real preferred, synthetic fallback
    weekly_path = KLINE / f'{name}_weekly_200.json'
    if weekly_path.exists():
        try:
            weekly = json.loads(weekly_path.read_bytes())
            if len(weekly) < 20: weekly = daily_to_weekly(daily)
        except:
            weekly = daily_to_weekly(daily)
    else:
        weekly = daily_to_weekly(daily)

    w_trend, _ = weekly_smc(weekly)
    stock_result = {'sym': sym, 'w_trend': w_trend, 'cycles': {}}

    try:
        sigs_d, _, _, _ = detect_all_signals_v20(daily)
        seqs_d = detect_sequences(sigs_d)
    except:
        seqs_d = []

    if seqs_d:
        n = len(daily)
        wins = {'full': 0, 'mid': max(0, n - 150), 'recent': max(0, n - 50)}
        daily_result = {}
        for wn, start in wins.items():
            perf = backtest(daily, seqs_d, start)
            if perf: daily_result[wn] = perf
        if daily_result:
            stock_result['cycles']['daily'] = {'n_seqs': len(seqs_d), 'windows': daily_result}

    if stock_result['cycles']:
        all_results[sym] = stock_result

    if (fi + 1) % 500 == 0:
        print(f"  [{fi+1}/{len(daily_files)}] {time.time()-t0:.0f}s results={len(all_results)}")

elapsed = time.time() - t0

# ═══ REPORT ═══
print(f"\n{'='*65}")
print(f"  最终全量回测 V3.3 ({elapsed:.0f}s)")
print(f"  扫描: {len(daily_files)} → {len(all_results)}有效")

td = defaultdict(int)
for r in all_results.values(): td[r['w_trend']] += 1
print(f"  趋势: bullish={td['bullish']} bearish={td['bearish']} neutral={td['neutral']}")
print(f"{'='*65}")

# Aggregate by trend x pattern x window
for trend in ['bullish', 'bearish', 'neutral']:
    agg_full = defaultdict(lambda: {'hits': 0, 'total': 0})
    agg_mid = defaultdict(lambda: {'hits': 0, 'total': 0})
    agg_recent = defaultdict(lambda: {'hits': 0, 'total': 0})
    
    for r in all_results.values():
        if r['w_trend'] != trend: continue
        c = r['cycles'].get('daily', {})
        for wn, perf in c.get('windows', {}).items():
            for pat, stats in perf.items():
                target_agg = {'full': agg_full, 'mid': agg_mid, 'recent': agg_recent}[wn]
                target_agg[pat]['hits'] += stats['hits']
                target_agg[pat]['total'] += stats['total']
    
    if not any(agg_full.values()): continue
    print(f"\n  {trend}:")
    for pat in ['L→D', 'S→D']:
        fw = agg_full.get(pat, {})
        mw = agg_mid.get(pat, {})
        rw = agg_recent.get(pat, {})
        parts = []
        if fw.get('total', 0) >= 10:
            parts.append(f"full:{fw['hits']/fw['total']:.0%}({fw['total']})")
        if mw.get('total', 0) >= 10:
            parts.append(f"mid:{mw['hits']/mw['total']:.0%}({mw['total']})")
        if rw.get('total', 0) >= 5:
            parts.append(f"recent:{rw['hits']/rw['total']:.0%}({rw['total']})")
        if parts:
            print(f"    {pat:6s} {' | '.join(parts)}")

# ═══ SAVE ═══
json.dump({'meta': {'version': '3.3', 'date': time.strftime('%Y-%m-%d'),
                    'stocks': len(all_results)},
           'results': all_results},
          open(OUT / 'backtest_final_v33.json', 'w'), ensure_ascii=False)
print(f"\n  Saved: {OUT/'backtest_final_v33.json'}")
