#!/usr/bin/env python3
"""
SMC 全股票 × 多周期 × 多窗口 回测 V3.1
======================================
- 周期: 日线 + 60min
- 窗口: full(全量) / mid(最近150) / recent(最近50)
- 模式: L→D, S→D, L_D_s, S_D_s (序列组合)
- 趋势: 周线SMC (bullish/bearish/neutral)
- 输出: 个股最佳 + 聚合报告
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20

KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v21')
OUT.mkdir(exist_ok=True)

TARGET = 2.0
LOOKAHEAD = 5
MIN_SAMPLES = 3

# ====== 信号分类和序列模式 ======
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

# ====== 周线趋势判断 (从日线合成) ======
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
    if last_dir == 'bull' and cb + bb >= cbr + bbr:
        return 'bullish', tc
    if last_dir == 'bear' and cbr + bbr > cb + bb:
        return 'bearish', tc
    if cb + bb > (cbr + bbr) * 1.5:
        return 'bullish', tc
    if cbr + bbr > (cb + bb) * 1.5:
        return 'bearish', tc
    return 'neutral', tc

# ====== 序列检测 ======
def detect_sequences(signals):
    sbb = defaultdict(list)
    for s in signals:
        sbb[s.idx].append(s)
    seqs = []
    for pn, pat_data in PATTERNS.items():
        keys = list(pat_data)
        direction = keys[-1]
        gaps = keys[-2]
        stage_keys = keys[:-2]
        stages = [CATS[sk] for sk in stage_keys]
        for sb in sorted(sbb):
            for sig in [s for s in sbb[sb] if s.type in stages[0]]:
                m = [sig]
                c = sig.idx
                ok = True
                for si in range(1, len(stages)):
                    fnd = False
                    for bi in range(c + 1, c + gaps[si - 1] + 1):
                        if bi in sbb:
                            for cand in sbb[bi]:
                                if cand.type in stages[si] and cand not in m:
                                    m.append(cand)
                                    c = bi
                                    fnd = True
                                    break
                        if fnd:
                            break
                    if not fnd:
                        ok = False
                        break
                if ok and len(m) == len(stages):
                    seqs.append({'p': pn, 'd': direction, 'bar': m[-1].idx})
    seen = set()
    u = []
    for s in sorted(seqs, key=lambda x: x['bar']):
        if s['bar'] not in seen:
            seen.add(s['bar'])
            u.append(s)
    return u

# ====== 回测测试 ======
def backtest(ohlcv, seqs, start=0):
    n = len(ohlcv)
    results = defaultdict(lambda: {'hits': 0, 'total': 0, 'returns': []})
    for s in seqs:
        b = s['bar']
        if b < start or b + LOOKAHEAD >= n:
            continue
        ep = ohlcv[b]['c']
        # T+1 compliant: buy at close, check next bars
        max_high = max(ohlcv[i]['h'] for i in range(b + 1, min(b + LOOKAHEAD + 1, n)))
        ret = (max_high - ep) / ep * 100
        results[s['p']]['total'] += 1
        results[s['p']]['returns'].append(ret)
        if ret >= TARGET:
            results[s['p']]['hits'] += 1
    return {k: {'hits': v['hits'], 'total': v['total'],
                'rate': round(v['hits'] / v['total'], 3),
                'avg_ret': round(sum(v['returns']) / len(v['returns']), 2)}
            for k, v in results.items() if v['total'] >= MIN_SAMPLES}

# ====== 主循环 ======
daily_files = sorted(KLINE.glob('*_daily_300.json'))
t0 = time.time()
all_results = {}  # {symbol: {周期: {窗口: {模式: {hits,total,rate,avg_ret}}}}}

processed = 0
for fi, df in enumerate(daily_files):
    sym = df.stem.replace('_daily_300', '')
    try:
        daily = json.loads(df.read_bytes())
        if len(daily) < 50: continue
    except:
        continue

    # 周线趋势
    weekly = daily_to_weekly(daily)
    w_trend, _ = weekly_smc(weekly)

    stock_result = {'w_trend': w_trend, 'cycles': {}}

    # ---- 日线 ----
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
            if perf:
                daily_result[wn] = perf
        if daily_result:
            stock_result['cycles']['daily'] = {
                'n_seqs': len(seqs_d),
                'n_signals': st_d.get('total', 0),
                'windows': daily_result
            }

    # ---- 60min ----
    m60_path = KLINE / f'{sym}_60min_500.json'
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
                        if perf:
                            m60_result[wn] = perf
                    if m60_result:
                        stock_result['cycles']['60min'] = {
                            'n_seqs': len(seqs_60),
                            'n_signals': st_60.get('total', 0),
                            'windows': m60_result
                        }
        except:
            pass

    if stock_result['cycles']:
        all_results[sym] = stock_result
        processed += 1

    if (fi + 1) % 500 == 0:
        elapsed = time.time() - t0
        print(f"  [{fi+1}/{len(daily_files)}] {elapsed:.0f}s stocks_with_result={processed}")

elapsed = time.time() - t0

# ====== 输出报告 ======
print(f"\n{'='*70}")
print(f"  SMC 全股票 × 多周期 × 多窗口 回测 V3.1 ({elapsed:.0f}s)")
print(f"  扫描: {len(daily_files)} → {processed}只有效结果")
print(f"{'='*70}")

# --- 个股最佳摘要 ---
print(f"\n  个股最佳组合 (每只股票 × 每个周期 × 每个窗口, 按full窗口rate排序):")

# daily best
daily_stocks = []
for sym, r in all_results.items():
    dc = r['cycles'].get('daily', {})
    for wn, perf in dc.get('windows', {}).items():
        for pat, stats in perf.items():
            daily_stocks.append((sym, 'daily', wn, pat, stats['rate'], stats['total'], r['w_trend']))

# Top 30
daily_stocks.sort(key=lambda x: (-x[4], -x[5]))
print(f"\n  【日线 Top 30】")
for i, (sym, cyc, wn, pat, rate, total, trend) in enumerate(daily_stocks[:30]):
    print(f"  {i+1:2d}. {sym:12s} {trend:8s} {pat:6s}@{wn:6s} rate={rate:.0%} n={total}")

# 60min best
m60_stocks = []
for sym, r in all_results.items():
    mc = r['cycles'].get('60min', {})
    for wn, perf in mc.get('windows', {}).items():
        for pat, stats in perf.items():
            m60_stocks.append((sym, '60min', wn, pat, stats['rate'], stats['total'], r['w_trend']))

m60_stocks.sort(key=lambda x: (-x[4], -x[5]))
print(f"\n  【60min Top 30】")
for i, (sym, cyc, wn, pat, rate, total, trend) in enumerate(m60_stocks[:30]):
    print(f"  {i+1:2d}. {sym:12s} {trend:8s} {pat:6s}@{wn:6s} rate={rate:.0%} n={total}")

# --- 周期对比 ---
print(f"\n  【周期对比 (aggregate by cycle × pattern)】")
for cycle in ['daily', '60min']:
    agg = defaultdict(lambda: {'hits': 0, 'total': 0, 'returns': []})
    count = 0
    for sym, r in all_results.items():
        c = r['cycles'].get(cycle, {})
        for wn, perf in c.get('windows', {}).items():
            if wn != 'full': continue
            for pat, stats in perf.items():
                agg[pat]['hits'] += stats['hits']
                agg[pat]['total'] += stats['total']
                count += 1
    print(f"  {cycle}: {count} stock-pattern combinations")
    for pat in ['L→D', 'S→D', 'L_D_s', 'S_D_s']:
        a = agg.get(pat)
        if a and a['total'] >= 10:
            wr = a['hits'] / a['total']
            print(f"    {pat:6s}  WR={wr:.1%}  N={a['total']}")

# --- 窗口稳定性 ---
print(f"\n  【窗口稳定性 (同一模式在full→mid→recent的变化)】")
for cycle in ['daily', '60min']:
    win_rates = defaultdict(lambda: defaultdict(list))
    for sym, r in all_results.items():
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
            if vals:
                rates.append(f"{wn}={sum(vals)/len(vals):.0%}(n={len(vals)})")
        if rates:
            print(f"    {pat:6s} {' → '.join(rates)}")

# --- 趋势过滤效果 ---
print(f"\n  【周线趋势过滤效果 (仅日线full窗口)】")
trend_agg = defaultdict(lambda: defaultdict(lambda: {'hits': 0, 'total': 0}))
for sym, r in all_results.items():
    trend = r['w_trend']
    c = r['cycles'].get('daily', {})
    for wn, perf in c.get('windows', {}).items():
        if wn != 'full': continue
        for pat, stats in perf.items():
            trend_agg[trend][pat]['hits'] += stats['hits']
            trend_agg[trend][pat]['total'] += stats['total']

for trend in ['bullish', 'bearish', 'neutral']:
    ta = trend_agg.get(trend, {})
    print(f"  {trend:8s}:")
    for pat in ['L→D', 'S→D', 'L_D_s', 'S_D_s']:
        pa = ta.get(pat)
        if pa and pa['total'] >= 5:
            wr = pa['hits'] / pa['total']
            print(f"    {pat:6s} WR={wr:.1%} N={pa['total']}")

# --- 跨周期一致性 ---
print(f"\n  【跨周期一致性 (日线+60min同股票对比)】")
both = []
for sym, r in all_results.items():
    if 'daily' in r['cycles'] and '60min' in r['cycles']:
        # Get best pattern in daily full
        d_perf = r['cycles']['daily']['windows'].get('full', {})
        m_perf = r['cycles']['60min']['windows'].get('full', {})
        if d_perf and m_perf:
            d_best = max(d_perf.items(), key=lambda x: x[1]['rate'])
            m_best = max(m_perf.items(), key=lambda x: x[1]['rate'])
            both.append((sym, r['w_trend'], d_best, m_best))

both.sort(key=lambda x: (-x[2][1]['rate'], -x[3][1]['rate']))
print(f"  双周期覆盖: {len(both)}只")
consistent = sum(1 for b in both if b[2][0] == b[3][0])
print(f"  最佳模式相同: {consistent}只 ({consistent/max(len(both),1)*100:.0f}%)")
daily_better = sum(1 for b in both if b[2][1]['rate'] > b[3][1]['rate'])
print(f"  日线更优: {daily_better}只  |  60min更优: {len(both)-daily_better}只")

# Top dual-cycle picks
print(f"\n  Top 10 双周期高分:")
for i, (sym, trend, d_best, m_best) in enumerate(both[:10]):
    print(f"  {i+1:2d}. {sym:12s} {trend:8s} 日:{d_best[0]:6s}@{d_best[1]['rate']:.0%}  60min:{m_best[0]:6s}@{m_best[1]['rate']:.0%}")

# ====== 保存 ======
output = {
    'meta': {'version': '3.1', 'date': time.strftime('%Y-%m-%d'),
             'stocks_scanned': len(daily_files),
             'stocks_with_results': processed,
             'stocks_with_60min': sum(1 for r in all_results.values() if '60min' in r.get('cycles', {})),
             'target_pct': TARGET, 'lookahead': LOOKAHEAD, 'elapsed_s': int(elapsed)},
    'results': all_results
}
json.dump(output, open(OUT / 'cross_cycle_window_backtest.json', 'w'), ensure_ascii=False)
print(f"\n  结果已保存: {OUT / 'cross_cycle_window_backtest.json'}")
print(f"  总股票: {processed}  含60min: {output['meta']['stocks_with_60min']}")
