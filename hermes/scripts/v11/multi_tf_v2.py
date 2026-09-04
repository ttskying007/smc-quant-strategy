#!/usr/bin/env python3
"""
SMC 多周期选股系统 V1.0
周线SMC信号 → 日线SMC序列组合 → 60min入场定位
周线从日线合成 (无需API)
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20, _calc_atr

KLINE_DIR = Path('/root/.hermes/kline_cache')
M60_DIR = KLINE_DIR / 'm60'
OUT_DIR = Path('/root/.hermes/smc_opt_v21')
OUT_DIR.mkdir(exist_ok=True)

# ════════════════════════════════════════════
# 1. 日线→周线合成
# ════════════════════════════════════════════

def daily_to_weekly(daily_ohlcv):
    """日线合成周线OHLC."""
    if len(daily_ohlcv) < 5:
        return []
    weekly = []
    # Group by calendar week (simplified: every 5 trading days)
    for i in range(0, len(daily_ohlcv), 5):
        chunk = daily_ohlcv[i:i+5]
        if len(chunk) < 3:  # skip partial weeks
            continue
        weekly.append({
            'o': chunk[0]['o'],
            'h': max(b['h'] for b in chunk),
            'l': min(b['l'] for b in chunk),
            'c': chunk[-1]['c'],
            't': chunk[-1].get('t', chunk[-1].get('date', str(i))),
        })
    return weekly

# ════════════════════════════════════════════
# 2. 周线SMC趋势 (用V20引擎)
# ════════════════════════════════════════════

def weekly_smc_trend(weekly_ohlcv):
    """周线SMC趋势: CHOCH/BOS方向 + 摆动结构."""
    if len(weekly_ohlcv) < 30:
        return 'neutral', {}
    
    sigs, st, _, _ = detect_all_signals_v20(weekly_ohlcv)
    tc = st['type_counts']
    
    # 趋势判断: CHOCH方向 + BOS方向 + 最新摆动结构
    choch_bull = tc.get('CHOCH_Bull', 0)
    choch_bear = tc.get('CHOCH_Bear', 0)
    bos_bull = tc.get('BOS_Bull', 0)
    bos_bear = tc.get('BOS_Bear', 0)
    
    # 最近一个CHOCH的方向
    recent_choch = [s for s in sigs if 'CHOCH' in s.type]
    last_choch_dir = None
    if recent_choch:
        last = recent_choch[-1]
        last_choch_dir = 'bull' if 'Bull' in last.type else 'bear'
    
    # 摆动结构: 最新HH/LL
    swings = st.get('swings', [])
    last_label = swings[-1]['label'] if swings else ''
    
    # 综合判断
    bullish_score = choch_bull + bos_bull
    bearish_score = choch_bear + bos_bear
    
    if last_choch_dir == 'bull' and bullish_score >= bearish_score:
        trend = 'bullish'
    elif last_choch_dir == 'bear' and bearish_score > bullish_score:
        trend = 'bearish'
    elif bullish_score > bearish_score * 1.5:
        trend = 'bullish'
    elif bearish_score > bullish_score * 1.5:
        trend = 'bearish'
    else:
        trend = 'neutral'
    
    info = {
        'choch_bull': choch_bull, 'choch_bear': choch_bear,
        'bos_bull': bos_bull, 'bos_bear': bos_bear,
        'last_choch': last_choch_dir,
        'last_swing': last_label,
        'signals': tc,
    }
    return trend, info

# ════════════════════════════════════════════
# 3. 日线SMC序列组合检测
# ════════════════════════════════════════════

SIGNAL_CATS = {
    'LIQUIDITY_LONG':  ['Sweep_SSL', 'EQL'],
    'LIQUIDITY_SHORT': ['Sweep_BSL', 'EQH'],
    'STRUCTURE_LONG':  ['CHOCH_Bull', 'BOS_Bull', 'MSS_Bull'],
    'STRUCTURE_SHORT': ['CHOCH_Bear', 'BOS_Bear', 'MSS_Bear'],
    'DEMAND_ZONE':     ['OB_Bull', 'FVG_Bull'],
    'SUPPLY_ZONE':     ['OB_Bear', 'FVG_Bear'],
}

PATTERNS = {
    'L→D':    {'stages': ['LIQUIDITY_LONG', 'DEMAND_ZONE'],     'gaps': [20], 'direction': 'long'},
    'S→D':    {'stages': ['STRUCTURE_LONG', 'DEMAND_ZONE'],     'gaps': [15], 'direction': 'long'},
    'L→S→D':  {'stages': ['LIQUIDITY_LONG','STRUCTURE_LONG','DEMAND_ZONE'], 'gaps':[30,15], 'direction':'long'},
    'L→D_s':  {'stages': ['LIQUIDITY_SHORT','SUPPLY_ZONE'],    'gaps': [20], 'direction': 'short'},
    'S→D_s':  {'stages': ['STRUCTURE_SHORT','SUPPLY_ZONE'],    'gaps': [15], 'direction': 'short'},
    'L→S→D_s':{'stages': ['LIQUIDITY_SHORT','STRUCTURE_SHORT','SUPPLY_ZONE'], 'gaps':[30,15], 'direction':'short'},
}

def detect_sequences(signals):
    """检测所有序列组合 (去重按entry_bar)."""
    sigs_by_bar = defaultdict(list)
    for s in signals:
        sigs_by_bar[s.idx].append(s)
    
    sequences = []
    for pat_name, pat in PATTERNS.items():
        stages = [SIGNAL_CATS[cat] for cat in pat['stages']]
        gaps = pat['gaps']
        
        for start_bar in sorted(sigs_by_bar.keys()):
            for s1 in [s for s in sigs_by_bar[start_bar] if s.type in stages[0]]:
                matched = [s1]; current = s1.idx; ok = True
                for si in range(1, len(stages)):
                    found = False
                    for bi in range(current+1, current+gaps[si-1]+1):
                        if bi in sigs_by_bar:
                            for cand in sigs_by_bar[bi]:
                                if cand.type in stages[si] and cand not in matched:
                                    matched.append(cand); current = bi; found = True; break
                        if found: break
                    if not found: ok = False; break
                if ok and len(matched) == len(stages):
                    sequences.append({'pattern': pat_name, 'direction': pat['direction'],
                                     'entry_bar': matched[-1].idx, 'entry_type': matched[-1].type})
    
    seen = set(); unique = []
    for seq in sorted(sequences, key=lambda x: x['entry_bar']):
        if seq['entry_bar'] not in seen:
            seen.add(seq['entry_bar']); unique.append(seq)
    return unique

# ════════════════════════════════════════════
# 4. 序列效果测试 (多窗口)
# ════════════════════════════════════════════

LOOKAHEAD = 5; TARGET = 2.0

def test_sequences(ohlcv, sequences, start_bar=0):
    """测试序列在未来N bar的命中率."""
    n = len(ohlcv)
    results = defaultdict(lambda: {'hits':0, 'total':0, 'returns':[]})
    
    for seq in sequences:
        bar = seq['entry_bar']
        if bar < start_bar: continue
        if bar + LOOKAHEAD >= n: continue
        
        entry_price = ohlcv[bar]['c']
        max_high = max(ohlcv[i]['h'] for i in range(bar+1, min(bar+LOOKAHEAD+1, n)))
        ret = (max_high - entry_price) / entry_price * 100
        
        results[seq['pattern']]['total'] += 1
        results[seq['pattern']]['returns'].append(ret)
        if ret >= TARGET:
            results[seq['pattern']]['hits'] += 1
    
    return {k: {'hits': v['hits'], 'total': v['total'],
                'rate': round(v['hits']/v['total'], 3),
                'avg_ret': round(sum(v['returns'])/len(v['returns']), 2)}
            for k, v in results.items() if v['total'] >= 3}

# ════════════════════════════════════════════
# 5. 主流程
# ════════════════════════════════════════════

daily_files = sorted(KLINE_DIR.glob('*_daily_300.json'))
print(f"Daily files: {len(daily_files)}")
print(f"60min files: {len(list(M60_DIR.glob('*_m60.json'))) if M60_DIR.exists() else 0}")

stock_profiles = {}
t0 = time.time()

for fi, df in enumerate(daily_files):
    sym = df.stem.replace('_daily_300', '')
    try:
        daily = json.loads(df.read_bytes())
        if len(daily) < 50: continue
    except: continue
    
    # ── 周线SMC ──
    weekly = daily_to_weekly(daily)
    w_trend, w_info = weekly_smc_trend(weekly) if len(weekly) >= 30 else ('neutral', {})
    
    # ── 日线SMC序列 ──
    sigs, st, _, _ = detect_all_signals_v20(daily)
    sequences = detect_sequences(sigs)
    
    if not sequences:
        continue
    
    # ── 多窗口测试 ──
    n = len(daily)
    windows = {
        'full': 0,
        'mid': max(0, n-150),
        'recent': max(0, n-50),
    }
    
    profile = {
        'symbol': sym,
        'weekly_trend': w_trend,
        'weekly_signals': w_info,
        'daily_signals': st['type_counts'],
        'daily_sequences': len(sequences),
        'windows': {},
    }
    
    for wname, start in windows.items():
        perf = test_sequences(daily, sequences, start)
        if perf:
            profile['windows'][wname] = perf
    
    if profile['windows']:
        # 选最佳long组合 (full窗口)
        full = profile['windows'].get('full', {})
        best_pat = None; best_rate = 0
        for pat, stats in full.items():
            if PATTERNS[pat]['direction'] == 'long' and stats['rate'] > best_rate:
                best_rate = stats['rate']; best_pat = pat
        if best_pat:
            profile['best_pattern'] = best_pat
            profile['best_rate'] = best_rate
            profile['best_total'] = full[best_pat]['total']
        
        stock_profiles[sym] = profile
    
    if (fi+1) % 500 == 0:
        print(f"  [{fi+1}/{len(daily_files)}] {time.time()-t0:.0f}s profiles={len(stock_profiles)}")

elapsed = time.time() - t0

# ════════════════════════════════════════════
# 6. 报告
# ════════════════════════════════════════════

print(f"\n{'='*70}")
print(f"  SMC 多周期选股系统 V1.0 ({elapsed:.0f}s)")
print(f"{'='*70}")

# 周线趋势分布
trend_dist = defaultdict(int)
for p in stock_profiles.values():
    trend_dist[p['weekly_trend']] += 1
print(f"\n  周线SMC趋势: bullish={trend_dist['bullish']} bearish={trend_dist['bearish']} neutral={trend_dist['neutral']}")

# 最佳组合 × 周线趋势
pat_trend = defaultdict(lambda: defaultdict(int))
rate_sum = defaultdict(lambda: defaultdict(list))
for p in stock_profiles.values():
    bp = p.get('best_pattern')
    if bp:
        pat_trend[p['weekly_trend']][bp] += 1
        rate_sum[p['weekly_trend']][bp].append(p.get('best_rate', 0))

print(f"\n  周线趋势 × 最佳日线组合:")
for trend in ['bullish', 'bearish', 'neutral']:
    pats = pat_trend[trend]
    if not pats: continue
    total = sum(pats.values())
    print(f"    {trend:8s} ({total}只):")
    for pat, count in sorted(pats.items(), key=lambda x: -x[1])[:4]:
        avg_rate = sum(rate_sum[trend][pat])/len(rate_sum[trend][pat]) if rate_sum[trend][pat] else 0
        print(f"      {pat:10s} {count:>4d}只 ({count/total*100:4.0f}%) avg_rate={avg_rate:.0%}")

# 60min覆盖
m60_stocks = set()
for p in stock_profiles.values():
    if (M60_DIR / f'{p["symbol"]}_m60.json').exists():
        m60_stocks.add(p['symbol'])
print(f"\n  60min覆盖: {len(m60_stocks)}/{len(stock_profiles)}")

# 选股示例
print(f"\n  选股示例 (bullish + L→D + rate≥80%):")
candidates = [(sym, p) for sym, p in stock_profiles.items()
              if p['weekly_trend']=='bullish' and p.get('best_pattern')=='L→D' and p.get('best_rate',0)>=0.8]
for sym, p in sorted(candidates, key=lambda x: -x[1].get('best_rate',0))[:15]:
    print(f"    {sym:12s} weekly={p['weekly_trend']} pattern={p.get('best_pattern','?')} rate={p.get('best_rate',0):.0%} n={p.get('best_total',0)}")

# 窗口稳定性
print(f"\n  时间窗口稳定性 (full→recent):")
stable = improved = degraded = 0
for p in stock_profiles.values():
    full = p['windows'].get('full', {})
    recent = p['windows'].get('recent', {})
    for pat in full:
        if pat in recent and full[pat]['total'] >= 5:
            delta = recent[pat]['rate'] - full[pat]['rate']
            if delta > 0.05: improved += 1
            elif delta < -0.05: degraded += 1
            else: stable += 1
total = stable+improved+degraded
print(f"    stable={stable}({stable/total*100:.0f}%) improved={improved}({improved/total*100:.0f}%) degraded={degraded}({degraded/total*100:.0f}%)")

# ═══ 保存 ═══
output = {
    'meta': {'version': '1.0', 'date': time.strftime('%Y-%m-%d'), 'stocks': len(stock_profiles)},
    'profiles': stock_profiles,
}
json.dump(output, open(OUT_DIR / 'multi_tf_stock_db.json', 'w'), ensure_ascii=False)
print(f"\n  数据库: {OUT_DIR / 'multi_tf_stock_db.json'}")
print(f"  大小: {OUT_DIR / 'multi_tf_stock_db.json'}")
