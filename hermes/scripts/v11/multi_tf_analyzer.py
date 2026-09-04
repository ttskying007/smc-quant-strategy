#!/usr/bin/env python3
"""
SMC 多周期选股+监控系统 V1.0
=============================
周线定趋势 → 日线测信号组合 → 60min精确定位入场
输出: 每只股票的 最佳组合+预期表现+时间窗口稳定性
"""
import json, sys, time, urllib.request
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20, _calc_atr

HUBBLE = 'http://43.167.234.49:3101'
HUBBLE_KEY = '123456'
KLINE_DIR = Path('/root/.hermes/kline_cache')
WEEKLY_DIR = KLINE_DIR / 'weekly'
WEEKLY_DIR.mkdir(exist_ok=True)
OUT_DIR = Path('/root/.hermes/smc_opt_v21')
OUT_DIR.mkdir(exist_ok=True)

# ════════════════════════════════════════════
# 1. 周线数据下载
# ════════════════════════════════════════════

def download_weekly(symbol_raw):
    """下载单只股票周线. symbol_raw = '600519_SH'"""
    out_path = WEEKLY_DIR / f'{symbol_raw}_weekly.json'
    if out_path.exists():
        try:
            data = json.loads(out_path.read_bytes())
            if len(data) >= 30: return symbol_raw, True, len(data)
        except: pass
    
    parts = symbol_raw.split('_')
    if len(parts) != 2: return symbol_raw, False, 0
    code, market = parts
    market_map = {'SH': 'sh', 'SZ': 'sz', 'BJ': 'bj'}
    mkt = market_map.get(market, 'sh')
    full_code = f'{mkt}{code}'
    
    try:
        url = f'{HUBBLE}/api/cn/kline?code={full_code}&freq=W&key={HUBBLE_KEY}'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        if isinstance(data, dict) and data.get('code') == 0:
            items = data.get('data', [])
            if not items: return symbol_raw, False, 0
            klines = []
            for it in items:
                klines.append({
                    't': str(it.get('t', it.get('date', ''))),
                    'o': float(it.get('o', it.get('open', 0))),
                    'h': float(it.get('h', it.get('high', 0))),
                    'l': float(it.get('l', it.get('low', 0))),
                    'c': float(it.get('c', it.get('close', 0))),
                })
            out_path.write_text(json.dumps(klines))
            return symbol_raw, True, len(klines)
    except Exception as e:
        pass
    return symbol_raw, False, 0

# ════════════════════════════════════════════
# 2. 周线趋势判断
# ════════════════════════════════════════════

def weekly_trend(weekly_klines):
    """周线趋势: MA20斜率 + 价格位置."""
    if len(weekly_klines) < 20:
        return 'neutral'
    closes = [b['c'] for b in weekly_klines]
    ma20 = sum(closes[-20:]) / 20
    ma20_prev = sum(closes[-21:-1]) / 20
    current = closes[-1]
    
    slope = (ma20 - ma20_prev) / ma20_prev * 100 if ma20_prev > 0 else 0
    
    if slope > 0.5 and current > ma20:
        return 'bullish'
    elif slope < -0.5 and current < ma20:
        return 'bearish'
    else:
        return 'neutral'

# ════════════════════════════════════════════
# 3. 日线信号组合 (按时间顺序的SMC序列)
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
}

def detect_daily_sequences(signals, active_patterns=None):
    """检测日线上的SMC序列组合."""
    if active_patterns is None:
        active_patterns = list(PATTERNS.keys())
    
    sigs_by_bar = defaultdict(list)
    for s in signals:
        sigs_by_bar[s.idx].append(s)
    
    sequences = []
    for pat_name in active_patterns:
        pat = PATTERNS[pat_name]
        stages = [SIGNAL_CATS[cat] for cat in pat['stages']]
        gaps = pat['gaps']
        
        for start_bar in sorted(sigs_by_bar.keys()):
            s1_candidates = [s for s in sigs_by_bar[start_bar] if s.type in stages[0]]
            for s1 in s1_candidates:
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
                    entry_sig = matched[-1]
                    sequences.append({
                        'pattern': pat_name,
                        'direction': pat['direction'],
                        'entry_bar': entry_sig.idx,
                        'entry_type': entry_sig.type,
                        'zone_lower': entry_sig.lower,
                        'zone_upper': entry_sig.upper,
                    })
    
    # Dedup by entry bar
    seen = set(); unique = []
    for seq in sorted(sequences, key=lambda x: x['entry_bar']):
        if seq['entry_bar'] not in seen:
            seen.add(seq['entry_bar']); unique.append(seq)
    return unique

