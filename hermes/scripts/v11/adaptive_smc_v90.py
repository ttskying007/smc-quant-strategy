#!/usr/bin/env python3
"""
自适应SMC V9.0 — 动态SL + 多周期共振 + 状态v2 + 全面回测
===========================================================
改进:
  1. 动态SL: 操作者状态驱动 (accumulation=松/ATR×0.8, trending=中/ATR×0.5,
                            rotational=紧/ATR×0.3, ranging=中/ATR×0.4, noise=跳过)
  2. 多周期共振: 日线序列 + 60min同方向确认 (BOS/CHOCH/MSS方向一致)
  3. 状态v2: 信号密度 + 成交量 + 位置(相对摆动点) + 衰减(信号新鲜度)
  4. 全面回测: 对比 V8.0(无共振无动态SL) vs V9.0(全改进)
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

TARGET = 2.0; LOOKAHEAD = 5; MAX_GAP = 25
MIN_STOCK_TRADES = 3

CATEGORIES = {
    'CTX_LONG':  ['BOS_Bull', 'CHOCH_Bull', 'MSS_Bull'],
    'CTX_SHORT': ['BOS_Bear', 'CHOCH_Bear', 'MSS_Bear'],
    'LIQ_LONG':  ['Sweep_SSL', 'EQL'],
    'LIQ_SHORT': ['Sweep_BSL', 'EQH'],
    'ZONE_LONG': ['OB_Bull', 'FVG_Bull'],
    'ZONE_SHORT':['OB_Bear', 'FVG_Bear'],
}

PATTERNS = {
    'LIQ→ZONE':     (['LIQ_LONG', 'ZONE_LONG'], [25]),
    'CTX→ZONE':     (['CTX_LONG', 'ZONE_LONG'], [20]),
    'ZONE_ONLY':    (['ZONE_LONG'], []),
    'LIQ→CTX→ZONE': (['LIQ_LONG', 'CTX_LONG', 'ZONE_LONG'], [30, 15]),
    'CTX→LIQ→ZONE': (['CTX_LONG', 'LIQ_LONG', 'ZONE_LONG'], [30, 25]),
}

# ═══ Dynamic SL multipliers by operator state ═══
SL_MULTIPLIERS = {
    'accumulation': 0.8,   # 庄家建仓 - 较松,容忍洗盘
    'trending':     0.5,   # 趋势延续 - 适中
    'rotational':   0.3,   # 游资轮动 - 紧,快速止损
    'ranging':      0.4,   # 区间震荡 - 中紧
    'noise':        0.0,   # 散户博弈 - 不交易
}

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

# ═══ State Detection V2 ═══
def detect_state_v2(signals, ohlcv):
    """Enhanced operator detection: density + volume + position + decay"""
    n_total = len(signals)
    if n_total == 0: return 'noise', 0.0, {}
    
    tc = defaultdict(int)
    for s in signals: tc[s.type] += 1
    
    N = len(ohlcv)
    recent = [s for s in signals if s.idx > N - 50]
    n_recent = len(recent)
    
    # 1. Signal density (signals per bar in recent window)
    density = n_recent / max(50, 1) if n_recent > 0 else 0
    
    # 2. Volume trend (average volume of recent 20 bars vs 50 bars)
    vol_recent = sum(ohlcv[i].get('v',0) for i in range(max(0,N-20), N)) / 20
    vol_all = sum(ohlcv[i].get('v',0) for i in range(N)) / max(N,1)
    vol_ratio = vol_recent / max(vol_all, 1) if vol_all > 0 else 1.0
    
    # 3. Signal position (zone signals near swing points = strong)
    zone_at_structure = 0
    for s in signals:
        if s.type in ('OB_Bull','OB_Bear','FVG_Bull','FVG_Bear'):
            if s.metadata.get('at_structure', False):
                zone_at_structure += 1
    zone_quality = zone_at_structure / max(tc.get('OB_Bull',0)+tc.get('OB_Bear',0)+tc.get('FVG_Bull',0)+tc.get('FVG_Bear',0), 1)
    
    # 4. Signal decay (ratio of recent signals to all signals)
    decay = n_recent / max(n_total, 1)
    
    # 5. Direction bias
    bull_sigs = tc.get('BOS_Bull',0)+tc.get('CHOCH_Bull',0)+tc.get('MSS_Bull',0)+tc.get('OB_Bull',0)+tc.get('FVG_Bull',0)
    bear_sigs = tc.get('BOS_Bear',0)+tc.get('CHOCH_Bear',0)+tc.get('MSS_Bear',0)+tc.get('OB_Bear',0)+tc.get('FVG_Bear',0)
    direction_bias = (bull_sigs - bear_sigs) / max(bull_sigs+bear_sigs, 1)
    
    # Classification logic - balanced thresholds
    sweep_ratio = (tc.get('Sweep_SSL',0)+tc.get('Sweep_BSL',0)) / max(n_total,1)
    bos_ratio = (tc.get('BOS_Bull',0)+tc.get('BOS_Bear',0)) / max(n_total,1)
    
    quality = min(1.0, zone_quality * 0.4 + density * 0.3 + decay * 0.3)
    
    # Stricter, more balanced classification
    if sweep_ratio > 0.15 and vol_ratio > 1.3 and zone_quality > 0.4:
        state = 'accumulation'  # high sweep + strong volume + quality zones
    elif bos_ratio > 0.12 and abs(direction_bias) > 0.5:
        state = 'trending'      # strong BOS dominance + clear direction
    elif density > 0.12 and abs(direction_bias) < 0.3 and sweep_ratio < 0.1:
        state = 'ranging'       # active but directionless, no sweeps
    elif sweep_ratio > 0.12 and density > 0.08:
        state = 'rotational'    # sweeps + moderate activity
    elif density < 0.05:
        state = 'noise'         # very sparse signals
    else:
        state = 'ranging'       # default: treat as ranging
    
    metrics = {
        'density': round(density, 3),
        'vol_ratio': round(vol_ratio, 2),
        'zone_quality': round(zone_quality, 2),
        'decay': round(decay, 2),
        'direction_bias': round(direction_bias, 2),
    }
    return state, round(quality, 2), metrics

# ═══ 60min Direction Check ═══
def get_60min_direction(sym, daily_bar_idx):
    """Check 60min direction around daily bar. 
    Returns: 'bull'/'bear'/'neutral' or None if no data"""
    name = sym.replace('.', '_')
    m60_path = KLINE / f'{name}_60min_500.json'
    if not m60_path.exists(): return None
    
    try:
        m60 = json.loads(m60_path.read_bytes())
        if len(m60) < 30: return None
    except:
        return None
    
    # Approximate: last 50 60min bars (about 12 daily bars equivalent)
    recent = m60[-50:]
    sigs, st, _, _ = detect_all_signals_v20(recent)
    tc = st.get('type_counts', {})
    
    bull = tc.get('BOS_Bull',0) + tc.get('CHOCH_Bull',0) + tc.get('MSS_Bull',0)
    bear = tc.get('BOS_Bear',0) + tc.get('CHOCH_Bear',0) + tc.get('MSS_Bear',0)
    
    if bull > bear * 1.5: return 'bull'
    if bear > bull * 1.5: return 'bear'
    return 'neutral'


# ═══ Sequence Detection (same as V8.0) ═══
def detect_sequences(signals):
    sbb = defaultdict(list)
    for s in signals: sbb[s.idx].append(s)
    all_seqs = []
    for pname, (stages, gaps) in PATTERNS.items():
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
    for pname in PATTERNS:
        seen = set()
        for s in sorted([x for x in all_seqs if x['pattern']==pname], key=lambda x:x['seq_bar']):
            if s['seq_bar'] not in seen: seen.add(s['seq_bar']); unique.append(s)
    return unique


# ═══ V8 Simple SL backtest (for pattern selection) ═══
def backtest_v8_simple(ohlcv, seqs):
    """V8.0 style: zone_low * 0.995 SL, no state adjustment"""
    n = len(ohlcv)
    trades = []
    for sq in seqs:
        eb = sq['seq_bar']
        if eb+1 >= n or eb+LOOKAHEAD+1 >= n: continue
        ep = ohlcv[eb+1]['o']
        sl = sq['zone_low'] * 0.995 if sq['zone_low'] > 0 else ep * 0.97
        tp = ep * 1.03
        exit_px = ep; reason = 'time_stop'
        for bi in range(eb+2, min(eb+LOOKAHEAD+1, n-1)+1):
            if ohlcv[bi]['l'] <= sl: exit_px = sl; reason = 'sl_hit'; break
            if ohlcv[bi]['h'] >= tp: exit_px = tp; reason = 'tp_hit'; break
        else: exit_px = ohlcv[min(eb+LOOKAHEAD, n-1)]['c']
        pnl = (exit_px - ep) / ep * 100
        trades.append({'won': pnl > 0, 'pnl_pct': round(pnl, 2)})
    return trades


# ═══ Backtest with Dynamic SL + Multi-TF ═══
def backtest_v9(ohlcv, seqs, state, atr_pct, require_60min=False, sym=''):
    n = len(ohlcv)
    trades = []
    
    sl_mult = SL_MULTIPLIERS.get(state, 0.5)
    if sl_mult == 0: return []  # noise state: no trades
    
    for sq in seqs:
        eb = sq['seq_bar']
        if eb+1>=n or eb+LOOKAHEAD+1>=n: continue
        
        # Multi-TF resonance check
        if require_60min:
            m60_dir = get_60min_direction(sym, eb)
            if m60_dir is None: continue  # no 60min data
            if m60_dir != 'bull':
                continue  # 60min not confirming daily bullish
        
        entry_bar = eb+1; ep = ohlcv[entry_bar]['o']
        
        # Dynamic SL: base on zone, adjust by state
        base_sl = sq['zone_low'] * 0.995 if sq['zone_low']>0 else ep*0.98
        # State adjustment: add ATR buffer
        state_buffer = atr_pct * ep * sl_mult
        sl_price = base_sl - state_buffer
        sl_price = max(sl_price, ep * 0.95)  # floor: max 5% loss
        
        tp_price = ep * 1.03
        
        exit_bar = entry_bar; exit_px = ep; reason = 'time_stop'
        for bi in range(entry_bar+1, min(entry_bar+LOOKAHEAD, n-1)+1):
            if ohlcv[bi]['l'] <= sl_price:
                exit_bar=bi; exit_px=sl_price; reason='sl_hit'; break
            if ohlcv[bi]['h'] >= tp_price:
                exit_bar=bi; exit_px=tp_price; reason='tp_hit'; break
        else:
            exit_bar=min(entry_bar+LOOKAHEAD,n-1); exit_px=ohlcv[exit_bar]['c']
        
        pnl = (exit_px-ep)/ep*100
        trades.append({
            'pattern':sq['pattern'], 'entry_bar':entry_bar,
            'sl_price':round(sl_price,2), 'tp_price':round(tp_price,2),
            'exit_bar':exit_bar, 'exit_px':round(exit_px,2),
            'pnl_pct':round(pnl,2), 'won':pnl>0, 'exit_reason':reason,
        })
    return trades


# ═══ MAIN ═══
print("V9.0: Dynamic SL + Multi-TF Resonance + State V2")
daily_files = sorted(KLINE.glob('*_daily_300.json'))
t0 = time.time()

# Run 2 variants:
# V9a: State v2 + Dynamic SL (no 60min)
# V9b: State v2 + Dynamic SL + 60min resonance

all_v9a = []
all_v9b = []
stock_stats = {}
state_dist = defaultdict(int)

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
    
    # State V2
    state, quality, metrics = detect_state_v2(sigs, daily)
    state_dist[state] += 1
    
    # ATR
    atr_pct = _calc_atr(daily, 14)
    avg_p = sum(b['c'] for b in daily[-50:]) / min(50, len(daily))
    if avg_p > 0: atr_pct = atr_pct / avg_p
    
    # ── Per-stock pattern selection (use V8 fixed SL for selection) ──
    all_seqs_by_pattern = defaultdict(list)
    for sq in seqs:
        all_seqs_by_pattern[sq['pattern']].append(sq)
    
    best_pattern = 'ZONE_ONLY'; best_wr = 0
    
    for pname, pseqs in all_seqs_by_pattern.items():
        if len(pseqs) < 3: continue
        # Use V8 simple SL for pattern selection
        test_trades = backtest_v8_simple(daily, pseqs)
        if test_trades:
            hits = sum(1 for t in test_trades if t['won'])
            wr = hits / len(test_trades)
            if wr > best_wr:
                best_wr = wr; best_pattern = pname
    
    best_seqs = all_seqs_by_pattern.get(best_pattern, seqs)
    
    # Backtest V9a (Dynamic SL, no 60min)
    trades_a = backtest_v9(daily, best_seqs, state, atr_pct, require_60min=False, sym=sym)
    for t in trades_a:
        t['symbol'] = sym; t['state'] = state; t['variant'] = 'v9a'; t['best_pattern'] = best_pattern
    all_v9a.extend(trades_a)
    
    # Backtest V9b (Dynamic SL + 60min resonance)
    trades_b = backtest_v9(daily, best_seqs, state, atr_pct, require_60min=True, sym=sym)
    for t in trades_b:
        t['symbol'] = sym; t['state'] = state; t['variant'] = 'v9b'; t['best_pattern'] = best_pattern
    all_v9b.extend(trades_b)
    
    if trades_a or trades_b:
        stock_stats[sym] = {'state': state, 'quality': quality, 'metrics': metrics,
                           'v9a_trades': len(trades_a), 'v9b_trades': len(trades_b)}
    
    if (fi+1) % 1000 == 0:
        print(f"  [{fi+1}/{len(daily_files)}] {time.time()-t0:.0f}s v9a={len(all_v9a)} v9b={len(all_v9b)}")

elapsed = time.time() - t0

# ═══ REPORT ═══
print(f"\n{'='*70}")
print(f"  V9.0 自适应SMC ({elapsed:.0f}s)")
print(f"  扫描: {len(daily_files)} → v9a:{len(all_v9a)}笔 v9b:{len(all_v9b)}笔")
print(f"\n  状态分布: {dict(sorted(state_dist.items(), key=lambda x:-x[1]))}")
print(f"{'='*70}")

# Compare variants
for variant, trades in [('V9a (State+DynamicSL)', all_v9a), ('V9b (State+DSL+60min)', all_v9b)]:
    if not trades: continue
    wins = sum(1 for t in trades if t['won'])
    wr = wins / len(trades)
    avg_pnl = sum(t['pnl_pct'] for t in trades) / len(trades)
    tp_rate = sum(1 for t in trades if t['exit_reason']=='tp_hit') / len(trades)
    sl_rate = sum(1 for t in trades if t['exit_reason']=='sl_hit') / len(trades)
    avg_loss = sum(t['pnl_pct'] for t in trades if not t['won']) / max(sum(1 for t in trades if not t['won']), 1)
    print(f"\n  {variant}:")
    print(f"    WR={wr:.1%} PnL={avg_pnl:+.2f}% N={len(trades)}")
    print(f"    TP={tp_rate:.0%} SL={sl_rate:.0%} AvgLoss={avg_loss:+.2f}%")

# By state performance (V9a)
print(f"\n  【V9a 按操作者状态】")
for state in ['accumulation', 'trending', 'rotational', 'ranging']:
    st = [t for t in all_v9a if t['state'] == state]
    if not st: continue
    wr = sum(1 for t in st if t['won']) / len(st)
    avg = sum(t['pnl_pct'] for t in st) / len(st)
    print(f"    {state:15s} WR={wr:.1%} AvgPnL={avg:+.2f}% N={len(st)}")

# Compare against V8.0 baseline
v80_wr = 0.803
v9a_wr = sum(1 for t in all_v9a if t['won']) / max(len(all_v9a), 1)
print(f"\n  【对比】 V8.0(Global best)=80.3% vs V9a={v9a_wr:.1%} vs V9b={sum(1 for t in all_v9b if t['won'])/max(len(all_v9b),1):.1%}")

# ═══ SAVE ═══
output = {
    'meta': {'version': '9.0', 'date': time.strftime('%Y-%m-%d'),
             'v8_baseline_wr': 0.803,
             'state_distribution': dict(state_dist)},
    'v9a': {'wr': round(v9a_wr, 4), 'trades': len(all_v9a)},
    'v9b': {'wr': round(sum(1 for t in all_v9b if t['won'])/max(len(all_v9b),1), 4), 'trades': len(all_v9b)},
    'stock_stats': stock_stats,
}
json.dump(output, open(OUT / 'adaptive_smc_v90.json', 'w'), ensure_ascii=False)
print(f"\n  Saved: {OUT/'adaptive_smc_v90.json'}")
