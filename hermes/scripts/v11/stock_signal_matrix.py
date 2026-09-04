#!/usr/bin/env python3
"""
SMC 个股信号效能矩阵 V1.0
===========================
对每只股票、每个时间窗口、每个信号组合, 评估"信号出现后未来N bar涨幅≥2%"的命中率.
输出: JSON矩阵, 可用于选股和监控.
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict
from itertools import combinations

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20, _calc_atr

KLINE_DIR = Path('/root/.hermes/kline_cache')
OUT_DIR = Path('/root/.hermes/smc_opt_v21')
OUT_DIR.mkdir(exist_ok=True)

# 配置
TARGET_PCT = 2.0      # 目标涨幅
LOOKAHEAD = 5          # 未来N根bar
CONTEXT_WINDOW = 5     # 信号上下文窗口
MIN_SAMPLES = 3        # 最少样本数才算有效

# 信号分类 (用于生成组合)
ENTRY_SIGNALS = ['FVG_Bull', 'OB_Bull']  # 入场触发信号
CONTEXT_SIGNALS = [
    'Sweep_SSL', 'Sweep_BSL', 'EQL', 'EQH',
    'CHOCH_Bull', 'CHOCH_Bear', 'BOS_Bull', 'BOS_Bear',
    'MSS_Bull', 'MSS_Bear',
    'FVG_Bear', 'OB_Bear', 'BPR',
]

# 预生成所有要测试的上下文组合 (单信号+双信号+三信号)
COMBO_LIST = []
# Single context signals
for s in CONTEXT_SIGNALS:
    COMBO_LIST.append(frozenset([s]))
# Pairs
for a, b in combinations(CONTEXT_SIGNALS, 2):
    COMBO_LIST.append(frozenset([a, b]))
# Triples (高频组合)
high_freq = ['Sweep_SSL','BOS_Bear','MSS_Bear','FVG_Bear','OB_Bear','BPR','EQL']
for a, b, c in combinations(high_freq, 3):
    COMBO_LIST.append(frozenset([a, b, c]))

print(f"Combo list: {len(COMBO_LIST)} combinations")

# ═══ 主循环 ═══
files = sorted(KLINE_DIR.glob('*_daily_300.json'))
stock_matrix = {}  # {symbol: {window: {combo: {hits, total, avg_ret}}}}

# 全局聚合 (用于跨股票分析)
global_combo = defaultdict(lambda: {'hits': 0, 'total': 0, 'avg_ret': 0.0, 'stocks': set()})

t0 = time.time()
for fi, fp in enumerate(files):
    sym = fp.stem.replace('_daily_300', '')
    try:
        ohlcv = json.loads(fp.read_bytes())
        n = len(ohlcv)
        if n < 60: continue
    except: continue
    
    sigs, _, _, _ = detect_all_signals_v20(ohlcv)
    
    # 信号索引
    sig_by_bar = defaultdict(set)
    for s in sigs:
        sig_by_bar[s.idx].add(s.type)
    
    # 多时间窗口: full(全量), mid(最近150), recent(最近50)
    stock_data = {}
    for window_name, start_bar in [('full', 0), ('mid', max(0, n-150)), ('recent', max(0, n-50))]:
        window_combos = defaultdict(lambda: {'hits': 0, 'total': 0, 'avg_ret': 0.0})
        
        # 遍历每个入场信号
        for s in sigs:
            if s.type not in ENTRY_SIGNALS:
                continue
            bar = s.idx
            if bar < start_bar: continue
            if bar + LOOKAHEAD >= n: continue
            
            # 收集上下文信号
            ctx = set()
            for bi in range(max(start_bar, bar-CONTEXT_WINDOW), bar+1):
                ctx.update(sig_by_bar.get(bi, set()))
            ctx.discard(s.type)  # 去掉入场信号自身
            
            if not ctx:
                continue
            
            # 未来收益
            entry_price = ohlcv[bar]['c']
            max_high = max(ohlcv[i]['h'] for i in range(bar+1, min(bar+LOOKAHEAD+1, n)))
            ret = (max_high - entry_price) / entry_price * 100
            
            # 对每个预定义的组合进行匹配
            ctx_frozen = frozenset(ctx)
            for combo in COMBO_LIST:
                if combo.issubset(ctx_frozen):
                    window_combos[combo]['total'] += 1
                    window_combos[combo]['avg_ret'] += ret
                    if ret >= TARGET_PCT:
                        window_combos[combo]['hits'] += 1
        
        # 只保留有足够样本的组合
        filtered = {}
        for combo, stats in window_combos.items():
            if stats['total'] >= MIN_SAMPLES:
                hit_rate = stats['hits'] / stats['total']
                avg_ret = stats['avg_ret'] / stats['total']
                filtered[str(sorted(combo))] = {
                    'hits': stats['hits'], 'total': stats['total'],
                    'rate': round(hit_rate, 3), 'avg_ret': round(avg_ret, 2),
                }
        stock_data[window_name] = filtered
    
    stock_matrix[sym] = stock_data
    
    # 全局聚合 (仅full窗口)
    if 'full' in stock_data:
        for combo_str, stats in stock_data['full'].items():
            combo_key = frozenset(eval(combo_str))
            global_combo[combo_key]['hits'] += stats['hits']
            global_combo[combo_key]['total'] += stats['total']
            global_combo[combo_key]['avg_ret'] += stats['avg_ret'] * stats['total']
            global_combo[combo_key]['stocks'].add(sym)
    
    if (fi+1) % 500 == 0:
        elapsed = time.time() - t0
        print(f"  [{fi+1}/{len(files)}] {elapsed:.0f}s stocks={len(stock_matrix)} combos={len(global_combo)}")

elapsed = time.time() - t0

# ═══ 输出 ═══
print(f"\n{'='*70}")
print(f"  SMC 个股信号效能矩阵 ({elapsed:.0f}s)")
print(f"  股票: {len(stock_matrix)}  组合: {len(COMBO_LIST)}  目标: +{TARGET_PCT}%/{LOOKAHEAD}bar")
print(f"{'='*70}")

# 全局最佳组合
print(f"\n  全局最佳组合 (合并所有股票, ≥50只股票):")
ranked = sorted(global_combo.items(), key=lambda x: x[1]['hits']/max(x[1]['total'],1), reverse=True)
for combo, stats in ranked:
    if len(stats['stocks']) < 50: continue
    if stats['total'] < 100: continue
    hit_rate = stats['hits'] / stats['total'] * 100
    avg_ret = stats['avg_ret'] / stats['total']
    combo_str = '+'.join(sorted(combo, key=lambda x: ('Bull' not in x, x)))
    print(f"    Hit={hit_rate:5.1f}% Ret={avg_ret:+5.2f}% N={stats['total']:>5d} stocks={len(stats['stocks']):>4d}  [{combo_str}]")

# 每只股票的最佳组合 (recent窗口)
print(f"\n  个股最佳组合摘要 (recent窗口):")
best_per_stock = {}
for sym, data in stock_matrix.items():
    recent = data.get('recent', {})
    best_combo = None
    best_rate = 0
    for combo_str, stats in recent.items():
        if stats['rate'] > best_rate and stats['total'] >= MIN_SAMPLES:
            best_rate = stats['rate']
            best_combo = combo_str
    if best_combo:
        best_per_stock[sym] = {'combo': best_combo, 'rate': best_rate, 'total': recent[best_combo]['total']}

# 最佳组合分布
combo_freq = defaultdict(int)
rate_dist = defaultdict(int)
for sym, info in best_per_stock.items():
    combo_freq[info['combo']] += 1
    bucket = int(info['rate'] * 10) * 10
    rate_dist[bucket] += 1

print(f"    有最佳组合的股票: {len(best_per_stock)}/{len(stock_matrix)}")
print(f"    命中率分布: {dict(sorted(rate_dist.items()))}")

print(f"\n  最常被各股选为最佳的上下文组合:")
for combo_str, freq in sorted(combo_freq.items(), key=lambda x: -x[1])[:10]:
    gs = global_combo.get(frozenset(eval(combo_str)), {})
    gh = gs.get('hits',0)/max(gs.get('total',1),1)*100 if gs.get('total',0)>0 else 0
    print(f"    {freq:>4d}只  GlobalHit={gh:4.1f}%  [{combo_str[:80]}]")

# 窗口切换分析
print(f"\n  窗口敏感度分析 (同一信号在不同窗口的表现差异):")
for combo, stats in ranked[:5]:
    if stats['total'] < 200: continue
    combo_str = '+'.join(sorted(combo))
    rates = []
    for window in ['full', 'mid', 'recent']:
        window_total = 0; window_hits = 0
        for sym, data in stock_matrix.items():
            wd = data.get(window, {})
            ck = str(sorted(combo))
            if ck in wd:
                window_total += wd[ck]['total']
                window_hits += wd[ck]['hits']
        if window_total > 0:
            rates.append(f"{window}={window_hits/window_total*100:.0f}%")
    if rates:
        print(f"    [{combo_str[:50]}]  {' | '.join(rates)}")

# ═══ 保存 ═══
# 精简版: 只保存每只股票每个窗口的top-5组合
compact = {}
for sym, data in stock_matrix.items():
    compact[sym] = {}
    for window, combos in data.items():
        top5 = sorted(combos.items(), key=lambda x: x[1]['rate'], reverse=True)[:5]
        compact[sym][window] = {c: s for c, s in top5}

json.dump(compact, open(OUT_DIR / 'stock_signal_matrix.json', 'w'), ensure_ascii=False)
print(f"\n  Saved to {OUT_DIR / 'stock_signal_matrix.json'} ({len(compact)} stocks)")
print(f"  格式: {{symbol: {{window: {{combo: {{rate, total, avg_ret}}}}}}}}")
