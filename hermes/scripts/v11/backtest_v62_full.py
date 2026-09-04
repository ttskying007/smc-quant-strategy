#!/usr/bin/env python3
"""
V6.2 全量回测 — 生成detailed_trades文件用于图表同步
retrace entry for OB/Pinbar, immediate for FVG
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20, Signal
from v11.v19_backtest_engine import find_tps, find_sls

KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v21')
TP_CAP = 1.05; MAX_WAIT = 10

def detect_pinbars(daily):
    pinbars = []
    for i in range(20, len(daily)):
        b = daily[i]; o, h, l, c = b['o'], b['h'], b['l'], b['c']
        if c <= o or h == l: continue
        body = c - o; range_hl = h - l
        if range_hl == 0: continue
        lower_wick = o - l; upper_wick = h - c
        if lower_wick > body * 2 and lower_wick > range_hl * 0.5:
            if upper_wick < range_hl * 0.2:
                pinbars.append(Signal('Pinbar_Bull', i, 'bull', lower=l, upper=c, price=c))
    return pinbars

def summary(trades):
    if not trades: return {}
    n=len(trades); wins=sum(1 for t in trades if t['pnl_pct']>0)
    avg=sum(t['pnl_pct'] for t in trades)/n
    return {'total_trades':n,'wr':round(wins/n,2),'avg_pnl':round(avg,2)}

t0 = time.time()
files = sorted(KLINE.glob('*_daily_300.json'))
all_trades = []
stocks_out = {}
processed = 0

for fpath in files:
    sym = fpath.stem.replace('_daily_300', '').replace('_SH','.SH').replace('_SZ','.SZ').replace('_BJ','.BJ')
    try:
        daily = json.loads(fpath.read_bytes())
        if len(daily) < 50: continue
    except: continue
    
    sigs, st, _, swings_dict = detect_all_signals_v20(daily)
    pinbars = detect_pinbars(daily)
    all_sigs = list(sigs) + pinbars
    n = len(daily)
    
    sbb = defaultdict(list)
    for s in all_sigs: sbb[s.idx].append(s)
    
    trades = []
    used_bars = set()
    
    for i in sorted(sbb.keys()):
        types_i = [s.type for s in sbb[i]]
        
        # OB_Bull: retrace entry
        if 'OB_Bull' in types_i:
            ob = next(s for s in sbb[i] if s.type == 'OB_Bull')
            entry_bar = i + 1
            if entry_bar >= n - 2 or entry_bar in used_bars: continue
            
            zone_low = ob.lower if hasattr(ob,'lower') and ob.lower > 0 else ob.price * 0.99
            ep_immediate = daily[entry_bar]['o']
            
            # Calculate TP (same absolute level), SL (tight below zone for retrace)
            tp, _, _ = find_tps(ep_immediate, sigs, swings_dict, daily)
            sl_imm, _, _ = find_sls(ep_immediate, sigs, swings_dict, daily)
            if tp is None: tp = ep_immediate * TP_CAP
            if tp > ep_immediate * TP_CAP: tp = ep_immediate * TP_CAP
            
            # Check RR for immediate entry (to confirm signal quality)
            tpd_i = abs(tp-ep_immediate)/ep_immediate*100
            sld_i = abs((sl_imm or ep_immediate*0.97)-ep_immediate)/ep_immediate*100
            if sld_i == 0 or tpd_i/sld_i < 1.0: continue
            
            # Find retrace
            retrace_bar = -1
            for k in range(entry_bar, min(entry_bar+MAX_WAIT, n)):
                if daily[k]['l'] <= zone_low:
                    retrace_bar = k; break
            
            if retrace_bar < 0: continue  # No retrace
            
            # Enter at zone_low
            ep = zone_low
            sl = ep * 0.97  # Tight stop below zone
            actual_entry_bar = retrace_bar
            
            # Execute trade
            exit_idx = -1; exit_price = 0; exit_method = 'eod'
            for k in range(actual_entry_bar+1, n):
                bk = daily[k]
                if bk['h'] >= tp: exit_idx=k; exit_price=tp; exit_method='tp_hit'; break
                if bk['l'] <= sl: exit_idx=k; exit_price=sl; exit_method='sl_hit'; break
            if exit_idx < 0: exit_idx=n-1; exit_price=daily[exit_idx]['c']
            if exit_idx <= actual_entry_bar: continue
            
            pnl = (exit_price - ep) / ep * 100
            won = pnl > 0
            trades.append({
                'entry_bar': actual_entry_bar, 'exit_bar': exit_idx,
                'entry_price': round(ep,2), 'exit_price': round(exit_price,2),
                'entry_date': str(daily[actual_entry_bar].get('t',''))[:8],
                'exit_date': str(daily[exit_idx].get('t',''))[:8],
                'pnl_pct': round(pnl,2), 'won': won,
                'entry_signal': 'OB_Bull', 'pattern': 'OB_retrace',
                'sl_price': round(sl,2), 'tp_price': round(tp,2),
                'exit_reason': exit_method, 'hold_bars': exit_idx - actual_entry_bar,
                'entry_mode': 'retrace', 'zone_low': round(zone_low,2),
            })
            used_bars.add(actual_entry_bar)
        
        # FVG_Bull: immediate entry (retrace harms FVG)
        if 'FVG_Bull' in types_i and 'OB_Bull' not in types_i:
            fvg = next(s for s in sbb[i] if s.type == 'FVG_Bull')
            entry_bar = i + 1
            if entry_bar >= n - 2 or entry_bar in used_bars: continue
            
            ep = daily[entry_bar]['o']
            if ep == 0: continue
            
            tp, _, _ = find_tps(ep, sigs, swings_dict, daily)
            sl, _, _ = find_sls(ep, sigs, swings_dict, daily)
            if tp is None: tp = ep * TP_CAP
            if tp > ep * TP_CAP: tp = ep * TP_CAP
            if sl is None: sl = ep * 0.97
            
            tpd = abs(tp-ep)/ep*100; sld = abs(sl-ep)/ep*100
            if sld == 0 or tpd/sld < 1.0: continue
            
            exit_idx=-1; exit_price=0; exit_method='eod'
            for k in range(entry_bar+1, n):
                bk = daily[k]
                if bk['h'] >= tp: exit_idx=k; exit_price=tp; exit_method='tp_hit'; break
                if bk['l'] <= sl: exit_idx=k; exit_price=sl; exit_method='sl_hit'; break
            if exit_idx<0: exit_idx=n-1; exit_price=daily[exit_idx]['c']
            if exit_idx<=entry_bar: continue
            
            pnl=(exit_price-ep)/ep*100; won=pnl>0
            trades.append({
                'entry_bar': entry_bar, 'exit_bar': exit_idx,
                'entry_price': round(ep,2), 'exit_price': round(exit_price,2),
                'entry_date': str(daily[entry_bar].get('t',''))[:8],
                'exit_date': str(daily[exit_idx].get('t',''))[:8],
                'pnl_pct': round(pnl,2), 'won': won,
                'entry_signal': 'FVG_Bull', 'pattern': 'FVG_immediate',
                'sl_price': round(sl,2), 'tp_price': round(tp,2),
                'exit_reason': exit_method, 'hold_bars': exit_idx-entry_bar,
                'entry_mode': 'immediate',
            })
            used_bars.add(entry_bar)
    
    if trades:
        stocks_out[sym] = {**summary(trades), 'trades': trades}
        all_trades.extend(trades)
    
    processed += 1
    if processed % 1000 == 0:
        print(f"  [{processed}] {time.time()-t0:.0f}s total_trades={len(all_trades)}")

elapsed = time.time()-t0
all_sum = summary(all_trades)

print(f"\n{'='*80}")
print(f"  V6.2 Retrace Backtest — {processed} stocks, {len(all_trades)} trades — {elapsed:.0f}s")
print(f"  WR={all_sum.get('wr',0)*100:.1f}% avgPnL={all_sum.get('avg_pnl',0):+.2f}%")
print(f"{'='*80}")

output = {
    'meta': {'version':'V6.2 retrace','date':time.strftime('%Y-%m-%d'),'stocks':len(stocks_out),
             'total_trades':len(all_trades),'elapsed':round(elapsed)},
    'all_trades': all_trades,
    'stocks': stocks_out,
    'summary': all_sum,
}
json.dump(output, open(OUT/'detailed_trades_v62.json','w'), ensure_ascii=False)
print(f"\n  保存: {OUT/'detailed_trades_v62.json'} ({len(all_trades)} trades)")
