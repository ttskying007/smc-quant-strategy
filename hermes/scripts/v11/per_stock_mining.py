#!/usr/bin/env python3
"""每只股票独立: 信号组合 → 未来N bar结果 的预测能力分析"""
import json, sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20, detect_signal_sequences

KLINE_DIR = Path('/root/.hermes/kline_cache')
files = sorted(KLINE_DIR.glob('*_daily_300.json'))

TARGET_PCT = 2.0    # 目标: 2%涨幅
LOOKAHEAD = 5       # 未来5 bar

# Global: 所有股票的 signal→outcome 汇总
global_combo = defaultdict(lambda: {'hits': 0, 'total': 0, 'avg_return': 0.0})

# Per-stock: 每只股票的 signal→outcome
per_stock = {}  # {symbol: {combo_tuple: {hits, total, avg_return}}}

# Track: 有多少样本
total_signals = 0
entry_signals = 0  # FVG_Bull + OB_Bull

checked = 0
for fp in files:
    sym = fp.stem.replace('_daily_300', '')
    try:
        ohlcv = json.loads(fp.read_bytes())
        n = len(ohlcv)
        if n < 50: continue
    except: continue
    checked += 1
    
    sigs, _, _, _ = detect_all_signals_v20(ohlcv)
    
    # Index signals by bar
    sig_by_bar = defaultdict(list)
    for s in sigs:
        sig_by_bar[s.idx].append(s.type)
    
    stock_combo = defaultdict(lambda: {'hits': 0, 'total': 0, 'avg_return': 0.0})
    
    # For each entry-signal bar (FVG_Bull or OB_Bull)
    for s in sigs:
        if s.type not in ('FVG_Bull', 'OB_Bull'):
            continue
        entry_bar = s.idx
        if entry_bar + LOOKAHEAD >= n:
            continue
        
        total_signals += 1
        entry_signals += 1
        
        # Collect signals in [entry_bar-5, entry_bar]
        nearby = set()
        for bi in range(max(0, entry_bar-5), entry_bar+1):
            for st in sig_by_bar.get(bi, []):
                nearby.add(st)
        
        combo_key = tuple(sorted(nearby))
        
        # Future return
        entry_price = ohlcv[entry_bar]['c']
        max_high = max(ohlcv[i]['h'] for i in range(entry_bar+1, min(entry_bar+LOOKAHEAD+1, n)))
        ret = (max_high - entry_price) / entry_price * 100
        
        hit = ret >= TARGET_PCT
        
        # Update global
        global_combo[combo_key]['total'] += 1
        if hit: global_combo[combo_key]['hits'] += 1
        global_combo[combo_key]['avg_return'] += ret
        
        # Update per-stock
        stock_combo[combo_key]['total'] += 1
        if hit: stock_combo[combo_key]['hits'] += 1
        stock_combo[combo_key]['avg_return'] += ret
    
    per_stock[sym] = dict(stock_combo)
    
    if checked % 1000 == 0:
        print(f'  [{checked}] {total_signals} signals, {len(global_combo)} unique combos...')

print(f'\nAnalyzed {checked} stocks, {total_signals} entry signals total')

# ═══ Report ═══
print(f'\n{"="*70}')
print(f'  GLOBAL: 信号组合 → 未来{LOOKAHEAD}bar内达到+{TARGET_PCT}% 的命中率')
print(f'  (至少30个样本的组合)')
print(f'{"="*70}')

ranked = sorted(global_combo.items(), key=lambda x: x[1]['hits']/max(x[1]['total'],1), reverse=True)
for combo, stats in ranked:
    if stats['total'] < 30: continue
    hit_rate = stats['hits'] / stats['total'] * 100
    avg_ret = stats['avg_return'] / stats['total']
    combo_str = '+'.join(c.replace('_Bull','⬆').replace('_Bear','⬇').replace('_BSL','▼').replace('_SSL','▲')[:6] for c in combo)
    print(f'  Hit={hit_rate:5.1f}% AvgRet={avg_ret:+5.2f}% N={stats["total"]:>5d}  {combo_str[:90]}')

# ═══ Per-stock diversity ═══
print(f'\n{"="*70}')
print(f'  每只股票的最佳组合多样性')
print(f'{"="*70}')

# For each stock, find its best combo
stock_best = {}
for sym, combos in per_stock.items():
    best_combo = None
    best_rate = -1
    best_n = 0
    for combo, stats in combos.items():
        if stats['total'] < 5: continue  # 至少5个样本
        rate = stats['hits'] / stats['total']
        if rate > best_rate:
            best_rate = rate
            best_combo = combo
            best_n = stats['total']
    if best_combo:
        stock_best[sym] = {'combo': best_combo, 'rate': best_rate, 'n': best_n}

# Distribution of best rates
rate_dist = defaultdict(int)
for sym, info in stock_best.items():
    bucket = int(info['rate'] * 10) * 10
    rate_dist[bucket] += 1

print(f'  有足够样本的股票: {len(stock_best)}/{checked}')
print(f'  最佳组合命中率分布:')
for bucket in sorted(rate_dist.keys()):
    bar = '█' * (rate_dist[bucket] // 20)
    print(f'    {bucket:>3d}%: {rate_dist[bucket]:>4d}只 {bar}')

# Diversity: what combos are chosen as "best"?
best_combo_freq = defaultdict(int)
for sym, info in stock_best.items():
    best_combo_freq[info['combo']] += 1

print(f'\n  最常被选为"最佳"的组合 (Top 15):')
ranked_best = sorted(best_combo_freq.items(), key=lambda x: -x[1])
for combo, freq in ranked_best[:15]:
    combo_str = '+'.join(c[:10] for c in combo)
    # Get global stats for this combo
    gs = global_combo.get(combo, {})
    gh = gs.get('hits', 0) / max(gs.get('total', 1), 1) * 100
    print(f'    {freq:>4d}只选择  GlobalHit={gh:4.1f}%  {combo_str[:80]}')

# ═══ Stock examples ═══
print(f'\n{"="*70}')
print(f'  个股示例 (最佳组合+命中率)')
print(f'{"="*70}')
for sym in ['600519', '000001', '300750', '000858', '002594', '600036']:
    if sym in stock_best:
        info = stock_best[sym]
        combo_str = '+'.join(c[:8] for c in info['combo'])
        print(f'  {sym:12s} best={info["rate"]*100:.0f}% N={info["n"]}  {combo_str[:80]}')
    else:
        print(f'  {sym:12s} 样本不足')
