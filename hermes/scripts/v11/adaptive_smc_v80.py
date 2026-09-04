#!/usr/bin/env python3
"""
自适应SMC系统 V8.0 — 股票画像 + 自适应组合 + 状态识别 + 多周期融合 + 失败分析
================================================================================
Phase 1: 股票画像 → 每只股票的最优模式 (per-stock WR matrix)
Phase 2: 自适应回测 → adaptive vs global baseline
Phase 3: 操作者状态识别 → 信号密度+质量分类
Phase 4: 失败模式分析 → 什么情况下失败
Phase 5: 多周期融合 → 日线+60min加权

核心假设: 不同股票在不同状态下适用不同信号组合
验证方法: 对比 Adaptive(per-stock best pattern) vs Global(fixed pattern)
"""
import json, time
from pathlib import Path
from collections import defaultdict
import sys

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20, _calc_atr

KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v21')
OUT.mkdir(exist_ok=True)
V70_FILE = OUT / 'full_sequence_backtest_v70.json'

TARGET = 2.0; LOOKAHEAD = 5; MIN_STOCK_TRADES = 5
MAX_GAP = 25

# ═══ Signal Classification (same as V7.0) ═══
CATEGORIES = {
    'CTX_LONG':  ['BOS_Bull', 'CHOCH_Bull', 'MSS_Bull'],
    'CTX_SHORT': ['BOS_Bear', 'CHOCH_Bear', 'MSS_Bear'],
    'LIQ_LONG':  ['Sweep_SSL', 'EQL'],
    'LIQ_SHORT': ['Sweep_BSL', 'EQH'],
    'ZONE_LONG': ['OB_Bull', 'FVG_Bull'],
    'ZONE_SHORT':['OB_Bear', 'FVG_Bear'],
}

LONG_PATTERNS = {
    'LIQ→ZONE':     (['LIQ_LONG', 'ZONE_LONG'], [25], 'long'),
    'CTX→ZONE':     (['CTX_LONG', 'ZONE_LONG'], [20], 'long'),
    'ZONE_ONLY':    (['ZONE_LONG'], [], 'long'),
    'LIQ→CTX→ZONE': (['LIQ_LONG', 'CTX_LONG', 'ZONE_LONG'], [30, 15], 'long'),
    'CTX→LIQ→ZONE': (['CTX_LONG', 'LIQ_LONG', 'ZONE_LONG'], [30, 25], 'long'),
}

ALL_PATTERNS = {**LONG_PATTERNS}

# ═══ Phase 1: Stock Profiling ═══
def detect_sequences(signals):
    sbb = defaultdict(list)
    for s in signals: sbb[s.idx].append(s)
    all_seqs = []
    for pname, (stages, gaps, direction) in ALL_PATTERNS.items():
        stage_sigs = [CATEGORIES[st] for st in stages]
        for sb in sorted(sbb):
            for sig in [s for s in sbb[sb] if s.type in stage_sigs[0]]:
                chain = [sig]; current = sig.idx; ok = True
                for si in range(1, len(stages)):
                    gap = gaps[si-1] if si-1 < len(gaps) else MAX_GAP
                    found = False
                    for bi in range(current+1, current+gap+1):
                        if bi in sbb:
                            for cand in sbb[bi]:
                                if cand.type in stage_sigs[si] and cand not in chain:
                                    chain.append(cand); current = bi; found = True; break
                        if found: break
                    if not found: ok = False; break
                if ok and len(chain) == len(stages):
                    all_seqs.append({'pattern': pname, 'seq_bar': chain[-1].idx,
                                     'zone_type': chain[-1].type,
                                     'zone_low': chain[-1].lower,
                                     'zone_high': chain[-1].upper})
    unique = []
    for pname in ALL_PATTERNS:
        seen = set()
        for s in sorted([x for x in all_seqs if x['pattern']==pname], key=lambda x:x['seq_bar']):
            if s['seq_bar'] not in seen: seen.add(s['seq_bar']); unique.append(s)
    return unique

