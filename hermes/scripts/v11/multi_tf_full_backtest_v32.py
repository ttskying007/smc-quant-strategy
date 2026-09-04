#!/usr/bin/env python3
"""
全量多周期分窗口回测 V3.2
===========================
- 周线: 优先真实API数据, 缺失用日线合成
- 周期: 日线 + 60min
- 窗口: full / mid(150) / recent(50)
- 模式: L→D, S→D, L_D_s, S_D_s
- 输出: 个股明细 + 聚合报告
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

TARGET = 2.0; LOOKAHEAD = 5; MIN_SAMPLES = 3

CATS = {
    'L_LONG':  ['Sweep_SSL', 'EQL'],
    'L_SHORT': ['Sweep_BSL', 'EQH'],
    'S_LONG':  ['CHOCH_Bull', 'BOS_Bull', 'MSS_Bull'],
    'S_SHORT': ['CHOCH_Bear', 'BOS_Bear', 'MSS_Bear'],
    'D_ZONE':  ['OB_Bull', 'FVG_Bull'],
    'S_ZONE':  ['OB_Bear', 'FVG_Bear'],
}

PATTERNS = {
    'L→D':   ('L_LONG', 'D_ZONE', [20], 'long'),
    'S→D':   ('S_LONG', 'D_ZONE', [15], 'long'),
    'L_D_s': ('L_SHORT', 'S_ZONE', [20], 'short'),
    'S_D_s': ('S_SHORT', 'S_ZONE', [15], 'short'),
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
    if len(weekly) < 30: return 'neutral', {}
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
        gaps = keys[-2]
        stage_keys = keys[:-2]
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
                    seqs.append({'p': pn, 'd': PATTERNS[pn][-1], 'bar': m[-1].idx})
    seen = set(); u = []
    for s in sorted(seqs, key=lambda x: x['bar']):
        if s['bar'] not in seen: seen.add(s['bar']); u.append(s)
    return u

def backtest(ohlcv, seqs, start=0):
    n = len(ohlcv)
    r = defaultdict(lambda: {'hits': 0, 'total': 0, 'returns': []})
    for s in seqs:
        b = s['bar']
        if b < start or b + LOOKAHEAD >= n: continue
        ep = ohlcv[b]['c']
        max_high = max(ohlcv[i]['h'] for i in range(b + 1, min(b + LOOKAHEAD + 1, n)))
        ret = (max_high - ep) / ep * 100
        r[s['p']]['total'] += 1
        r[s['p']]['returns'].append(ret)
        if ret >= TARGET: r[s['p']]['hits'] += 1
    return {k: {'hits': v['hits'], 'total': v['total'],
                'rate': round(v['hits'] / v['total'], 3),
                'avg_ret': round(sum(v['returns']) / len(v['returns']), 2)}
            for k, v in r.items() if v['total'] >= MIN_SAMPLES}

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

    # Weekday: real or synthetic
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
    stock_result = {'sym': sym, 'w_trend': w_trend, 'w_source': 'real' if weekly_path.exists() else 'synthetic',
                    'cycles': {}}

    # ── Daily ──
    try:
        sigs_d, st_d, _, _ = detect_all_signals_v20(daily)
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
            stock_result['cycles']['daily'] = {
                'n_seqs': len(seqs_d), 'windows': daily_result}

    # ── 60min ──
    m60_path = KLINE / f'{name}_60min_500.json'
    if m60_path.exists():
        try:
            m60 = json.loads(m60_path.read_bytes())
            if len(m60) >= 30:
                sigs_60, st_60, _, _ = detect_all_signals_v20(m60)
                seqs_60 = detect_sequences(sigs_60)
                if seqs_60:
                    n60 = len(m60)
                    wins60 = {'full': 0, 'mid': max(0, n60 - 300), 'recent': max(0, n60 - 100)}
                    m60_result = {}
                    for wn, start in wins60.items():
                        perf = backtest(m60, seqs_60, start)
                        if perf: m60_result[wn] = perf
                    if m60_result:
                        stock_result['cycles']['60min'] = {
                            'n_seqs': len(seqs_60), 'windows': m60_result}
        except: pass

    if stock_result['cycles']:
        all_results[sym] = stock_result

    if (fi + 1) % 500 == 0:
        elapsed = time.time() - t0
        print(f"  [{fi+1}/{len(daily_files)}] {elapsed:.0f}s results={len(all_results)}")

elapsed = time.time() - t0

# ═══ REPORT ═══
print(f"\n{'='*70}")
print(f"  全量多周期分窗口回测 V3.2 ({elapsed:.0f}s)")
print(f"  扫描: {len(daily_files)} → {len(all_results)}只有效结果")
weekly_real = sum(1 for r in all_results.values() if r.get('w_source') == 'real')
weekly_syn = len(all_results) - weekly_real
print(f"  周线: {weekly_real}真实 + {weekly_syn}合成")
print(f"{'='*70}")

# ── 趋势分布 ──
td = defaultdict(int)
for r in all_results.values(): td[r['w_trend']] += 1
print(f"\n  周线趋势: bullish={td['bullish']} bearish={td['bearish']} neutral={td['neutral']}")

# ── 周期对比 (full窗口) ──
print(f"\n  【周期对比 (日线 vs 60min, full窗口)】")
for cycle in ['daily', '60min']:
    agg = defaultdict(lambda: {'hits': 0, 'total': 0})
    count = 0
    for r in all_results.values():
        c = r['cycles'].get(cycle, {})
        for wn, perf in c.get('windows', {}).items():
            if wn != 'full': continue
            for pat, stats in perf.items():
                agg[pat]['hits'] += stats['hits']
                agg[pat]['total'] += stats['total']
                count += 1
    print(f"  {cycle}: {count}股票-模式组合")
    for pat in ['L→D', 'S→D', 'L_D_s', 'S_D_s']:
        a = agg.get(pat)
        if a and a['total'] >= 10:
            wr = a['hits'] / a['total']
            print(f"    {pat:6s}  WR={wr:.1%}  N={a['total']}")

# ── 趋势×模式 (日线full) ──
print(f"\n  【周线趋势 × 模式 (日线full)】")
trend_pat = defaultdict(lambda: defaultdict(lambda: {'hits': 0, 'total': 0}))
for r in all_results.values():
    trend = r['w_trend']
    c = r['cycles'].get('daily', {})
    for wn, perf in c.get('windows', {}).items():
        if wn != 'full': continue
        for pat, stats in perf.items():
            trend_pat[trend][pat]['hits'] += stats['hits']
            trend_pat[trend][pat]['total'] += stats['total']

for trend in ['bullish', 'bearish', 'neutral']:
    tp = trend_pat.get(trend, {})
    if not tp: continue
    print(f"  {trend:8s}:")
    for pat in ['L→D', 'S→D', 'L_D_s', 'S_D_s']:
        pa = tp.get(pat)
        if pa and pa['total'] >= 5:
            print(f"    {pat:6s} WR={pa['hits']/pa['total']:.1%} N={pa['total']}")

# ── 窗口稳定性 ──
print(f"\n  【窗口稳定性 (full→mid→recent)】")
for cycle in ['daily', '60min']:
    win_rates = defaultdict(lambda: defaultdict(list))
    for r in all_results.values():
        c = r['cycles'].get(cycle, {})
        for wn, perf in c.get('windows', {}).items():
            for pat, stats in perf.items():
                if stats['total'] >= MIN_SAMPLES:
                    win_rates[pat][wn].append(stats['rate'])
    print(f"\n  {cycle}:")
    for pat in ['L→D', 'S→D']:
        wrp = win_rates.get(pat, {})
        if not wrp: continue
        rates = []
        for wn in ['full', 'mid', 'recent']:
            vals = wrp.get(wn, [])
            if vals: rates.append(f"{wn}={sum(vals)/len(vals):.0%}n={len(vals)}")
        if rates: print(f"    {pat:6s} {' → '.join(rates)}")

# ── Top个股 ──
print(f"\n  【Top 30 日线full窗口】")
daily_best = []
for sym, r in all_results.items():
    c = r['cycles'].get('daily', {})
    for wn, perf in c.get('windows', {}).items():
        if wn != 'full': continue
        for pat, stats in perf.items():
            daily_best.append((sym, pat, stats['rate'], stats['total'], r['w_trend']))
daily_best.sort(key=lambda x: (-x[2], -x[3]))
for i, (sym, pat, rate, total, trend) in enumerate(daily_best[:30]):
    print(f"  {i+1:2d}. {sym:12s} {trend:8s} {pat:6s} rate={rate:.0%} n={total}")

# ── 跨周期 ──
both = []
for sym, r in all_results.items():
    if 'daily' in r['cycles'] and '60min' in r['cycles']:
        d_perf = r['cycles']['daily']['windows'].get('full', {})
        m_perf = r['cycles']['60min']['windows'].get('full', {})
        if d_perf and m_perf:
            d_best = max(d_perf.items(), key=lambda x: x[1]['rate'])
            m_best = max(m_perf.items(), key=lambda x: x[1]['rate'])
            both.append((sym, r['w_trend'], d_best, m_best))
both.sort(key=lambda x: (-x[2][1]['rate'], -x[3][1]['rate']))
consistent = sum(1 for b in both if b[2][0] == b[3][0])
print(f"\n  【跨周期】双周期={len(both)} 模式一致={consistent}({consistent/max(len(both),1)*100:.0f}%)")
print(f"  Top10 双周期:")
for i, (sym, trend, db, mb) in enumerate(both[:10]):
    print(f"  {i+1:2d}. {sym:12s} {trend:8s} 日:{db[0]:6s}@{db[1]['rate']:.0%} 60m:{mb[0]:6s}@{mb[1]['rate']:.0%}")

# ═══ SAVE ═══
output = {
    'meta': {'version': '3.2', 'date': time.strftime('%Y-%m-%d'),
             'stocks': len(all_results), 'weekly_real': weekly_real,
             'weekly_synthetic': weekly_syn,
             'target': TARGET, 'lookahead': LOOKAHEAD},
    'results': all_results
}
json.dump(output, open(OUT / 'multi_tf_full_backtest_v32.json', 'w'), ensure_ascii=False)
print(f"\n  结果: {OUT/'multi_tf_full_backtest_v32.json'} ({len(all_results)} stocks)")
