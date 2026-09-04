#!/usr/bin/env python3
"""自由组合挖掘: 从14,196笔交易反向学习有效信号组合"""
import json, sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20
from v11.v19_backtest_engine import backtest_v19

KLINE_DIR = Path('/root/.hermes/kline_cache')

files = sorted(KLINE_DIR.glob('*_daily_300.json'))

# For each trade, record: signal types in 5 bars before entry → PnL
combo_stats = defaultdict(lambda: {'trades': 0, 'wins': 0, 'total_pnl': 0.0, 'symbols': set()})

# Also track: single signal types before entry
single_stats = defaultdict(lambda: {'trades': 0, 'wins': 0, 'total_pnl': 0.0})

# Track: number of signals within 5-bar window
density_stats = defaultdict(lambda: {'trades': 0, 'wins': 0, 'total_pnl': 0.0})

checked = 0
for fp in files:
    sym = fp.stem.replace('_daily_300', '')
    try:
        ohlcv = json.loads(fp.read_bytes())
        if len(ohlcv) < 50: continue
    except: continue
    checked += 1
    
    sigs, _, _, swings_dict = detect_all_signals_v20(ohlcv)
    trades = backtest_v19(sym, ohlcv, sigs, swings_dict)
    if not isinstance(trades, list):
        trades = trades[0]
    
    if not trades:
        continue
    
    # Build signal index by bar
    sig_by_bar = defaultdict(list)
    for s in sigs:
        sig_by_bar[s.idx].append(s.type)
    
    for t in trades:
        entry_bar = t.entry_signal_bar
        pnl = t.pnl_pct
        won = pnl > 0
        
        # Collect signals in [entry_bar-5, entry_bar]
        nearby = []
        for bi in range(max(0, entry_bar-5), entry_bar+1):
            nearby.extend(sig_by_bar.get(bi, []))
        
        # Dedup + sort
        nearby_types = tuple(sorted(set(nearby)))
        sig_count = len(nearby)
        
        combo_stats[nearby_types]['trades'] += 1
        if won: combo_stats[nearby_types]['wins'] += 1
        combo_stats[nearby_types]['total_pnl'] += pnl
        combo_stats[nearby_types]['symbols'].add(sym)
        
        # Single signal stats
        for st in set(nearby):
            single_stats[st]['trades'] += 1
            if won: single_stats[st]['wins'] += 1
            single_stats[st]['total_pnl'] += pnl
        
        # Density stats
        density_stats[sig_count]['trades'] += 1
        if won: density_stats[sig_count]['wins'] += 1
        density_stats[sig_count]['total_pnl'] += pnl
    
    if checked % 1000 == 0:
        print(f'  [{checked}] {len(combo_stats)} unique combos...')

print(f'\nAnalyzed {checked} stocks')

# ═══ Report: Top Combos ═══
print(f'\n{"="*70}')
print(f'  TOP 30 信号组合 (按胜率, 至少5笔交易)')
print(f'{"="*70}')
ranked = sorted(combo_stats.items(), key=lambda x: x[1]['wins']/x[1]['trades'], reverse=True)
shown = 0
for combo, stats in ranked:
    if stats['trades'] < 5: continue
    wr = stats['wins']/stats['trades']*100
    avg_pnl = stats['total_pnl']/stats['trades']
    combo_str = '+'.join(c.replace('_Bull','⬆').replace('_Bear','⬇').replace('_BSL','▼').replace('_SSL','▲')[:8] for c in combo)
    print(f'  WR={wr:5.1f}% PnL={avg_pnl:+5.1f}% N={stats["trades"]:>4d} stocks={len(stats["symbols"]):>3d}  {combo_str[:80]}')
    shown += 1
    if shown >= 30: break

# ═══ Report: Single signal before entry ═══
print(f'\n{"="*70}')
print(f'  单个信号类型在入场前5bar的出现频率和效果')
print(f'{"="*70}')
for st in sorted(single_stats.keys()):
    stat = single_stats[st]
    if stat['trades'] < 10: continue
    wr = stat['wins']/stat['trades']*100
    avg_pnl = stat['total_pnl']/stat['trades']
    bar = '█'*int(wr/5)
    print(f'  {st:20s} N={stat["trades"]:>5d} WR={wr:5.1f}% PnL={avg_pnl:+5.1f}% {bar}')

# ═══ Report: Signal density ═══
print(f'\n{"="*70}')
print(f'  入场前5bar信号密度 vs 胜率')
print(f'{"="*70}')
for cnt in sorted(density_stats.keys()):
    stat = density_stats[cnt]
    wr = stat['wins']/stat['trades']*100
    avg_pnl = stat['total_pnl']/stat['trades']
    bar = '█'*int(stat['trades']/500)
    print(f'  {cnt:>3d}个信号 N={stat["trades"]:>5d} WR={wr:5.1f}% PnL={avg_pnl:+5.1f}% {bar}')

# ═══ Report: Best 2-signal combos ═══
print(f'\n{"="*70}')
print(f'  TOP 2-信号组合 (至少3笔)')
print(f'{"="*70}')
for combo, stats in ranked:
    if len(combo) != 2: continue
    if stats['trades'] < 3: continue
    wr = stats['wins']/stats['trades']*100
    avg_pnl = stats['total_pnl']/stats['trades']
    combo_str = '+'.join(c[:12] for c in combo)
    print(f'  WR={wr:5.1f}% PnL={avg_pnl:+5.1f}% N={stats["trades"]:>3d}  {combo_str}')
    if shown > 50: break