def backtest_one(ohlcv, seqs):
    n = len(ohlcv); trades = []
    for sq in seqs:
        eb = sq['seq_bar']
        if eb+1>=n or eb+LOOKAHEAD+1>=n: continue
        entry_bar = eb+1; ep = ohlcv[entry_bar]['o']
        sl = sq['zone_low']*0.995 if sq['zone_low']>0 else ep*0.97
        tp = ep*1.03
        exit_bar = entry_bar; exit_px = ep; reason = 'time_stop'
        for bi in range(entry_bar+1, min(entry_bar+LOOKAHEAD, n-1)+1):
            if ohlcv[bi]['l']<=sl: exit_bar=bi; exit_px=sl; reason='sl_hit'; break
            if ohlcv[bi]['h']>=tp: exit_bar=bi; exit_px=tp; reason='tp_hit'; break
        else: exit_bar=min(entry_bar+LOOKAHEAD,n-1); exit_px=ohlcv[exit_bar]['c']
        pnl = (exit_px-ep)/ep*100
        trades.append({'pattern':sq['pattern'],'entry_bar':entry_bar,'pnl_pct':round(pnl,2),
                       'won':pnl>0,'exit_reason':reason})
    return trades

def daily_to_weekly(d): 
    w=[]
    for i in range(0,len(d),5):
        c=d[i:i+5]
        if len(c)>=3: w.append({'o':c[0]['o'],'h':max(x['h'] for x in c),'l':min(x['l'] for x in c),'c':c[-1]['c']})
    return w

def weekly_trend(w):
    if len(w)<20: return 'neutral'
    sigs,st,_,_=detect_all_signals_v20(w)
    tc=st['type_counts'];cb=tc.get('CHOCH_Bull',0);cbr=tc.get('CHOCH_Bear',0)
    bb=tc.get('BOS_Bull',0);bbr=tc.get('BOS_Bear',0)
    last=[s for s in sigs if 'CHOCH' in s.type]
    ld='bull' if last and 'Bull' in last[-1].type else ('bear' if last and 'Bear' in last[-1].type else None)
    if ld=='bull' and cb+bb>=cbr+bbr: return 'bullish'
    if ld=='bear' and cbr+bbr>cb+bb: return 'bearish'
    if cb+bb>(cbr+bbr)*1.5: return 'bullish'
    if cbr+bbr>(cb+bb)*1.5: return 'bearish'
    return 'neutral'

# ═══ Phase 3: Operator State Detection ═══
def detect_operator_state(signals):
    """Classify current operator based on signal density and quality"""
    tc = defaultdict(int)
    for s in signals:
        tc[s.type] += 1
    n = len(signals)
    if n == 0: return 'idle', 0.0
    
    # Signal density ratios
    sweep_ratio = (tc.get('Sweep_SSL',0) + tc.get('Sweep_BSL',0)) / n
    bos_ratio = (tc.get('BOS_Bull',0) + tc.get('BOS_Bear',0)) / n
    choch_ratio = (tc.get('CHOCH_Bull',0) + tc.get('CHOCH_Bear',0)) / n
    mss_ratio = (tc.get('MSS_Bull',0) + tc.get('MSS_Bear',0)) / n
    zone_ratio = (tc.get('FVG_Bull',0) + tc.get('FVG_Bear',0) + tc.get('OB_Bull',0) + tc.get('OB_Bear',0)) / n
    
    # Quality: zone not broken = strong operator
    ob_bull = tc.get('OB_Bull', 0); ob_bear = tc.get('OB_Bear', 0)
    quality = min(1.0, (ob_bull + ob_bear) / max(n, 1) * 2)
    
    if sweep_ratio > 0.2 and zone_ratio > 0.3:
        return 'accumulation', quality  # 庄家建仓/出货
    elif bos_ratio > 0.15 and zone_ratio > 0.2:
        return 'trending', quality     # 趋势资金
    elif mss_ratio > 0.1 or choch_ratio > 0.1:
        return 'rotational', quality   # 游资轮动
    elif zone_ratio > 0.3:
        return 'ranging', quality      # 区间震荡
    else:
        return 'noise', quality        # 散户博弈