# ════════════════════════════════════════════
# 4. 60min数据加载
# ════════════════════════════════════════════

M60_DIR = KLINE_DIR / 'm60'
M60_DIR.mkdir(exist_ok=True)

def load_60min(symbol_raw):
    """加载60min数据."""
    fp = M60_DIR / f'{symbol_raw}_m60.json'
    if not fp.exists():
        return None
    try:
        data = json.loads(fp.read_bytes())
        if len(data) < 30: return None
        return data
    except:
        return None

# ════════════════════════════════════════════
# 5. 回测 (日线序列→未来收益评估)
# ════════════════════════════════════════════

LOOKAHEAD = 5; TARGET = 2.0

def test_sequence_performance(ohlcv, sequences):
    """测试每个序列的后续表现."""
    n = len(ohlcv)
    results = defaultdict(lambda: {'hits':0, 'total':0, 'returns':[]})
    
    for seq in sequences:
        bar = seq['entry_bar']
        if bar + LOOKAHEAD >= n: continue
        
        entry_price = ohlcv[bar]['c']
        max_high = max(ohlcv[i]['h'] for i in range(bar+1, min(bar+LOOKAHEAD+1, n)))
        ret = (max_high - entry_price) / entry_price * 100
        
        results[seq['pattern']]['total'] += 1
        results[seq['pattern']]['returns'].append(ret)
        if ret >= TARGET:
            results[seq['pattern']]['hits'] += 1
    
    return {k: {'hits': v['hits'], 'total': v['total'],
                'rate': round(v['hits']/v['total'], 3) if v['total'] else 0,
                'avg_ret': round(sum(v['returns'])/len(v['returns']), 2) if v['returns'] else 0}
            for k, v in results.items() if v['total'] >= 3}

# ════════════════════════════════════════════
# 6. 主流程
# ════════════════════════════════════════════

# Step 1: 下载周线 (并行)
print("Downloading weekly data...")
daily_files = sorted(KLINE_DIR.glob('*_daily_300.json'))
symbols = [f.stem.replace('_daily_300', '') for f in daily_files]
weekly_ok = 0

with ThreadPoolExecutor(max_workers=20) as ex:
    futures = {ex.submit(download_weekly, s): s for s in symbols}
    for f in as_completed(futures):
        sym, ok, n = f.result()
        if ok: weekly_ok += 1
        if weekly_ok % 500 == 0:
            print(f"  Weekly downloaded: {weekly_ok}/{len(symbols)}")

print(f"Weekly: {weekly_ok}/{len(symbols)} stocks")

# Step 2: 逐个股票分析
print("\nAnalyzing per-stock multi-tf...")
stock_profiles = {}
t0 = time.time()

for fi, df in enumerate(daily_files):
    sym = df.stem.replace('_daily_300', '')
    try:
        daily_ohlcv = json.loads(df.read_bytes())
        if len(daily_ohlcv) < 50: continue
    except: continue
    
    # 周线趋势
    weekly_path = WEEKLY_DIR / f'{sym}_weekly.json'
    trend = 'neutral'
    if weekly_path.exists():
        try:
            weekly_klines = json.loads(weekly_path.read_bytes())
            trend = weekly_trend(weekly_klines)
        except: pass
    
    # 日线信号+序列
    sigs, _, _, _ = detect_all_signals_v20(daily_ohlcv)
    sequences = detect_daily_sequences(sigs)
    
    if not sequences:
        continue
    
    # 多窗口测试
    n = len(daily_ohlcv)
    windows = {'full': (0, n), 'mid': (max(0, n-150), n), 'recent': (max(0, n-50), n)}
    
    profile = {'symbol': sym, 'weekly_trend': trend, 'windows': {}}
    
    for wname, (start, end) in windows.items():
        window_seqs = [s for s in sequences if s['entry_bar'] >= start]
        if not window_seqs: continue
        perf = test_sequence_performance(daily_ohlcv, window_seqs)
        if perf:
            profile['windows'][wname] = perf
    
    if profile['windows']:
        stock_profiles[sym] = profile
    
    if (fi+1) % 500 == 0:
        print(f"  [{fi+1}/{len(daily_files)}] {time.time()-t0:.0f}s profiles={len(stock_profiles)}")

