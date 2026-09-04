#!/usr/bin/env python3
"""
SMC序列策略引擎 V1.0 — 可扩展架构
=====================================
- 信号分三大类: LIQUIDITY / STRUCTURE / ZONE
- 序列模式: 按时间顺序的信号类组合
- 新增信号只需添加到对应分类即可
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Set, Tuple

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20
from v11.v19_backtest_engine import find_tps, find_sls

# ════════════════════════════════════════════
# 1. 信号分类注册表 (扩展点: 新增信号加到这里)
# ════════════════════════════════════════════

SIGNAL_CATEGORIES = {
    # 流动性类: 止损聚集/扫荡
    'LIQUIDITY_LONG':  ['Sweep_SSL', 'EQL'],
    'LIQUIDITY_SHORT': ['Sweep_BSL', 'EQH'],
    
    # 结构类: 趋势方向/转换
    'STRUCTURE_LONG':  ['CHOCH_Bull', 'BOS_Bull', 'MSS_Bull'],
    'STRUCTURE_SHORT': ['CHOCH_Bear', 'BOS_Bear', 'MSS_Bear'],
    
    # 供需区域类: 入场POI
    'DEMAND_ZONE':     ['OB_Bull', 'FVG_Bull'],
    'SUPPLY_ZONE':     ['OB_Bear', 'FVG_Bear'],
    
    # 未来扩展预留:
    # 'OTE_ZONE':        ['OTE_Discount'],
    # 'KILLZONE':        ['KZ_Asian','KZ_London','KZ_NY'],
    # 'PD_ARRAY':        ['BreakerBlock_Bull','BreakerBlock_Bear'],
}

# ════════════════════════════════════════════
# 2. 序列模式定义 (扩展点: 新增模式加到这里)
# ════════════════════════════════════════════
# 格式: (名称, [阶段类别列表], [阶段间最大bar间隔], 入场阶段索引)
#       入场阶段索引 = 哪个阶段是实际入场点 (0=第一阶段, -1=最后阶段)

SEQUENCE_PATTERNS = {
    # ── Long Patterns ──
    'L→S→D': {
        'stages': ['LIQUIDITY_LONG', 'STRUCTURE_LONG', 'DEMAND_ZONE'],
        'gaps': [30, 15],
        'entry_stage': -1,   # 在需求区入场
        'direction': 'long',
        'description': '流动性扫荡 → 结构确认 → 需求区入场',
    },
    'S→D': {
        'stages': ['STRUCTURE_LONG', 'DEMAND_ZONE'],
        'gaps': [15],
        'entry_stage': -1,
        'direction': 'long',
        'description': '结构突破 → 需求区入场',
    },
    'L→D': {
        'stages': ['LIQUIDITY_LONG', 'DEMAND_ZONE'],
        'gaps': [20],
        'entry_stage': -1,
        'direction': 'long',
        'description': '流动性扫荡 → 需求区入场',
    },
    
    # ── Short Patterns ──
    'L→S→D_short': {
        'stages': ['LIQUIDITY_SHORT', 'STRUCTURE_SHORT', 'SUPPLY_ZONE'],
        'gaps': [30, 15],
        'entry_stage': -1,
        'direction': 'short',
        'description': '流动性扫荡 → 结构确认 → 供给区入场',
    },
    'S→D_short': {
        'stages': ['STRUCTURE_SHORT', 'SUPPLY_ZONE'],
        'gaps': [15],
        'entry_stage': -1,
        'direction': 'short',
        'description': '结构突破 → 供给区入场',
    },
    
    # ── 未来扩展 ──
    # 'OTE→ZONE': {
    #     'stages': ['OTE_ZONE', 'DEMAND_ZONE'],
    #     ...
    # },
}

# Active patterns for this backtest (select which to use)
ACTIVE_PATTERNS = ['L→S→D', 'S→D', 'L→D', 'L→S→D_short', 'S→D_short']

# ════════════════════════════════════════════
# 3. 序列检测引擎
# ════════════════════════════════════════════

def detect_sequences(signals, active_patterns=None):
    """检测所有匹配的SMC序列。返回 [{pattern, signals, entry_bar, direction, ...}]."""
    if active_patterns is None:
        active_patterns = list(SEQUENCE_PATTERNS.keys())
    
    # 索引信号: bar → [signal_types]
    sigs_by_bar = defaultdict(list)
    for s in signals:
        sigs_by_bar[s.idx].append(s)
    
    all_bars = sorted(sigs_by_bar.keys())
    sequences = []
    
    for pat_name in active_patterns:
        pat = SEQUENCE_PATTERNS[pat_name]
        stages = pat['stages']
        gaps = pat['gaps']
        direction = pat['direction']
        
        # 展开每个阶段的允许信号类型
        stage_types = [SIGNAL_CATEGORIES[cat] for cat in stages]
        
        # 滑动窗口: 从每个可能的起始bar开始匹配
        for start_bar in all_bars:
            # 找到第一阶段匹配的信号
            s1_candidates = [s for s in sigs_by_bar.get(start_bar, [])
                           if s.type in stage_types[0]]
            if not s1_candidates:
                continue
            
            for s1 in s1_candidates:
                matched_signals = [s1]
                current_bar = s1.idx
                ok = True
                
                # 匹配后续阶段
                for stage_idx in range(1, len(stages)):
                    max_gap = gaps[stage_idx - 1]
                    found = False
                    
                    for bi in range(current_bar + 1, current_bar + max_gap + 1):
                        if bi not in sigs_by_bar:
                            continue
                        for cand in sigs_by_bar[bi]:
                            if cand.type in stage_types[stage_idx] \
                               and cand not in matched_signals:
                                matched_signals.append(cand)
                                current_bar = bi
                                found = True
                                break
                        if found:
                            break
                    
                    if not found:
                        ok = False
                        break
                
                if not ok or len(matched_signals) != len(stages):
                    continue
                
                # 确定入场信号 (entry_stage指定的阶段)
                entry_idx = pat['entry_stage']
                entry_sig = matched_signals[entry_idx]
                
                sequences.append({
                    'pattern': pat_name,
                    'direction': direction,
                    'signals': [(s.type, s.idx, s.price) for s in matched_signals],
                    'entry_bar': entry_sig.idx,
                    'entry_type': entry_sig.type,
                    'entry_price': entry_sig.price,
                    'zone_lower': entry_sig.lower,
                    'zone_upper': entry_sig.upper,
                    'start_bar': matched_signals[0].idx,
                    'end_bar': matched_signals[-1].idx,
                })
    
    # 按入场bar去重
    seen = set()
    unique = []
    for seq in sorted(sequences, key=lambda x: x['entry_bar']):
        key = seq['entry_bar']
        if key not in seen:
            seen.add(key)
            unique.append(seq)
    
    return unique


# ════════════════════════════════════════════
# 4. 回测引擎
# ════════════════════════════════════════════

def backtest_sequences(ohlcv, sequences, signals, swings_dict):
    """执行序列入场交易."""
    n = len(ohlcv)
    trades = []
    used_bars = set()
    
    for seq in sequences:
        entry_bar = seq['entry_bar']
        confirmed_at = entry_bar + 1  # T+1: 下一根bar入场
        if confirmed_at >= n - 2: continue
        if confirmed_at in used_bars: continue
        
        entry_price = ohlcv[confirmed_at]['o']
        direction = seq['direction']
        
        # TP/SL from structural levels
        if direction == 'long':
            tp_price, tp_src, _ = find_tps(entry_price, signals, swings_dict, ohlcv)
            sl_price, sl_src, _ = find_sls(entry_price, signals, swings_dict, ohlcv)
        else:
            sl_price, sl_src, _ = find_tps(entry_price, signals, swings_dict, ohlcv)
            tp_price, tp_src, _ = find_sls(entry_price, signals, swings_dict, ohlcv)
        
        # TP cap 5%
        max_tp = entry_price * (1.05 if direction == 'long' else 0.95)
        if (direction == 'long' and tp_price > max_tp) or \
           (direction == 'short' and tp_price < max_tp):
            tp_price = max_tp
        
        # RR >= 1.0
        tp_dist = abs(tp_price - entry_price) / entry_price * 100
        sl_dist = abs(sl_price - entry_price) / entry_price * 100
        if sl_dist > 0 and tp_dist / sl_dist < 1.0:
            continue
        
        # Walk forward
        exit_idx = -1; exit_price = 0; exit_method = 'eod'
        for i in range(confirmed_at + 1, n):
            bar = ohlcv[i]
            if direction == 'long':
                if bar['h'] >= tp_price:
                    exit_idx = i; exit_price = tp_price; exit_method = 'tp_hit'; break
                if bar['l'] <= sl_price:
                    exit_idx = i; exit_price = sl_price; exit_method = 'sl_hit'; break
            else:
                if bar['l'] <= tp_price:
                    exit_idx = i; exit_price = tp_price; exit_method = 'tp_hit'; break
                if bar['h'] >= sl_price:
                    exit_idx = i; exit_price = sl_price; exit_method = 'sl_hit'; break
        
        if exit_idx < 0:
            exit_idx = n - 1; exit_price = ohlcv[exit_idx]['c']
            exit_method = 'eod'
        if exit_idx <= confirmed_at: continue  # T+1
        
        pnl = (exit_price - entry_price) / entry_price * 100
        if direction == 'short': pnl = -pnl
        
        trades.append({
            'pattern': seq['pattern'],
            'direction': direction,
            'entry_bar': confirmed_at,
            'entry_price': entry_price,
            'exit_bar': exit_idx,
            'exit_price': exit_price,
            'exit_method': exit_method,
            'pnl_pct': pnl,
            'hold_bars': exit_idx - confirmed_at,
            'tp_price': tp_price,
            'sl_price': sl_price,
        })
        used_bars.add(exit_idx)
    
    return trades


def compute_stats(trades, label=''):
    """计算策略统计."""
    if not trades: return None
    n = len(trades)
    wins = sum(1 for t in trades if t['pnl_pct'] > 0)
    total_pnl = sum(t['pnl_pct'] for t in trades)
    total_hold = sum(t['hold_bars'] for t in trades)
    
    win_pnls = [t['pnl_pct'] for t in trades if t['pnl_pct'] > 0]
    loss_pnls = [abs(t['pnl_pct']) for t in trades if t['pnl_pct'] <= 0]
    
    em = defaultdict(int)
    for t in trades: em[t['exit_method']] += 1
    
    return {
        'label': label,
        'trades': n,
        'wins': wins,
        'wr': wins / n * 100,
        'avg_pnl': total_pnl / n,
        'total_pnl': total_pnl,
        'avg_hold': total_hold / n,
        'avg_win': sum(win_pnls)/len(win_pnls) if win_pnls else 0,
        'avg_loss': sum(loss_pnls)/len(loss_pnls) if loss_pnls else 0,
        'pf': sum(win_pnls)/sum(loss_pnls) if loss_pnls else 999,
        'tp_hit': em.get('tp_hit', 0),
        'sl_hit': em.get('sl_hit', 0),
        'eod': em.get('eod', 0),
    }


# ════════════════════════════════════════════
# 5. 主程序
# ════════════════════════════════════════════

KLINE_DIR = Path('/root/.hermes/kline_cache')
files = sorted(KLINE_DIR.glob('*_daily_300.json'))

# Accumulators
bl_all = []
seq_all = []
per_pattern = defaultdict(list)
seq_stocks = set()

t0 = time.time()
for fi, fp in enumerate(files):
    sym = fp.stem.replace('_daily_300', '')
    try:
        ohlcv = json.loads(fp.read_bytes())
        n = len(ohlcv)
        if n < 50: continue
    except: continue
    
    sigs, _, _, swings_dict = detect_all_signals_v20(ohlcv)
    
    # Baseline
    from v11.v19_backtest_engine import backtest_v19
    trades_bl = backtest_v19(sym, ohlcv, sigs, swings_dict)
    if isinstance(trades_bl, tuple): trades_bl = trades_bl[0]
    if trades_bl:
        for t in trades_bl:
            bl_all.append({'pnl_pct': t.pnl_pct, 'hold_bars': t.hold_bars,
                          'exit_method': t.exit_method})
    
    # Sequences
    sequences = detect_sequences(sigs, ACTIVE_PATTERNS)
    if not sequences:
        continue
    
    seq_stocks.add(sym)
    trades_seq = backtest_sequences(ohlcv, sequences, sigs, swings_dict)
    for t in trades_seq:
        seq_all.append(t)
        per_pattern[t['pattern']].append(t)
    
    if (fi+1) % 1000 == 0:
        print(f"  [{fi+1}/4800] {time.time()-t0:.0f}s bl={len(bl_all)} seq={len(seq_all)}")

elapsed = time.time() - t0

# ═══ Report ═══
bl_st = compute_stats(bl_all, 'Baseline')
seq_st = compute_stats(seq_all, 'Combined (S→D + L→S→D + L→D)')

print(f"\n{'='*75}")
print(f"  SMC序列策略 V1.0 — 可扩展架构 ({elapsed:.0f}s)")
print(f"{'='*75}")

print(f"\n  信号分类: {sum(len(v) for v in SIGNAL_CATEGORIES.values())}种信号, {len(SIGNAL_CATEGORIES)}个分类")
print(f"  序列模式: {len(SEQUENCE_PATTERNS)}种定义, {len(ACTIVE_PATTERNS)}种激活")

print(f"\n  {'Strategy':25s} {'Trades':>6s} {'WR':>6s} {'PnL':>7s} {'Win':>7s} {'Loss':>7s} {'PF':>6s} {'Hold':>5s} {'TP%':>5s} {'Total':>8s}")
print(f"  {'─'*25} {'─'*6} {'─'*6} {'─'*7} {'─'*7} {'─'*7} {'─'*6} {'─'*5} {'─'*5} {'─'*8}")

for st in [bl_st, seq_st]:
    if not st: continue
    print(f"  {st['label']:25s} {st['trades']:>6d} {st['wr']:>5.1f}% {st['avg_pnl']:>+6.2f}% {st['avg_win']:>+6.2f}% {st['avg_loss']:>+6.2f}% {st['pf']:>5.1f} {st['avg_hold']:>4.1f}b {st['tp_hit']/st['trades']*100:>4.0f}% {st['total_pnl']:>+7.0f}%")

# Per-pattern
print(f"\n  Per-Pattern:")
for pat in ACTIVE_PATTERNS:
    trades = per_pattern.get(pat, [])
    if len(trades) < 5: continue
    st = compute_stats(trades, pat)
    print(f"    {pat:15s} {st['trades']:>5d}笔 WR={st['wr']:5.1f}% PnL={st['avg_pnl']:+.2f}% PF={st['pf']:.1f} TP={st['tp_hit']/st['trades']*100:.0f}%")

# PnL distribution
print(f"\n  PnL分布对比:")
for label, trades in [('Baseline', bl_all), ('Combined', seq_all)]:
    buckets = defaultdict(int)
    for t in trades:
        p = t['pnl_pct']
        if p < -2: buckets['<-2%'] += 1
        elif p < -1: buckets['-2~-1'] += 1
        elif p < 0: buckets['-1~0'] += 1
        elif p < 1: buckets['0~1%'] += 1
        elif p < 2: buckets['1~2%'] += 1
        elif p < 3: buckets['2~3%'] += 1
        elif p <= 5: buckets['3~5%'] += 1
        else: buckets['>5%'] += 1
    n = len(trades)
    dist = '  '.join(f'{k}={buckets[k]/n*100:.0f}%' for k in ['<-2%','-2~-1','-1~0','0~1%','1~2%','2~3%','3~5%','>5%'])
    print(f"    {label:15s} {dist}")

# Sequence stats
print(f"\n  序列统计:")
print(f"    序列信号股票: {len(seq_stocks)}/{len(files)} ({len(seq_stocks)/len(files)*100:.0f}%)")
print(f"    总序列检测: {sum(len(per_pattern[p]) for p in ACTIVE_PATTERNS if p in per_pattern)}")
print(f"    模式覆盖: {[(p, len(per_pattern.get(p,[]))) for p in ACTIVE_PATTERNS]}")
print(f"\n  扩展性: 新增信号→加入SIGNAL_CATEGORIES, 新模式→加入SEQUENCE_PATTERNS")