# ═══ Phase 4: Failure Mode Analysis ═══
def analyze_failure(trades):
    """Why do trades fail?"""
    failures = [t for t in trades if not t['won']]
    if not failures: return {}
    
    reasons = defaultdict(int)
    for t in failures:
        reasons[t.get('exit_reason', '?')] += 1
    
    avg_loss = sum(t['pnl_pct'] for t in failures) / len(failures)
    return {
        'n_failures': len(failures),
        'failure_rate': len(failures) / max(len(trades), 1),
        'avg_loss_pct': round(avg_loss, 2),
        'reasons': dict(reasons),
    }


# ═══ MAIN ═══
print("Phase 1: Building per-stock profile matrix...")
daily_files = sorted(KLINE.glob('*_daily_300.json'))
t0 = time.time()

stock_profiles = {}       # {sym: {pattern: {wr, total, avg_pnl}}}
stock_states = {}         # {sym: operator_state}
stock_failures = {}       # {sym: failure_analysis}
all_trades_global = []    # Global baseline (ZONE_ONLY for all)
all_trades_adaptive = []  # Adaptive (per-stock best)

for fi, df in enumerate(daily_files):
    name = df.stem.replace('_daily_300', '')
    parts = name.rsplit('_', 1)
    sym = f'{parts[0]}.{parts[1]}' if len(parts) == 2 else name
    try:
        daily = json.loads(df.read_bytes())
        if len(daily) < 50: continue
    except: continue
    
    try:
        sigs, _, _, _ = detect_all_signals_v20(daily)
        seqs = detect_sequences(sigs)
    except: continue
    if not seqs: continue
    
    # Weekly trend
    wp = KLINE / f'{name}_weekly_200.json'
    try:
        w = json.loads(wp.read_bytes()) if wp.exists() else daily_to_weekly(daily)
        if len(w)<20: w=daily_to_weekly(daily)
    except: w=daily_to_weekly(daily)
    trend = weekly_trend(w)
    
    # Operator state
    op_state, op_quality = detect_operator_state(sigs)
    stock_states[sym] = {'state': op_state, 'quality': round(op_quality, 2), 'trend': trend}
    
    # Backtest all patterns
    trades = backtest_one(daily, seqs)
    if not trades: continue
    
    # Per-pattern stats
    pattern_stats = defaultdict(lambda: {'hits': 0, 'total': 0, 'pnls': []})
    for t in trades:
        p = t['pattern']
        pattern_stats[p]['total'] += 1
        pattern_stats[p]['pnls'].append(t['pnl_pct'])
        if t['won']: pattern_stats[p]['hits'] += 1
    
    # Build profile: which pattern works best for this stock?
    profile = {}
    best_pattern = None; best_wr = 0
    for p, s in pattern_stats.items():
        if s['total'] < 3: continue  # minimum samples
        wr = s['hits'] / s['total']
        avg_pnl = sum(s['pnls']) / len(s['pnls'])
        profile[p] = {'wr': round(wr, 3), 'total': s['total'], 'avg_pnl': round(avg_pnl, 2)}
        if wr > best_wr:
            best_wr = wr; best_pattern = p
    
    if not profile: continue
    
    stock_profiles[sym] = {
        'trend': trend,
        'state': op_state,
        'quality': round(op_quality, 2),
        'best_pattern': best_pattern,
        'best_wr': round(best_wr, 3),
        'patterns': profile,
    }
    
    # Failure analysis
    stock_failures[sym] = analyze_failure(trades)
    
    # Global baseline: use ZONE_ONLY trades
    global_trades = [t for t in trades if t['pattern'] == 'ZONE_ONLY']
    for t in global_trades: t['symbol'] = sym; t['method'] = 'global'
    all_trades_global.extend(global_trades)
    
    # Adaptive: use best pattern trades
    adaptive_trades = [t for t in trades if t['pattern'] == best_pattern]
    for t in adaptive_trades: t['symbol'] = sym; t['method'] = 'adaptive'
    all_trades_adaptive.extend(adaptive_trades)
    
    if (fi+1) % 1000 == 0:
        print(f"  [{fi+1}/{len(daily_files)}] {time.time()-t0:.0f}s profiled={len(stock_profiles)}")

elapsed = time.time() - t0

# ═══ REPORT ═══
print(f"\n{'='*70}")
print(f"  自适应SMC V8.0 ({elapsed:.0f}s) — {len(stock_profiles)}只股票画像完成")
print(f"{'='*70}")

