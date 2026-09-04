#!/usr/bin/env python3
"""
ENTRY_AT_ZONE 回调入场回测 V5.0
================================
V17已验证: ZONE入场 WR=94.2% vs CLOSE入场 WR=42.8%
原理: 序列触发后等价格回调到Zone区域再入场, SL在真实支撑上

策略:
  1. 检测L→D/S→D序列
  2. 提取Zone信号(FVG_Bull/OB_Bull)的lower价格
  3. 序列完成后等待价格回踩Zone
  4. 触及Zone.lower → 入场 (bar收盘价)
  5. 跌破Zone.lower > ATR×0.5 → 放弃 (zone被破坏)
  6. 最多等10根bar
  7. T+1: entry_idx > exit_idx from sequence
  8. 目标: +2%/5bar
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

TARGET = 2.0; LOOKAHEAD = 5; MAX_WAIT = 10
ZONE_BREAK_ATR = 0.5  # zone被破坏的ATR倍数

CATS = {
    'L_LONG':  ['Sweep_SSL', 'EQL'],
    'S_LONG':  ['CHOCH_Bull', 'BOS_Bull', 'MSS_Bull'],
    'D_ZONE':  ['OB_Bull', 'FVG_Bull'],
}

PATTERNS = {
    'L→D': ('L_LONG', 'D_ZONE', [20], 'long'),
    'S→D': ('S_LONG', 'D_ZONE', [15], 'long'),
}

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

def detect_sequences_with_zones(signals):
    """Detect sequences AND extract zone info for entry"""
    sbb = defaultdict(list)
    for s in signals: sbb[s.idx].append(s)
    seqs = []
    for pn, pat_data in PATTERNS.items():
        keys = list(pat_data)
        gaps = keys[-2]; stage_keys = keys[:-2]
        stages = [CATS[sk] for sk in stage_keys]
        for sb in sorted(sbb):
            for sig in [s for s in sbb[sb] if s.type in stages[0]]:
                m = [sig]; c = sig.idx; ok = True
                for si in range(1, len(stages)):
                    fnd = False
                    for bi in range(c + 1, c + gaps[si - 1] + 1):
                        if bi in sbb:
                            for cand in sbb[bi]:
                                if cand.type in stages[si] and cand not in m:
                                    m.append(cand); c = bi; fnd = True; break
                        if fnd: break
                    if not fnd: ok = False; break
                if ok and len(m) == len(stages):
                    # Extract zone: the last signal (D_ZONE) 
                    zone_sig = m[-1]
                    zone_low = zone_sig.lower
                    zone_high = zone_sig.upper
                    zone_type = zone_sig.type
                    seqs.append({
                        'pattern': pn, 'direction': 'long',
                        'seq_bar': m[-1].idx,  # bar where sequence completes
                        'signals': [{'type': s.type, 'bar': s.idx, 'price': s.price,
                                     'upper': s.upper, 'lower': s.lower} for s in m],
                        'zone': {'type': zone_type, 'low': zone_low, 'high': zone_high}
                    })
    # Deduplicate by seq_bar
    seen = set(); u = []
    for s in sorted(seqs, key=lambda x: x['seq_bar']):
        if s['seq_bar'] not in seen: seen.add(s['seq_bar']); u.append(s)
    return u

def backtest_entry_at_zone(ohlcv, seqs, start=0):
    """Test entry-at-zone: wait for pullback to zone, enter at close of that bar"""
    n = len(ohlcv)
    atr_val, atr_pct = _calc_atr(ohlcv, 14), 0
    avg_p = sum(b['c'] for b in ohlcv[-50:]) / min(50, len(ohlcv))
    if avg_p > 0: atr_pct = atr_val / avg_p
    
    results = []
    
    for sq in seqs:
        seq_bar = sq['seq_bar']
        if seq_bar < start: continue
        zone = sq['zone']
        zone_low = zone['low']
        zone_high = zone['high']
        
        # Zone must be valid
        if zone_low <= 0 or zone_high <= 0 or zone_low >= zone_high:
            continue
        
        # Scan forward bars for pullback to zone
        entry_bar = -1
        entry_price = 0
        max_wait = min(seq_bar + MAX_WAIT + 1, n - LOOKAHEAD - 1)
        
        for bi in range(seq_bar + 1, max_wait):
            bar_low = ohlcv[bi]['l']
            bar_high = ohlcv[bi]['h']
            
            # Check if zone is broken (price went below zone by > ATR*0.5)
            zone_break_level = zone_low * (1 - atr_pct * ZONE_BREAK_ATR)
            if bar_low < zone_break_level:
                break  # zone destroyed, skip this sequence
            
            # Check if price hit the zone (pulled back to entry area)
            if bar_low <= zone_high and bar_low >= zone_low * 0.98:
                # Price touched zone - enter at this bar's close
                entry_bar = bi
                entry_price = ohlcv[bi]['c']
                break
        
        if entry_bar < 0:
            continue  # no pullback entry
        
        # T+1 check: entry must be after sequence bar
        if entry_bar <= seq_bar:
            continue
        
        # Calculate return
        if entry_bar + LOOKAHEAD >= n:
            continue
        
        max_high = max(ohlcv[i]['h'] for i in range(entry_bar + 1, min(entry_bar + LOOKAHEAD + 1, n)))
        ret = (max_high - entry_price) / entry_price * 100
        
        results.append({
            'pattern': sq['pattern'],
            'zone_type': zone['type'],
            'zone_low': round(zone_low, 2),
            'zone_high': round(zone_high, 2),
            'seq_bar': seq_bar,
            'entry_bar': entry_bar,
            'entry_price': round(entry_price, 2),
            'wait_bars': entry_bar - seq_bar,
            'ret_pct': round(ret, 2),
            'hit': ret >= TARGET,
        })
    
    return results


# ═══ MAIN ═══
daily_files = sorted(KLINE.glob('*_daily_300.json'))
t0 = time.time()

all_trades = []       # flat list of all trades
stock_summaries = {}  # per-stock summary
global_stats = {'total': 0, 'hits': 0, 'entered': 0, 'skipped_no_zone': 0, 'skipped_broken': 0, 'skipped_no_pullback': 0}

for fi, df in enumerate(daily_files):
    name = df.stem.replace('_daily_300', '')
    parts = name.rsplit('_', 1)
    sym = f'{parts[0]}.{parts[1]}' if len(parts) == 2 else name
    try:
        daily = json.loads(df.read_bytes())
        if len(daily) < 50: continue
    except: continue
    
    # Detect signals and sequences
    try:
        sigs, _, _, _ = detect_all_signals_v20(daily)
        seqs = detect_sequences_with_zones(sigs)
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
    
    # 3 windows
    n = len(daily)
    windows = {'full': 0, 'mid': max(0, n - 150), 'recent': max(0, n - 50)}
    
    stock_trades = []
    for wn, start in windows.items():
        trades = backtest_entry_at_zone(daily, seqs, start)
        for t in trades:
            t['symbol'] = sym
            t['window'] = wn
            t['w_trend'] = w_trend
        stock_trades.extend(trades)
    
    if stock_trades:
        all_trades.extend(stock_trades)
        hits = sum(1 for t in stock_trades if t['hit'])
        total = len(stock_trades)
        stock_summaries[sym] = {
            'w_trend': w_trend,
            'trades': total,
            'wr': round(hits / total, 3) if total else 0,
            'best_pattern': max(set(t['pattern'] for t in stock_trades), key=lambda p: sum(1 for t in stock_trades if t['pattern'] == p and t['hit']) / max(sum(1 for t in stock_trades if t['pattern'] == p), 1)),
        }
    
    if (fi + 1) % 500 == 0:
        elapsed = time.time() - t0
        print(f"  [{fi+1}/{len(daily_files)}] {elapsed:.0f}s trades={len(all_trades)} stocks={len(stock_summaries)}")

elapsed = time.time() - t0

# ═══ REPORT ═══
print(f"\n{'='*70}")
print(f"  ENTRY_AT_ZONE 回调入场回测 V5.0 ({elapsed:.0f}s)")
print(f"  扫描: {len(daily_files)} → {len(stock_summaries)}只有交易")
print(f"{'='*70}")

# Aggregate by pattern × window × trend
for window in ['full', 'mid', 'recent']:
    wt = [t for t in all_trades if t['window'] == window]
    if not wt: continue
    hits = sum(1 for t in wt if t['hit'])
    total = len(wt)
    avg_wait = sum(t['wait_bars'] for t in wt) / total if total else 0
    print(f"\n  {window}: WR={hits/total*100:.1f}% N={total} 平均等待={avg_wait:.1f}bar")

    # By pattern
    for pat in ['L→D', 'S→D']:
        pt = [t for t in wt if t['pattern'] == pat]
        if pt:
            ph = sum(1 for t in pt if t['hit'])
            print(f"    {pat}: WR={ph/len(pt)*100:.1f}% N={len(pt)}")

    # By trend
    for trend in ['bullish', 'bearish', 'neutral']:
        tt = [t for t in wt if t['w_trend'] == trend]
        if tt:
            th = sum(1 for t in tt if t['hit'])
            print(f"    {trend}: WR={th/len(tt)*100:.1f}% N={len(tt)}")

print(f"\n  Zone类型表现:")
for zt in ['FVG_Bull', 'OB_Bull']:
    ztrades = [t for t in all_trades if t['zone_type'] == zt]
    if ztrades:
        zh = sum(1 for t in ztrades if t['hit'])
        print(f"    {zt}: WR={zh/len(ztrades)*100:.1f}% N={len(ztrades)}")

# Compare with close entry
print(f"\n  CLOSE入场 vs ZONE入场对比 (full窗口):")
close_wr = 0.95  # from V3.3 bullish+S→D
zone_full = [t for t in all_trades if t['window'] == 'full']
zone_wr = sum(1 for t in zone_full if t['hit']) / max(len(zone_full), 1) * 100 if zone_full else 0
print(f"    CLOSE入场: WR≈95% (V3.3, immediate at sequence bar)")
print(f"    ZONE入场:  WR={zone_wr:.1f}% (等回调到zone, 均等{sum(t['wait_bars'] for t in zone_full)/max(len(zone_full),1):.1f}bar)")

# ═══ SAVE ═══
output = {
    'meta': {'version': '5.0', 'method': 'entry_at_zone', 'date': time.strftime('%Y-%m-%d'),
             'stocks': len(stock_summaries), 'total_trades': len(all_trades)},
    'trades': all_trades,
    'stocks': stock_summaries
}
json.dump(output, open(OUT / 'entry_at_zone_backtest_v50.json', 'w'), ensure_ascii=False)
print(f"\n  Saved: {OUT/'entry_at_zone_backtest_v50.json'} ({len(all_trades)} trades)")