elapsed = time.time() - t0

# ════════════════════════════════════════════
# 7. 汇总报告
# ════════════════════════════════════════════

print(f"\n{'='*70}")
print(f"  SMC 多周期选股系统 V1.0 ({elapsed:.0f}s)")
print(f"{'='*70}")
print(f"  周线数据: {weekly_ok}只")
print(f"  有序列组合的股票: {len(stock_profiles)}只")

# 按周线趋势分组
trend_groups = defaultdict(list)
for sym, p in stock_profiles.items():
    trend_groups[p['weekly_trend']].append(sym)

print(f"\n  周线趋势分布: bullish={len(trend_groups['bullish'])} bearish={len(trend_groups['bearish'])} neutral={len(trend_groups['neutral'])}")

# 每只股票的最佳组合 (full window, long only)
print(f"\n  个股最佳日线组合 (full window, long only):")
best_map = {}
for sym, p in stock_profiles.items():
    full = p['windows'].get('full', {})
    best_pat = None; best_rate = 0
    for pat, stats in full.items():
        if 'long' in PATTERNS.get(pat, {}).get('direction', '') and stats['rate'] > best_rate:
            best_rate = stats['rate']; best_pat = pat
    if best_pat:
        best_map[sym] = {'trend': p['weekly_trend'], 'pattern': best_pat,
                         'rate': best_rate, 'total': full[best_pat]['total']}

# Pattern distribution by trend
pat_by_trend = defaultdict(lambda: defaultdict(int))
for sym, info in best_map.items():
    pat_by_trend[info['trend']][info['pattern']] += 1

for trend in ['bullish', 'bearish', 'neutral']:
    pats = pat_by_trend[trend]
    if pats:
        total = sum(pats.values())
        pat_str = ' '.join(f'{p}={c}({c/total*100:.0f}%)' for p, c in sorted(pats.items(), key=lambda x:-x[1])[:5])
        print(f"    {trend:8s} ({total}只): {pat_str}")

# 命中率分布
rate_dist = defaultdict(int)
for info in best_map.values():
    bucket = int(info['rate']*20)*5
    rate_dist[bucket] += 1
print(f"\n  命中率分布: {dict(sorted(rate_dist.items()))}")

# 时间窗口稳定性
print(f"\n  窗口稳定性 (full→recent变化):")
stable = 0; improved = 0; degraded = 0
for sym, p in stock_profiles.items():
    full = p['windows'].get('full', {})
    recent = p['windows'].get('recent', {})
    for pat in full:
        if pat in recent and full[pat]['total'] >= 5:
            delta = recent[pat]['rate'] - full[pat]['rate']
            if delta > 0.05: improved += 1
            elif delta < -0.05: degraded += 1
            else: stable += 1
total_comp = stable + improved + degraded
if total_comp:
    print(f"    稳定: {stable}({stable/total_comp*100:.0f}%)  改善: {improved}({improved/total_comp*100:.0f}%)  恶化: {degraded}({degraded/total_comp*100:.0f}%)")

# ═══ 保存选股数据库 ═══
output = {
    'meta': {'version': '1.0', 'date': time.strftime('%Y-%m-%d'),
             'stocks': len(stock_profiles), 'weekly_data': weekly_ok,
             'patterns': {k: v['direction'] for k, v in PATTERNS.items()}},
    'profiles': stock_profiles,
    'best_map': {sym: info for sym, info in best_map.items()},
}

json.dump(output, open(OUT_DIR / 'multi_tf_stock_db.json', 'w'), ensure_ascii=False)
print(f"\n  数据库: {OUT_DIR / 'multi_tf_stock_db.json'}")
print(f"  选股示例 (bullish+L→D rate>0.8): {sum(1 for i in best_map.values() if i['trend']=='bullish' and i['pattern']=='L→D' and i['rate']>=0.8)}只")