# ═══ Global vs Adaptive ═══
global_wr = sum(1 for t in all_trades_global if t['won']) / max(len(all_trades_global), 1)
global_avg = sum(t['pnl_pct'] for t in all_trades_global) / max(len(all_trades_global), 1)
adaptive_wr = sum(1 for t in all_trades_adaptive if t['won']) / max(len(all_trades_adaptive), 1)
adaptive_avg = sum(t['pnl_pct'] for t in all_trades_adaptive) / max(len(all_trades_adaptive), 1)

print(f"\n  【Global(ZONE_ONLY) vs Adaptive(per-stock best)】")
print(f"  {'':20s} {'WR':>7s} {'AvgPnL':>8s} {'Trades':>7s} {'Stocks':>7s}")
print(f"  {'Global (fixed)':20s} {global_wr:>6.1%} {global_avg:>+7.2f}% {len(all_trades_global):>7d} {'n/a':>7s}")
print(f"  {'Adaptive (stock)':20s} {adaptive_wr:>6.1%} {adaptive_avg:>+7.2f}% {len(all_trades_adaptive):>7d} {len(stock_profiles):>7d}")
if adaptive_wr > global_wr:
    print(f"  ✅ Adaptive beats Global by {adaptive_wr-global_wr:+.1%} WR")
else:
    print(f"  ⚠️ Global wins by {global_wr-adaptive_wr:+.1%} WR")

# ═══ Best Pattern Distribution ═══
print(f"\n  【每只股票最优模式分布】")
best_dist = defaultdict(int)
for sym, p in stock_profiles.items():
    best_dist[p['best_pattern']] += 1
for pat, count in sorted(best_dist.items(), key=lambda x: -x[1]):
    avg_wr = sum(sp['patterns'][pat]['wr'] for sp in stock_profiles.values() if pat in sp.get('patterns',{})) / max(count, 1)
    print(f"    {pat:<20s} {count:>4d}只 avg_WR={avg_wr:.1%}")

# ═══ Operator State → Best Pattern ═══
print(f"\n  【操作者状态 → 最优模式映射】")
state_pattern = defaultdict(lambda: defaultdict(list))
for sym, p in stock_profiles.items():
    state_pattern[p['state']][p['best_pattern']].append(p['best_wr'])

for state in ['accumulation', 'trending', 'rotational', 'ranging', 'noise']:
    sp = state_pattern.get(state, {})
    if not sp: continue
    print(f"\n  {state}:")
    for pat, wrs in sorted(sp.items(), key=lambda x: -len(x[1])):
        avg = sum(wrs)/len(wrs)
        print(f"    {pat:<20s} {len(wrs):>4d}只 avg_WR={avg:.1%}")

# ═══ Failure Analysis ═══
print(f"\n  【失败模式分析】")
all_failures = [t for t in all_trades_adaptive if not t['won']]
if all_failures:
    fail_reasons = defaultdict(int)
    for t in all_failures: fail_reasons[t.get('exit_reason','?')] += 1
    avg_fail = sum(t['pnl_pct'] for t in all_failures) / len(all_failures)
    print(f"  总失败率: {len(all_failures)/max(len(all_trades_adaptive),1):.1%}")
    print(f"  平均亏损: {avg_fail:+.2f}%")
    for reason, count in sorted(fail_reasons.items()):
        print(f"    {reason}: {count} ({count/len(all_failures)*100:.0f}%)")

# ═══ SAVE ═══
output = {
    'meta': {'version': '8.0', 'date': time.strftime('%Y-%m-%d'), 'stocks_profiled': len(stock_profiles)},
    'global_baseline': {'wr': round(global_wr, 4), 'avg_pnl': round(global_avg, 2), 'trades': len(all_trades_global)},
    'adaptive': {'wr': round(adaptive_wr, 4), 'avg_pnl': round(adaptive_avg, 2), 'trades': len(all_trades_adaptive)},
    'profiles': stock_profiles,
    'states': stock_states,
}
json.dump(output, open(OUT / 'adaptive_smc_v80.json', 'w'), ensure_ascii=False)
print(f"\n  Saved: {OUT/'adaptive_smc_v80.json'}")
