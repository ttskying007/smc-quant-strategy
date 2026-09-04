#!/usr/bin/env python3
"""
V6.2 回调入场回测 — 对比"开盘买入" vs "回调到zone买入"
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20
from v11.v19_backtest_engine import find_tps, find_sls

KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v21')
TP_CAP = 1.05
MAX_WAIT = 10  # Max bars to wait for retrace

def summary(trades):
    if not trades: return {'n':0,'wr':0,'avg':0,'cum':0,'tp%':0,'sl%':0,'hold':0}
    n=len(trades); wins=sum(1 for t in trades if t['pnl']>0)
    avg=sum(t['pnl'] for t in trades)/n; cum=sum(t['pnl'] for t in trades)
    tp=sum(1 for t in trades if t['exit']=='tp')/n*100
    sl=sum(1 for t in trades if t['exit']=='sl')/n*100
    hold=sum(t['hold'] for t in trades)/n
    return {'n':n,'wr':round(wins/n*100,1),'avg':round(avg,2),'cum':round(cum,1),'tp%':round(tp,1),'sl%':round(sl,1),'hold':round(hold,1)}

def execute_trade(daily, entry_bar, ep_in, tp, sl, sigs, swings_dict):
    """Execute from entry_bar to exit. Returns trade dict or None."""
    n = len(daily)
    if entry_bar >= n - 2: return None
    exit_idx = -1; exit_price = 0; exit_method = 'eod'
    for k in range(entry_bar+1, n):
        bk = daily[k]
        if bk['h'] >= tp: exit_idx=k; exit_price=tp; exit_method='tp'; break
        if bk['l'] <= sl: exit_idx=k; exit_price=sl; exit_method='sl'; break
    if exit_idx < 0: exit_idx = n-1; exit_price = daily[exit_idx]['c']
    if exit_idx <= entry_bar: return None
    pnl = (exit_price - ep_in) / ep_in * 100
    return {'pnl':pnl, 'exit':exit_method, 'hold':exit_idx-entry_bar}

def run_backtest(files, method='open'):
    """method: 'open' = buy next bar open; 'retrace' = wait for retrace to zone"""
    results = {'OB_Bull': [], 'FVG_Bull': [], 'Pinbar_Bull': []}
    stats = {'skipped_no_retrace': 0, 'entered_retrace': 0, 'entered_immediate': 0}
    processed = 0
    
    for fpath in files:
        sym = fpath.stem.replace('_daily_300', '')
        try:
            daily = json.loads(fpath.read_bytes())
            if len(daily) < 50: continue
        except: continue
        
        sigs, st, _, swings_dict = detect_all_signals_v20(daily)
        n = len(daily)
        used_bars = set()
        
        for s in sigs:
            if s.type not in ('OB_Bull', 'FVG_Bull'): continue
            i = s.idx
            entry_bar = i + 1
            if entry_bar >= n - 2: continue
            if entry_bar in used_bars: continue
            
            zone_low = s.lower if hasattr(s,'lower') and s.lower > 0 else s.price * 0.99
            
            tp, _, _ = find_tps(daily[entry_bar]['o'], sigs, swings_dict, daily)
            sl, _, _ = find_sls(daily[entry_bar]['o'], sigs, swings_dict, daily)
            if tp is None: tp = daily[entry_bar]['o'] * TP_CAP
            if tp > daily[entry_bar]['o'] * TP_CAP: tp = daily[entry_bar]['o'] * TP_CAP
            if sl is None: sl = daily[entry_bar]['o'] * 0.97
            
            tpd = abs(tp-daily[entry_bar]['o'])/daily[entry_bar]['o']*100
            sld = abs(sl-daily[entry_bar]['o'])/daily[entry_bar]['o']*100
            if sld == 0 or tpd/sld < 1.0: continue
            
            if method == 'open':
                # Current: buy at next bar open
                ep = daily[entry_bar]['o']
                trade = execute_trade(daily, entry_bar, ep, tp, sl, sigs, swings_dict)
                if trade:
                    trade['zone_type'] = s.type
                    results[s.type].append(trade)
                    used_bars.add(entry_bar)
            
            elif method == 'retrace':
                # New: wait for retrace to zone
                retrace_bar = -1
                for k in range(entry_bar, min(entry_bar+MAX_WAIT, n)):
                    if daily[k]['l'] <= zone_low:
                        retrace_bar = k
                        break
                
                if retrace_bar >= 0:
                    stats['entered_retrace'] += 1
                    ep = zone_low  # Enter at zone price
                    # TP: keep original (resistance above), SL: tight stop below zone
                    tp2 = tp  # Same absolute TP (resistance level unchanged)
                    sl2 = ep * 0.97  # Tight SL just below the zone
                    trade = execute_trade(daily, retrace_bar, ep, tp2, sl2, sigs, swings_dict)
                    if trade:
                        trade['zone_type'] = s.type
                        trade['wait_bars'] = retrace_bar - entry_bar + 1
                        results[s.type].append(trade)
                        used_bars.add(retrace_bar)
                else:
                    stats['skipped_no_retrace'] += 1
        
        processed += 1
        if processed % 500 == 0:
            print(f"  [{processed}] {time.time()-t0:.0f}s")
    
    return results, stats, processed

# ═══ MAIN ═══
t0 = time.time()
files = sorted(KLINE.glob('*_daily_300.json'))[:2000]  # 2000 stocks for comparison

print("═══ RUNNING: 开盘买入 ═══")
r_open, s_open, p_open = run_backtest(files, 'open')
print(f"  Done: {p_open} stocks, {time.time()-t0:.0f}s\n")

t1 = time.time()
print("═══ RUNNING: 回调买入 ═══")
r_retrace, s_retrace, p_retrace = run_backtest(files, 'retrace')
print(f"  Done: {p_retrace} stocks, {time.time()-t1:.0f}s\n")

# ═══ REPORT ═══
print("=" * 90)
print(f"  V6.2 回调入场 vs 开盘入场 — {p_open} stocks")
print("=" * 90)

print(f"\n  {'Signal':<15s} {'Method':<10s} {'Trades':>6s} {'WR':>6s} {'AvgPnL':>7s} {'CumPnL':>8s} {'TP%':>5s} {'SL%':>5s} {'Hold':>5s}")
print(f"  {'-'*75}")

for stype in ['OB_Bull', 'FVG_Bull']:
    so = summary(r_open[stype])
    sr = summary(r_retrace[stype])
    print(f"  {stype:<15s} {'open':<10s} {so['n']:>6d} {so['wr']:>5.1f}% {so['avg']:>+6.2f}% {so['cum']:>+7.1f}% {so['tp%']:>4.1f}% {so['sl%']:>4.1f}% {so['hold']:>4.1f}b")
    print(f"  {stype:<15s} {'retrace':<10s} {sr['n']:>6d} {sr['wr']:>5.1f}% {sr['avg']:>+6.2f}% {sr['cum']:>+7.1f}% {sr['tp%']:>4.1f}% {sr['sl%']:>4.1f}% {sr['hold']:>4.1f}b")
    delta_n = sr['n'] - so['n']; delta_wr = sr['wr'] - so['wr']
    delta_avg = sr['avg'] - so['avg']
    print(f"  {'':15s} {'Δ':<10s} {delta_n:>+6d} {delta_wr:>+5.1f}pp {delta_avg:>+6.2f}% {'':>8s}")
    print()

print(f"  回调统计:")
print(f"    等待到回调并入场: {s_retrace['entered_retrace']}")
print(f"    无回调跳过:       {s_retrace['skipped_no_retrace']}")
print(f"    跳过率:           {s_retrace['skipped_no_retrace']/(s_retrace['skipped_no_retrace']+s_retrace['entered_retrace'])*100:.0f}%")

# Wait bars distribution
wait_bars = [t.get('wait_bars',0) for trades in r_retrace.values() for t in trades if 'wait_bars' in t]
if wait_bars:
    wc = Counter(wait_bars)
    print(f"\n  等待bar数分布: {dict(sorted(wc.items()))}")

# Save
output = {
    'meta': {'version':'V6.2 retrace-test','date':time.strftime('%Y-%m-%d'),'stocks':p_open, 'max_wait':MAX_WAIT},
    'open': {st: summary(r_open[st]) for st in ['OB_Bull','FVG_Bull']},
    'retrace': {st: summary(r_retrace[st]) for st in ['OB_Bull','FVG_Bull']},
    'stats': s_retrace,
}
json.dump(output, open(OUT/'retrace_vs_open_v62.json','w'), ensure_ascii=False, indent=2)
print(f"\n  保存: {OUT/'retrace_vs_open_v62.json'}")
