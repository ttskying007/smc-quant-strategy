#!/usr/bin/env python3
"""全模式SMC序列回测 — 三大类信号按时间顺序排列的所有有效组合"""
import json, sys, time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20
from v11.v19_backtest_engine import find_tps, find_sls

KLINE_DIR = Path('/root/.hermes/kline_cache')

# ═══ 信号分类 ═══
LIQUIDITY_LONG  = ['Sweep_SSL', 'EQL']       # 下方流动性被扫 → 看涨
LIQUIDITY_SHORT = ['Sweep_BSL', 'EQH']       # 上方流动性被扫 → 看跌
STRUCTURE_LONG  = ['CHOCH_Bull', 'BOS_Bull', 'MSS_Bull']  # 看涨结构
STRUCTURE_SHORT = ['CHOCH_Bear', 'BOS_Bear', 'MSS_Bear']  # 看跌结构
DEMAND_ZONES    = ['OB_Bull', 'FVG_Bull']     # 需求区
SUPPLY_ZONES    = ['OB_Bear', 'FVG_Bear']     # 供给区

# ═══ 所有有效Long序列模式 (每个信号类选一个代表, 按时间顺序) ═══
# 格式: (名称, [阶段1_类型列表, 阶段2_类型列表, ...], 最大bar间隔列表)
LONG_PATTERNS = [
    # 经典SMC: Demand Zone → Liquidity Sweep → Structure → Entry
    ('D→L→S',  [DEMAND_ZONES, LIQUIDITY_LONG, STRUCTURE_LONG],  [20, 30]),
    # Sweep first: Liquidity → Structure → Demand forms → Entry
    ('L→S→D',  [LIQUIDITY_LONG, STRUCTURE_LONG, DEMAND_ZONES],  [30, 15]),
    # Sweep + Structure only
    ('L→S',    [LIQUIDITY_LONG, STRUCTURE_LONG],                [30]),
    # Structure → Demand
    ('S→D',    [STRUCTURE_LONG, DEMAND_ZONES],                  [15]),
    # Demand → Structure (zone forms, then structure confirms)
    ('D→S',    [DEMAND_ZONES, STRUCTURE_LONG],                  [20]),
    # Triple: L→S→D with structure first
    ('L→S→D_v2', [LIQUIDITY_LONG, STRUCTURE_LONG, DEMAND_ZONES], [20, 10]),
    # Demand + Sweep overlap → Structure
    ('D+L→S',  [DEMAND_ZONES, LIQUIDITY_LONG, STRUCTURE_LONG],  [10, 20]),
]

SHORT_PATTERNS = [
    ('S→L→D',  [SUPPLY_ZONES, LIQUIDITY_SHORT, STRUCTURE_SHORT], [20, 30]),
    ('L→S→D',  [LIQUIDITY_SHORT, STRUCTURE_SHORT, SUPPLY_ZONES], [30, 15]),
    ('L→S',    [LIQUIDITY_SHORT, STRUCTURE_SHORT],               [30]),
    ('S→D',    [STRUCTURE_SHORT, SUPPLY_ZONES],                  [15]),
    ('D→S',    [SUPPLY_ZONES, STRUCTURE_SHORT],                  [20]),
    ('L→S→D_v2', [LIQUIDITY_SHORT, STRUCTURE_SHORT, SUPPLY_ZONES], [20, 10]),
    ('D+L→S',  [SUPPLY_ZONES, LIQUIDITY_SHORT, STRUCTURE_SHORT], [10, 20]),
]

def detect_sequences(signals, patterns, max_window=50):
    """检测所有匹配的时间序列模式."""
    sigs_by_bar = defaultdict(list)
    for s in signals:
        sigs_by_bar[s.idx].append(s)
    
    sequences = []
    
    for pat_name, stage_types_list, max_gaps in patterns:
        # For each starting bar, try to match stages in order
        for start_bar in sorted(sigs_by_bar.keys()):
            # Stage 1: find a signal matching stage_types_list[0]
            stage1_sigs = [s for s in sigs_by_bar[start_bar] if s.type in stage_types_list[0]]
            if not stage1_sigs:
                continue
            
            for s1 in stage1_sigs:
                current_bar = s1.idx
                matched = [s1]
                ok = True
                
                for stage_idx in range(1, len(stage_types_list)):
                    stage_types = stage_types_list[stage_idx]
                    max_gap = max_gaps[stage_idx - 1]
                    
                    # Search forward for a matching signal
                    found = False
                    for bi in range(current_bar + 1, min(current_bar + max_gap + 1, max(sigs_by_bar.keys()) + 1)):
                        if bi in sigs_by_bar:
                            for s in sigs_by_bar[bi]:
                                if s.type in stage_types and s not in matched:
                                    matched.append(s)
                                    current_bar = bi
                                    found = True
                                    break
                        if found:
                            break
                    
                    if not found:
                        ok = False
                        break
                
                if ok and len(matched) == len(stage_types_list):
                    # Entry at the last matched signal's demand/supply zone
                    last_sig = matched[-1]
                    sequences.append({
                        'pattern': pat_name,
                        'signals': [(s.type, s.idx) for s in matched],
                        'entry_bar': last_sig.idx,
                        'entry_type': last_sig.type,
                        'entry_price': last_sig.price,
                        'zone_lower': last_sig.lower,
                        'zone_upper': last_sig.upper,
                        'start_bar': matched[0].idx,
                        'end_bar': last_sig.idx,
                    })
    
    # Dedup by entry bar
    seen = set()
    unique = []
    for seq in sequences:
        key = seq['entry_bar']
        if key not in seen:
            seen.add(key)
            unique.append(seq)
    
    return sorted(unique, key=lambda x: x['entry_bar'])


