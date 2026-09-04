#!/usr/bin/env python3
"""
完整逐笔交易回测 V6.0
=====================
每笔交易记录:
  入场: bar/date/price/signal_type/pattern/SL/TP
  出场: bar/date/price/reason(tp_hit/sl_hit/trailing/time_stop)
  结果: P&L%/hold_bars/RR

策略: V3.3序列系统 (close entry, WR≈95%)
      周线趋势过滤 + L→D/S→D序列 + T+1
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

LOOKAHEAD = 10  # max hold for TP/SL detection
MIN_SAMPLES = 3

CATS = {
    'L_LONG':  ['Sweep_SSL', 'EQL'],
    'S_LONG':  ['CHOCH_Bull', 'BOS_Bull', 'MSS_Bull'],
    'D_ZONE':  ['OB_Bull', 'FVG_Bull'],
}
PATTERNS = {
    'L→D': ('L_LONG', 'D_ZONE', [20], 'long'),
    'S→D': ('S_LONG', 'D_ZONE', [15], 'long'),
}

def fmt_date(d):
    s = str(d).strip()
    if len(s) >= 10 and s[4]=='-' and s[7]=='-': return s[:10]
    if len(s)==8 and s.isdigit(): return f'{s[:4]}-{s[4:6]}-{s[6:8]}'
    return s

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

def detect_sequences(signals):
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
                    zone_sig = m[-1]
                    seqs.append({
                        'pattern': pn, 'direction': 'long',
                        'seq_bar': m[-1].idx,
                        'zone_type': zone_sig.type,
                        'zone_low': round(zone_sig.lower, 2),
                        'zone_high': round(zone_sig.upper, 2),
                        'signals': [{'type': s.type, 'bar': s.idx} for s in m],
                    })
    seen = set(); u = []
    for s in sorted(seqs, key=lambda x: x['seq_bar']):
        if s['seq_bar'] not in seen: seen.add(s['seq_bar']); u.append(s)
    return u

def backtest_with_exit_detail(ohlcv, dates, seqs, start=0):
    """Full trade simulation with exit reason tracking"""
    n = len(ohlcv)
    trades = []
    used_bars = set()
    
    # Find swing highs for TP
    swings = _find_swings(ohlcv)
    
    for sq in seqs:
        seq_bar = sq['seq_bar']
        if seq_bar < start: continue
        if seq_bar + 1 >= n: continue  # T+1
        if seq_bar in used_bars: continue
        
        entry_bar = seq_bar + 1  # T+1: enter next bar
        if entry_bar >= n - 2: continue
        
        entry_price = ohlcv[entry_bar]['o']  # open of next bar
        zone_low = sq['zone_low']
        zone_high = sq['zone_high']
        
        # SL: just below zone (zone_low - 0.5%), min 0.3%
        sl_pct = max(0.003, (entry_price - zone_low) / entry_price * 0.5)
        sl_price = entry_price * (1 - sl_pct)
        
        # TP: find next swing high above entry
        tp_price = 0
        for sw in swings:
            if sw['bar'] > seq_bar and sw['type'] == 'H' and sw['price'] > entry_price:
                tp_price = sw['price']
                break
        if tp_price <= entry_price:
            tp_price = entry_price * 1.03  # fallback 3%
        
        # Simulate exit
        exit_bar = entry_bar
        exit_price = entry_price
        exit_reason = 'time_stop'
        hold_bars = 0
        
        max_hold = min(entry_bar + LOOKAHEAD, n - 1)
        
        for bi in range(entry_bar + 1, max_hold + 1):
            bar_h = ohlcv[bi]['h']
            bar_l = ohlcv[bi]['l']
            bar_o = ohlcv[bi]['o']
            
            # Check SL first (intraday low hits SL)
            if bar_l <= sl_price:
                exit_bar = bi
                exit_price = sl_price
                exit_reason = 'sl_hit'
                hold_bars = bi - entry_bar
                break
            
            # Check TP
            if bar_h >= tp_price:
                exit_bar = bi
                exit_price = tp_price
                exit_reason = 'tp_hit'
                hold_bars = bi - entry_bar
                break
        
        if exit_reason == 'time_stop':
            hold_bars = max_hold - entry_bar
            exit_bar = max_hold
            exit_price = ohlcv[max_hold]['c']
        
        pnl_pct = (exit_price - entry_price) / entry_price * 100
        rr = abs(tp_price - entry_price) / max(abs(sl_price - entry_price), 0.001) if sl_price > 0 else 0
        
        trades.append({
            'pattern': sq['pattern'],
            'entry_signal': sq['zone_type'],
            'entry_bar': entry_bar,
            'entry_date': dates[entry_bar] if entry_bar < len(dates) else '?',
            'entry_price': round(entry_price, 2),
            'sl_price': round(sl_price, 2),
            'tp_price': round(tp_price, 2),
            'exit_bar': exit_bar,
            'exit_date': dates[exit_bar] if exit_bar < len(dates) else '?',
            'exit_price': round(exit_price, 2),
            'exit_reason': exit_reason,
            'pnl_pct': round(pnl_pct, 2),
            'hold_bars': hold_bars,
            'rr': round(rr, 1),
            'won': pnl_pct > 0,
        })
        
        used_bars.add(seq_bar)
    
    return trades


def _find_swings(ohlcv):
    """Simple swing detection for TP targeting"""
    n = len(ohlcv)
    swings = []
    lookback = 5
    for i in range(lookback, n - lookback):
        h = ohlcv[i]['h']
        l = ohlcv[i]['l']
        is_high = all(ohlcv[j]['h'] <= h for j in range(i - lookback, i + lookback + 1) if j != i)
        is_low = all(ohlcv[j]['l'] >= l for j in range(i - lookback, i + lookback + 1) if j != i)
        if is_high: swings.append({'bar': i, 'price': h, 'type': 'H'})
        if is_low: swings.append({'bar': i, 'price': l, 'type': 'L'})
    return sorted(swings, key=lambda x: x['bar'])


# ═══ MAIN ═══
daily_files = sorted(KLINE.glob('*_daily_300.json'))
t0 = time.time()

all_trades = []
stock_summaries = {}

for fi, df in enumerate(daily_files):
    name = df.stem.replace('_daily_300', '')
    parts = name.rsplit('_', 1)
    sym = f'{parts[0]}.{parts[1]}' if len(parts) == 2 else name
    try:
        daily = json.loads(df.read_bytes())
        if len(daily) < 50: continue
    except: continue
    
    dates = [fmt_date(str(b.get('date', b.get('t', ''))))[:10] for b in daily]
    
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
    
    n = len(daily)
    windows = {'full': 0, 'mid': max(0, n - 150), 'recent': max(0, n - 50)}
    
    for wn, start in windows.items():
        trades = backtest_with_exit_detail(daily, dates, seqs, start)
        for t in trades:
            t['symbol'] = sym
            t['window'] = wn
            t['w_trend'] = w_trend
            all_trades.append(t)
    
    if (fi + 1) % 500 == 0:
        print(f"  [{fi+1}/{len(daily_files)}] {time.time()-t0:.0f}s trades={len(all_trades)}")

elapsed = time.time() - t0

# ═══ REPORT ═══
print(f"\n{'='*70}")
print(f"  完整逐笔交易回测 V6.0 ({elapsed:.0f}s)")
print(f"  扫描: {len(daily_files)} → {len(all_trades)}笔交易")

# By window
for wn in ['full', 'mid', 'recent']:
    wt = [t for t in all_trades if t['window'] == wn]
    if not wt: continue
    wins = sum(1 for t in wt if t['won'])
    avg_pnl = sum(t['pnl_pct'] for t in wt) / len(wt)
    avg_hold = sum(t['hold_bars'] for t in wt) / len(wt)
    tp_hits = sum(1 for t in wt if t['exit_reason'] == 'tp_hit')
    sl_hits = sum(1 for t in wt if t['exit_reason'] == 'sl_hit')
    ts = sum(1 for t in wt if t['exit_reason'] == 'time_stop')
    
    print(f"\n  {wn}: WR={wins/len(wt)*100:.1f}% N={len(wt)} PnL={avg_pnl:+.2f}% Hold={avg_hold:.1f}bar")
    print(f"    TP={tp_hits}({tp_hits/len(wt)*100:.0f}%) SL={sl_hits}({sl_hits/len(wt)*100:.0f}%) TimeStop={ts}({ts/len(wt)*100:.0f}%)")
    
    for pat in ['L→D', 'S→D']:
        pt = [t for t in wt if t['pattern'] == pat]
        if pt:
            pw = sum(1 for t in pt if t['won'])
            print(f"    {pat}: WR={pw/len(pt)*100:.1f}% N={len(pt)}")

# By exit reason
print(f"\n  退出原因分布:")
for reason in ['tp_hit', 'sl_hit', 'time_stop']:
    rt = [t for t in all_trades if t['exit_reason'] == reason]
    if rt:
        rw = sum(1 for t in rt if t['won'])
        avg_r = sum(t['pnl_pct'] for t in rt) / len(rt)
        print(f"    {reason}: N={len(rt)} WR={rw/len(rt)*100:.1f}% AvgPnL={avg_r:+.2f}%")

# ═══ SAVE ═══
# Group trades by symbol
by_symbol = defaultdict(list)
for t in all_trades:
    by_symbol[t['symbol']].append(t)

stock_list = {}
for sym, trades in by_symbol.items():
    full_t = [t for t in trades if t['window'] == 'full']
    wins = sum(1 for t in full_t if t['won'])
    total = len(full_t)
    stock_list[sym] = {
        'total_trades': total,
        'wr': round(wins / total, 3) if total else 0,
        'avg_pnl': round(sum(t['pnl_pct'] for t in full_t) / total, 2) if total else 0,
        'trades': sorted(full_t, key=lambda x: x['entry_bar']),
    }

output = {
    'meta': {'version': '6.0', 'method': 'close_entry_sequence', 'date': time.strftime('%Y-%m-%d'),
             'total_trades': len(all_trades), 'stocks_with_trades': len(stock_list)},
    'all_trades': sorted(all_trades, key=lambda x: (x['symbol'], x['window'], x['entry_bar'])),
    'stocks': stock_list,
    'summary': {
        'full': {'total': len([t for t in all_trades if t['window']=='full']),
                 'wr': round(sum(1 for t in all_trades if t['window']=='full' and t['won'])/max(len([t for t in all_trades if t['window']=='full']),1), 3)},
    }
}
json.dump(output, open(OUT / 'detailed_trades_v60.json', 'w'), ensure_ascii=False)
print(f"\n  Saved: {OUT/'detailed_trades_v60.json'} ({len(all_trades)} trades, {len(stock_list)} stocks)")
