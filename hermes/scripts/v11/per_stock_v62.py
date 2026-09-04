#!/usr/bin/env python3
"""
V6.2 Per-Stock分析 — 找出最优参数下每只股票的WR/PnL
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20, Signal
from v11.v19_backtest_engine import find_tps, find_sls

KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v21')
TP_CAP = 1.05; MW = 7; SL_MUL = 0.96

def detect_pinbars(daily):
    pinbars = []
    for i in range(20, len(daily)):
        b = daily[i]; o,h,l,c = b['o'],b['h'],b['l'],b['c']
        if c<=o or h==l: continue
        body=c-o; range_hl=h-l
        if range_hl==0: continue
        lw=o-l; uw=h-c
        if lw>body*2 and lw>range_hl*0.5 and uw<range_hl*0.2:
            pinbars.append(Signal('Pinbar_Bull',i,'bull',lower=l,upper=c,price=c))
    return pinbars

t0 = time.time()
files = sorted(KLINE.glob('*_daily_300.json'))
stock_results = {}  # sym -> {trades, wr, avg_pnl}
processed = 0

for fpath in files:
    sym = fpath.stem.replace('_daily_300', '')
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
    
    trades = []; used = set()
    
    for i in sorted(sbb.keys()):
        types_i = [s.type for s in sbb[i]]
        
        # OB_Bull + Pinbar_Bull: retrace entry
        for sname in ['OB_Bull', 'Pinbar_Bull']:
            if sname not in types_i: continue
            sig = next(s for s in sbb[i] if s.type == sname)
            entry_bar = i + 1
            if entry_bar >= n-2 or entry_bar in used: continue
            
            zone_low = sig.lower if hasattr(sig,'lower') and sig.lower>0 else sig.price*0.99
            ep_open = daily[entry_bar]['o']
            
            tp, _, _ = find_tps(ep_open, sigs, swings_dict, daily)
            if tp is None: tp = ep_open * TP_CAP
            if tp > ep_open * TP_CAP: tp = ep_open * TP_CAP
            
            tpd = abs(tp-ep_open)/ep_open*100
            sld_i = abs(ep_open*0.97-ep_open)/ep_open*100
            if sld_i==0 or tpd/sld_i < 1.0: continue
            
            retrace_bar = -1
            for k in range(entry_bar, min(entry_bar+MW, n)):
                if daily[k]['l'] <= zone_low:
                    retrace_bar = k; break
            if retrace_bar < 0: continue
            
            ep = zone_low; sl = ep * SL_MUL
            ei=-1; ex=0; em='eod'
            for k in range(retrace_bar+1, n):
                bk=daily[k]
                if bk['h']>=tp: ei=k; ex=tp; em='tp'; break
                if bk['l']<=sl: ei=k; ex=sl; em='sl'; break
            if ei<0: ei=n-1; ex=daily[ei]['c']
            if ei>retrace_bar:
                trades.append((ex-ep)/ep*100)
                used.add(retrace_bar)
        
        # FVG_Bull: immediate entry
        if 'FVG_Bull' in types_i and 'OB_Bull' not in types_i:
            entry_bar = i+1
            if entry_bar>=n-2 or entry_bar in used: continue
            ep = daily[entry_bar]['o']
            if ep==0: continue
            
            tp, _, _ = find_tps(ep, sigs, swings_dict, daily)
            sl, _, _ = find_sls(ep, sigs, swings_dict, daily)
            if tp is None: tp = ep*TP_CAP
            if tp > ep*TP_CAP: tp = ep*TP_CAP
            if sl is None: sl = ep*0.97
            
            tpd=abs(tp-ep)/ep*100; sld=abs(sl-ep)/ep*100
            if sld==0 or tpd/sld<1.0: continue
            
            ei=-1; ex=0; em='eod'
            for k in range(entry_bar+1, n):
                bk=daily[k]
                if bk['h']>=tp: ei=k; ex=tp; em='tp'; break
                if bk['l']<=sl: ei=k; ex=sl; em='sl'; break
            if ei<0: ei=n-1; ex=daily[ei]['c']
            if ei>entry_bar:
                trades.append((ex-ep)/ep*100)
                used.add(entry_bar)
    
    if trades:
        wins = sum(1 for p in trades if p>0)
        avg = sum(trades)/len(trades)
        cum = sum(trades)
        stock_results[sym] = {
            'trades': len(trades), 'wr': round(wins/len(trades)*100,1),
            'avg_pnl': round(avg,2), 'cum_pnl': round(cum,1),
            'pnls': trades,
        }
    
    processed += 1
    if processed % 1000 == 0:
        print(f"  [{processed}] {time.time()-t0:.0f}s stocks_with_trades={len(stock_results)}")

elapsed = time.time()-t0
print(f"\n{'='*80}")
print(f"  V6.2 Per-Stock — {processed} stocks, {len(stock_results)} with trades — {elapsed:.0f}s")
print(f"{'='*80}")

# TOP 20 stocks by WR (min 5 trades)
qualified = {k:v for k,v in stock_results.items() if v['trades']>=5}
by_wr = sorted(qualified.items(), key=lambda x: -x[1]['wr'])
by_avg = sorted(qualified.items(), key=lambda x: -x[1]['avg_pnl'])
by_cum = sorted(qualified.items(), key=lambda x: -x[1]['cum_pnl'])

print(f"\n  TOP 20 by WR (≥5 trades, {len(qualified)} stocks):")
print(f"  {'Stock':<14s} {'Trades':>6s} {'WR':>6s} {'Avg':>7s} {'Cum':>8s}")
print(f"  {'-'*50}")
for sym, v in by_wr[:20]:
    print(f"  {sym:<14s} {v['trades']:>6d} {v['wr']:>5.1f}% {v['avg_pnl']:>+6.2f}% {v['cum_pnl']:>+7.1f}%")

print(f"\n  TOP 20 by Cum PnL (≥5 trades):")
for sym, v in by_cum[:20]:
    print(f"  {sym:<14s} {v['trades']:>6d} {v['wr']:>5.1f}% {v['avg_pnl']:>+6.2f}% {v['cum_pnl']:>+7.1f}%")

# WORST stocks
print(f"\n  WORST 10 by WR (≥5 trades):")
for sym, v in by_wr[-10:]:
    print(f"  {sym:<14s} {v['trades']:>6d} {v['wr']:>5.1f}% {v['avg_pnl']:>+6.2f}% {v['cum_pnl']:>+7.1f}%")

# Summary stats
all_wr = [v['wr'] for v in qualified.values()]
all_avg = [v['avg_pnl'] for v in qualified.values()]
print(f"\n  Distribution ({len(qualified)} stocks ≥5 trades):")
print(f"    WR:  min={min(all_wr):.0f}% median={sorted(all_wr)[len(all_wr)//2]:.0f}% max={max(all_wr):.0f}%")
print(f"    Avg: min={min(all_avg):+.1f}% median={sorted(all_avg)[len(all_avg)//2]:+.1f}% max={max(all_avg):+.1f}%")

# Stocks with WR=100%
w100 = [(k,v) for k,v in qualified.items() if v['wr']==100.0]
print(f"\n  WR=100% stocks: {len(w100)}")
for sym, v in w100[:10]:
    print(f"    {sym}: {v['trades']} trades avg={v['avg_pnl']:+.2f}%")

# Save
output = {
    'meta': {'version':'V6.2 per-stock','date':time.strftime('%Y-%m-%d'),'stocks':len(stock_results),
             'qualified_5trades':len(qualified),'elapsed':round(elapsed)},
    'top_wr': [(sym, v) for sym,v in by_wr[:50]],
    'top_cum': [(sym, v) for sym,v in by_cum[:50]],
    'worst_wr': [(sym, v) for sym,v in by_wr[-20:]],
    'all': {sym: {'trades':v['trades'],'wr':v['wr'],'avg_pnl':v['avg_pnl'],'cum_pnl':v['cum_pnl']} 
            for sym,v in stock_results.items()},
}
json.dump(output, open(OUT/'per_stock_v62.json','w'), ensure_ascii=False, indent=2)
print(f"\n  保存: {OUT/'per_stock_v62.json'}")