# ═══ 回测 ═══
files = sorted(KLINE_DIR.glob('*_daily_300.json'))

# Baseline
bl = {'trades':0, 'wins':0, 'total_pnl':0.0, 'total_hold':0, 'exit_methods':defaultdict(int)}

# Per-pattern results
pattern_results = defaultdict(lambda: {'trades':0, 'wins':0, 'total_pnl':0.0, 'total_hold':0,
                                        'exit_methods':defaultdict(int), 'stocks':set()})

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
            bl['trades'] += 1
            bl['total_pnl'] += t.pnl_pct
            bl['total_hold'] += t.hold_bars
            bl['exit_methods'][t.exit_method] += 1
            if t.pnl_pct > 0: bl['wins'] += 1
    
    # All sequence patterns
    all_seqs = detect_sequences(sigs, LONG_PATTERNS + SHORT_PATTERNS)
    
    used_bars = set()
    for seq in all_seqs:
        entry_bar = seq['entry_bar']
        confirmed_at = entry_bar + 1
        if confirmed_at >= n - 2: continue
        if confirmed_at in used_bars: continue
        
        entry_price = ohlcv[confirmed_at]['o']
        is_long = seq['entry_type'] in DEMAND_ZONES
        
        if is_long:
            tp_price, tp_src, _ = find_tps(entry_price, sigs, swings_dict, ohlcv)
            sl_price, sl_src, _ = find_sls(entry_price, sigs, swings_dict, ohlcv)
        else:
            sl_price, sl_src, _ = find_tps(entry_price, sigs, swings_dict, ohlcv)
            tp_price, tp_src, _ = find_sls(entry_price, sigs, swings_dict, ohlcv)
        
        max_tp = entry_price * (1.05 if is_long else 0.95)
        if (is_long and tp_price > max_tp) or (not is_long and tp_price < max_tp):
            tp_price = max_tp
        
        tp_dist = abs(tp_price - entry_price) / entry_price * 100
        sl_dist = abs(sl_price - entry_price) / entry_price * 100
        if sl_dist > 0 and tp_dist / sl_dist < 1.0:
            continue
        
        exit_idx = -1; exit_price = 0; exit_method = 'eod'
        for i in range(confirmed_at + 1, n):
            bar = ohlcv[i]
            if is_long:
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
            exit_idx = n - 1; exit_price = ohlcv[exit_idx]['c']; exit_method = 'eod'
        if exit_idx <= confirmed_at: continue
        
        pnl = (exit_price - entry_price) / entry_price * 100
        if not is_long: pnl = -pnl
        
        pat = seq['pattern']
        pattern_results[pat]['trades'] += 1
        pattern_results[pat]['total_pnl'] += pnl
        pattern_results[pat]['total_hold'] += (exit_idx - confirmed_at)
        pattern_results[pat]['exit_methods'][exit_method] += 1
        pattern_results[pat]['stocks'].add(sym)
        if pnl > 0: pattern_results[pat]['wins'] += 1
        used_bars.add(exit_idx)
    
    if (fi+1) % 1000 == 0:
        print(f"  [{fi+1}/4800] {time.time()-t0:.0f}s")

# ═══ Report ═══
elapsed = time.time() - t0
bl_wr = bl['wins']/bl['trades']*100 if bl['trades'] else 0
bl_pnl = bl['total_pnl']/bl['trades'] if bl['trades'] else 0
bl_tp = bl['exit_methods'].get('tp_hit',0)

print(f"\n{'='*80}")
print(f"  SMC全模式序列回测 ({elapsed:.0f}s) — Baseline: {bl['trades']}笔 WR={bl_wr:.1f}% PnL={bl_pnl:+.2f}%")
print(f"{'='*80}")
print(f"  {'Pattern':12s} {'Dir':>4s} {'Trades':>6s} {'Stocks':>6s} {'WR':>6s} {'PnL':>7s} {'Hold':>5s} {'TP%':>5s} {'SL%':>5s}")
print(f"  {'─'*12} {'─'*4} {'─'*6} {'─'*6} {'─'*6} {'─'*7} {'─'*5} {'─'*5} {'─'*5}")

# All patterns
all_pats = sorted(pattern_results.items(), key=lambda x: x[1]['wins']/max(x[1]['trades'],1), reverse=True)
for pat, pr in all_pats:
    if pr['trades'] < 5: continue
    wr = pr['wins']/pr['trades']*100
    pnl = pr['total_pnl']/pr['trades']
    hold = pr['total_hold']/pr['trades']
    tp = pr['exit_methods'].get('tp_hit',0)
    sl = pr['exit_methods'].get('sl_hit',0)
    direction = 'Long' if any(t in DEMAND_ZONES for t in [s[0] for s in LONG_PATTERNS if s[0]==pat]) else \
                'Short' if any(t in SUPPLY_ZONES for t in [s[0] for s in SHORT_PATTERNS if s[0]==pat]) else \
                ('Long' if '→' in pat and pat.split('→')[-1] in ['D','S→D','L→S→D'] else 'Short')
    # Better direction detection
    is_long = False
    for lp in LONG_PATTERNS:
        if lp[0] == pat: is_long = True; break
    direction = 'Long' if is_long else 'Short'
    print(f"  {pat:12s} {direction:>4s} {pr['trades']:>6d} {len(pr['stocks']):>6d} {wr:>5.1f}% {pnl:>+6.2f}% {hold:>4.1f}b {tp/pr['trades']*100:>4.0f}% {sl/pr['trades']*100:>4.0f}%")
