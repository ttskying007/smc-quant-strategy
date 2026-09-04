#!/usr/bin/env python3
"""
SMC 全信号分类 × 全量时间顺序组合 验证 V7.0
============================================
信号分类:
  CTX_LONG/BULL: BOS_Bull, CHOCH_Bull, MSS_Bull     (上行背景)
  CTX_SHORT/BEAR: BOS_Bear, CHOCH_Bear, MSS_Bear    (下行背景)
  LIQ_LONG: Sweep_SSL, EQL                          (多头流动性事件)
  LIQ_SHORT: Sweep_BSL, EQH                         (空头流动性事件)
  ZONE_LONG: OB_Bull, FVG_Bull                      (需求区POI)
  ZONE_SHORT: OB_Bear, FVG_Bear                     (供给区POI)
  CONFLUENCE: BPR                                   (平衡价格区)

时间顺序序列 (LONG方向, 按出现时间从左到右):
  1-stage: ZONE→Entry
  2-stage: LIQ→ZONE→Entry, CTX→ZONE→Entry
  3-stage: CTX→LIQ→ZONE→Entry, LIQ→CTX→ZONE→Entry
  4-stage: CTX→LIQ→CTX→ZONE→Entry (full SMC flow)

验证: 每只股票→检测序列→T+1入场→5bar目标+2%
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
MAX_GAP = 25  # max bars between stages

# ═══ Signal Classification ═══
CATEGORIES = {
    'CTX_LONG':  ['BOS_Bull', 'CHOCH_Bull', 'MSS_Bull'],
    'CTX_SHORT': ['BOS_Bear', 'CHOCH_Bear', 'MSS_Bear'],
    'LIQ_LONG':  ['Sweep_SSL', 'EQL'],
    'LIQ_SHORT': ['Sweep_BSL', 'EQH'],
    'ZONE_LONG': ['OB_Bull', 'FVG_Bull'],
    'ZONE_SHORT':['OB_Bear', 'FVG_Bear'],
    'CONFLUENCE':['BPR'],
}

# ═══ Time-Ordered Sequence Patterns ═══
# Each pattern: (stages, gaps_between_stages, direction)
# stages = list of category names, must appear in time order
# gaps = max bars between consecutive stages

LONG_PATTERNS = {
    # 1-stage: just zone
    'ZONE_ONLY':       (['ZONE_LONG'], [], 'long'),
    
    # 2-stage: liquidity + zone
    'LIQ→ZONE':        (['LIQ_LONG', 'ZONE_LONG'], [25], 'long'),
    'CTX→ZONE':        (['CTX_LONG', 'ZONE_LONG'], [20], 'long'),
    
    # 2-stage with confluence
    'LIQ→ZONE+BPR':    (['LIQ_LONG', 'ZONE_LONG', 'CONFLUENCE'], [25, 10], 'long'),
    'CTX→ZONE+BPR':    (['CTX_LONG', 'ZONE_LONG', 'CONFLUENCE'], [20, 10], 'long'),
    
    # 3-stage: full SMC flow
    'LIQ→CTX→ZONE':    (['LIQ_LONG', 'CTX_LONG', 'ZONE_LONG'], [30, 15], 'long'),
    'CTX→LIQ→ZONE':    (['CTX_LONG', 'LIQ_LONG', 'ZONE_LONG'], [30, 25], 'long'),
    
    # 4-stage: full flow with confluence
    'CTX→LIQ→CTX→ZONE':(['CTX_LONG', 'LIQ_LONG', 'CTX_LONG', 'ZONE_LONG'], [30, 15, 10], 'long'),
    'LIQ→CTX→ZONE+BPR':(['LIQ_LONG', 'CTX_LONG', 'ZONE_LONG', 'CONFLUENCE'], [30, 15, 10], 'long'),
}

SHORT_PATTERNS = {
    'ZONE_ONLY_S':      (['ZONE_SHORT'], [], 'short'),
    'LIQ→ZONE_S':       (['LIQ_SHORT', 'ZONE_SHORT'], [25], 'short'),
    'CTX→ZONE_S':       (['CTX_SHORT', 'ZONE_SHORT'], [20], 'short'),
    'CTX→LIQ→ZONE_S':   (['CTX_SHORT', 'LIQ_SHORT', 'ZONE_SHORT'], [30, 25], 'short'),
}

ALL_PATTERNS = {**LONG_PATTERNS, **SHORT_PATTERNS}
print(f"Testing {len(ALL_PATTERNS)} sequence patterns")

# ═══ Core logic ═══
def detect_sequences(signals):
    """Detect ALL sequence patterns from signal stream"""
    sbb = defaultdict(list)
    for s in signals:
        sbb[s.idx].append(s)
    
    all_seqs = []
    
    for pname, (stages, gaps, direction) in ALL_PATTERNS.items():
        stage_signals = [CATEGORIES[st] for st in stages]
        
        for sb in sorted(sbb):
            for sig in [s for s in sbb[sb] if s.type in stage_signals[0]]:
                chain = [sig]
                current_bar = sig.idx
                ok = True
                
                for si in range(1, len(stages)):
                    gap = gaps[si - 1] if si - 1 < len(gaps) else MAX_GAP
                    found = False
                    for bi in range(current_bar + 1, current_bar + gap + 1):
                        if bi in sbb:
                            for cand in sbb[bi]:
                                if cand.type in stage_signals[si] and cand not in chain:
                                    chain.append(cand)
                                    current_bar = bi
                                    found = True
                                    break
                        if found: break
                    if not found:
                        ok = False
                        break
                
                if ok and len(chain) == len(stages):
                    zone_sig = chain[-1]
                    all_seqs.append({
                        'pattern': pname,
                        'direction': direction,
                        'seq_bar': zone_sig.idx,
                        'zone_type': zone_sig.type,
                        'zone_low': round(zone_sig.lower, 2),
                        'zone_high': round(zone_sig.upper, 2),
                        'signals': [{'type': s.type, 'bar': s.idx, 'price': s.price} for s in chain],
                        'n_stages': len(stages),
                    })
    
    # Dedup per pattern (allow same zone in different patterns)
    unique = []
    for pname in ALL_PATTERNS:
        pattern_seqs = [s for s in all_seqs if s['pattern'] == pname]
        seen = set()
        for s in sorted(pattern_seqs, key=lambda x: x['seq_bar']):
            if s['seq_bar'] not in seen:
                seen.add(s['seq_bar'])
                unique.append(s)
    return unique


def backtest_sequences(ohlcv, seqs):
    """T+1 close entry, 2% target in 5 bars"""
    n = len(ohlcv)
    trades = []
    
    for sq in seqs:
        seq_bar = sq['seq_bar']
        if seq_bar + 1 >= n: continue  # T+1
        if seq_bar + LOOKAHEAD + 1 >= n: continue
        
        entry_bar = seq_bar + 1
        entry_price = ohlcv[entry_bar]['o']
        zone_low = sq['zone_low']
        
        # SL: just below zone
        sl_price = zone_low * 0.995 if zone_low > 0 else entry_price * 0.97
        # TP: 3% target
        tp_price = entry_price * 1.03
        
        # Simulate
        exit_bar = entry_bar
        exit_price = entry_price
        exit_reason = 'time_stop'
        
        max_hold = min(entry_bar + LOOKAHEAD, n - 1)
        for bi in range(entry_bar + 1, max_hold + 1):
            if ohlcv[bi]['l'] <= sl_price:
                exit_bar = bi; exit_price = sl_price; exit_reason = 'sl_hit'; break
            if ohlcv[bi]['h'] >= tp_price:
                exit_bar = bi; exit_price = tp_price; exit_reason = 'tp_hit'; break
        else:
            exit_bar = max_hold
            exit_price = ohlcv[max_hold]['c']
        
        pnl = (exit_price - entry_price) / entry_price * 100
        trades.append({
            'pattern': sq['pattern'],
            'direction': sq['direction'],
            'n_stages': sq['n_stages'],
            'zone_type': sq['zone_type'],
            'entry_bar': entry_bar,
            'entry_price': round(entry_price, 2),
            'sl_price': round(sl_price, 2),
            'tp_price': round(tp_price, 2),
            'exit_bar': exit_bar,
            'exit_price': round(exit_price, 2),
            'exit_reason': exit_reason,
            'pnl_pct': round(pnl, 2),
            'won': pnl > 0,
        })
    
    return trades


def daily_to_weekly(daily):
    w = []
    for i in range(0, len(daily), 5):
        c = daily[i:i+5]
        if len(c) >= 3:
            w.append({'o': c[0]['o'], 'h': max(b['h'] for b in c),
                      'l': min(b['l'] for b in c), 'c': c[-1]['c']})
    return w

def weekly_smc(weekly):
    if len(weekly) < 20: return 'neutral'
    sigs, st, _, _ = detect_all_signals_v20(weekly)
    tc = st['type_counts']
    cb = tc.get('CHOCH_Bull', 0); cbr = tc.get('CHOCH_Bear', 0)
    bb = tc.get('BOS_Bull', 0); bbr = tc.get('BOS_Bear', 0)
    last = [s for s in sigs if 'CHOCH' in s.type]
    last_dir = 'bull' if last and 'Bull' in last[-1].type else ('bear' if last and 'Bear' in last[-1].type else None)
    if last_dir == 'bull' and cb + bb >= cbr + bbr: return 'bullish'
    if last_dir == 'bear' and cbr + bbr > cb + bb: return 'bearish'
    if cb + bb > (cbr + bbr) * 1.5: return 'bullish'
    if cbr + bbr > (cb + bb) * 1.5: return 'bearish'
    return 'neutral'


# ═══ MAIN ═══
daily_files = sorted(KLINE.glob('*_daily_300.json'))
t0 = time.time()

all_trades = []
global_pattern = defaultdict(lambda: {'hits': 0, 'total': 0, 'pnls': []})

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
    except:
        continue
    
    if not seqs: continue
    
    # Weekly trend
    weekly_path = KLINE / f'{name}_weekly_200.json'
    try:
        if weekly_path.exists():
            weekly = json.loads(weekly_path.read_bytes())
            if len(weekly) < 20: weekly = daily_to_weekly(daily)
        else:
            weekly = daily_to_weekly(daily)
    except:
        weekly = daily_to_weekly(daily)
    w_trend = weekly_smc(weekly)
    
    trades = backtest_sequences(daily, seqs)
    for t in trades:
        t['symbol'] = sym
        t['w_trend'] = w_trend
        all_trades.append(t)
        global_pattern[t['pattern']]['hits'] += 1 if t['won'] else 0
        global_pattern[t['pattern']]['total'] += 1
        global_pattern[t['pattern']]['pnls'].append(t['pnl_pct'])
    
    if (fi + 1) % 500 == 0:
        print(f"  [{fi+1}/{len(daily_files)}] {time.time()-t0:.0f}s trades={len(all_trades)} patterns={len(global_pattern)}")

elapsed = time.time() - t0

# ═══ REPORT ═══
print(f"\n{'='*75}")
print(f"  SMC 全信号分类 × 全量时间顺序组合 V7.0 ({elapsed:.0f}s)")
print(f"  扫描: {len(daily_files)} → {len(all_trades)}笔交易")
print(f"  测试: {len(ALL_PATTERNS)}个序列模式")
print(f"{'='*75}")

# Rank by WR (single trade quality!)
ranked = []
for pn, stats in global_pattern.items():
    if stats['total'] < 20: continue
    wr = stats['hits'] / stats['total']
    avg_pnl = sum(stats['pnls']) / len(stats['pnls'])
    tp_rate = sum(1 for t in all_trades if t['pattern'] == pn and t['exit_reason'] == 'tp_hit') / stats['total']
    ranked.append((pn, wr, stats['total'], stats['hits'], avg_pnl, tp_rate, ALL_PATTERNS[pn][-1]))

ranked.sort(key=lambda x: -x[1])

print(f"\n  【全模式排名 (按WR, 单笔质量优先)】")
print(f"  {'排名':>3s} {'模式':<25s} {'方向':>5s} {'WR':>6s} {'N':>6s} {'均P&L':>7s} {'TP率':>6s}")
print(f"  {'-'*60}")
for i, (pn, wr, total, hits, avg_pnl, tp_rate, direction) in enumerate(ranked):
    print(f"  {i+1:>3d} {pn:<25s} {direction:>5s} {wr:>5.1%} {total:>6d} {avg_pnl:>+6.2f}% {tp_rate:>5.0%}")

# By stage count
print(f"\n  【按阶段数聚合】")
for ns in [1, 2, 3, 4]:
    stage_trades = [t for t in all_trades if t['n_stages'] == ns]
    if not stage_trades: continue
    wr = sum(1 for t in stage_trades if t['won']) / len(stage_trades)
    avg_pnl = sum(t['pnl_pct'] for t in stage_trades) / len(stage_trades)
    print(f"  {ns}-stage: WR={wr:.1%} N={len(stage_trades)} AvgPnL={avg_pnl:+.2f}%")

# Top by trend
print(f"\n  【周线趋势 × 最佳模式】")
for trend in ['bullish', 'bearish', 'neutral']:
    trend_trades = [t for t in all_trades if t['w_trend'] == trend]
    if not trend_trades: continue
    print(f"\n  {trend}:")
    for pat in [r[0] for r in ranked[:6]]:
        pt = [t for t in trend_trades if t['pattern'] == pat]
        if len(pt) >= 10:
            wr = sum(1 for t in pt if t['won']) / len(pt)
            print(f"    {pat:<25s} WR={wr:.1%} N={len(pt)}")

# ═══ SAVE ═══
output = {
    'meta': {'version': '7.0', 'patterns_tested': len(ALL_PATTERNS),
             'date': time.strftime('%Y-%m-%d'), 'total_trades': len(all_trades)},
    'ranking': [{'pattern': pn, 'wr': round(wr, 4), 'total': total, 'avg_pnl': round(avg_pnl, 2),
                 'direction': direction} for pn, wr, total, _, avg_pnl, _, direction in ranked],
    'all_trades': all_trades,
}
json.dump(output, open(OUT / 'full_sequence_backtest_v70.json', 'w'), ensure_ascii=False)
print(f"\n  Saved: {OUT/'full_sequence_backtest_v70.json'}")
