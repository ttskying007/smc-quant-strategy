#!/usr/bin/env python3
"""
V6 L2全组合回测 — 每类START→ZONE按时间窗口回测
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20, Signal
from v11.v19_backtest_engine import find_tps, find_sls

KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v21')
TP_CAP = 1.05

ALL_START = ['Sweep_SSL', 'EQL', 'CHOCH_Bull', 'BOS_Bull', 'MSS_Bull']
ZONE_TYPES = ['OB_Bull', 'FVG_Bull', 'Pinbar_Bull']

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

def weekly_trend(weekly):
    if len(weekly) < 20: return 'neutral'
    sigs, st, _, _ = detect_all_signals_v20(weekly)
    tc = st['type_counts']
    cb = tc.get('CHOCH_Bull',0); cbr = tc.get('CHOCH_Bear',0)
    bb = tc.get('BOS_Bull',0); bbr = tc.get('BOS_Bear',0)
    last_ch = [s for s in sigs if 'CHOCH' in s.type]
    ld = 'bull' if last_ch and 'Bull' in last_ch[-1].type else ('bear' if last_ch and 'Bear' in last_ch[-1].type else None)
    if ld == 'bull' and cb+bb >= cbr+bbr: return 'bullish'
    if ld == 'bear' and cbr+bbr > cb+bb: return 'bearish'
    if cb+bb > (cbr+bbr)*1.5: return 'bullish'
    if cbr+bbr > (cb+bb)*1.5: return 'bearish'
    return 'neutral'

def daily_to_weekly(daily):
    w = []
    for i in range(0, len(daily), 5):
        chunk = daily[i:i+5]
        if len(chunk) >= 3:
            w.append({'o':chunk[0]['o'],'h':max(b['h'] for b in chunk),
                      'l':min(b['l'] for b in chunk),'c':chunk[-1]['c']})
    return w

def summary(trades):
    if not trades: return {'n':0,'wr':0,'avg':0,'cum':0,'pf':0,'tp%':0,'sl%':0}
    n=len(trades); wins=sum(1 for t in trades if t['pnl']>0)
    avg=sum(t['pnl'] for t in trades)/n
    cum=sum(t['pnl'] for t in trades)
    wp=[t['pnl'] for t in trades if t['pnl']>0]
    lp=[abs(t['pnl']) for t in trades if t['pnl']<=0]
    pf=sum(wp)/sum(lp) if lp else 999
    tp=sum(1 for t in trades if t['exit']=='tp')/n*100
    sl=sum(1 for t in trades if t['exit']=='sl')/n*100
    return {'n':n,'wr':round(wins/n*100,1),'avg':round(avg,2),'cum':round(cum,1),'pf':round(pf,1),'tp%':round(tp,1),'sl%':round(sl,1)}

# Gap windows to test
GAP_WINDOWS = [('gap1-3',1,3),('gap1-5',1,5),('gap1-10',1,10),('gap4-10',4,10),('gap1-15',1,15)]

TIMERANGES = {
    '2024-H1': ('20240101','20240630'),
    '2024-H2': ('20240701','20241231'),
    '2025-H1': ('20250101','20250630'),
    '2025-H2': ('20250701','20251231'),
    '2026':     ('20260101','99999999'),
    'All':      ('00000000','99999999'),
}

t0 = time.time()
files = sorted(KLINE.glob('*_daily_300.json'))

# combo_key → gap_window → timerange → [trades]
combo_gap_results = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

processed = 0
for f in files:
    sym = f.stem.replace('_daily_300', '')
    try:
        daily = json.loads(f.read_bytes())
        if len(daily) < 50: continue
    except: continue
    
    weekly_path = KLINE / f'{sym}_weekly_200.json'
    weekly = None
    if weekly_path.exists():
        try: weekly = json.loads(weekly_path.read_bytes())
        except: pass
    if weekly is None or len(weekly) < 20:
        weekly = daily_to_weekly(daily)
    if weekly_trend(weekly) != 'bullish': continue
    
    sigs, st, _, swings_dict = detect_all_signals_v20(daily)
    pinbars = detect_pinbars(daily)
    all_sigs = list(sigs) + pinbars
    n = len(daily)
    
    sbb = defaultdict(list)
    for s in all_sigs: sbb[s.idx].append(s)
    
    for i in sorted(sbb.keys()):
        start_sigs = [s for s in sbb[i] if s.type in ALL_START]
        if not start_sigs: continue
        
        for start_s in start_sigs:
            # Find best zone within max gap
            best_zone = None; best_score = -999
            for j in range(i+1, min(i+15+1, n)):
                if j not in sbb: continue
                zone_cands = [s for s in sbb[j] if s.type in ZONE_TYPES]
                if not zone_cands: continue
                for z in zone_cands:
                    gap = j - i
                    z_score = (gap * -1.5) + (3 if z.type=='OB_Bull' else (2 if z.type=='Pinbar_Bull' else 1))
                    if z_score > best_score:
                        best_score = z_score; best_zone = (z, j, gap)
            
            if not best_zone: continue
            zone, j, gap = best_zone
            entry_bar = j + 1
            if entry_bar >= n - 2: continue
            ep = daily[entry_bar]['o']
            if ep == 0: continue
            
            # OB_Bull handled by L1, skip as L2 for this analysis
            if zone.type == 'OB_Bull': continue
            
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
                if bk['h'] >= tp: exit_idx=k; exit_price=tp; exit_method='tp'; break
                if bk['l'] <= sl: exit_idx=k; exit_price=sl; exit_method='sl'; break
            if exit_idx<0: exit_idx=n-1; exit_price=daily[exit_idx]['c']
            if exit_idx<=entry_bar: continue
            
            pnl=(exit_price-ep)/ep*100
            entry_date = str(daily[entry_bar].get('t',''))[:8]
            combo_key = f'{start_s.type}→{zone.type}'
            
            trade = {'pnl':pnl,'exit':exit_method,'date':entry_date,'gap':gap}
            
            # Store by gap window
            for gw_name, gmin, gmax in GAP_WINDOWS:
                if gmin <= gap <= gmax:
                    for tr_name, (d0, d1) in TIMERANGES.items():
                        if d0 <= entry_date <= d1:
                            combo_gap_results[combo_key][gw_name][tr_name].append(trade)
    
    processed += 1
    if processed % 1500 == 0:
        print(f"  [{processed}] {time.time()-t0:.0f}s")

elapsed = time.time()-t0
print(f"\n{'='*100}")
print(f"  V6 L2 全组合 × Gap窗口 × 时间范围回测 — {processed} stocks — {elapsed:.0f}s")
print(f"{'='*100}")

# Best gap window per combo (using All timerange)
print(f"\n  Per-combo optimal gap window:")
print(f"  {'Combo':<32s} {'BestGap':>10s} {'Trades':>6s} {'WR':>6s} {'Avg':>7s} {'Cum':>8s}")
print(f"  {'-'*75}")
for combo_key in sorted(combo_gap_results.keys()):
    best_gw = None; best_wr = 0
    for gw_name, gmin, gmax in GAP_WINDOWS:
        st = summary(combo_gap_results[combo_key][gw_name]['All'])
        if st['n'] >= 5 and st['wr'] > best_wr:
            best_wr = st['wr']; best_gw = (gw_name, st)
    if best_gw:
        gw_name, st = best_gw
        print(f"  {combo_key:<32s} {gw_name:>10s} {st['n']:>6d} {st['wr']:>5.1f}% {st['avg']:>+6.2f}% {st['cum']:>+7.1f}%")

# Full matrix: per combo, All gap=1-10, by timerange
print(f"\n{'='*100}")
print(f"  Combo × TimeRange (gap 1-10)")
print(f"{'='*100}")
print(f"  {'Combo':<32s} {'Range':<10s} {'Trades':>6s} {'WR':>6s} {'Avg':>7s} {'Cum':>8s}")
print(f"  {'-'*80}")
for combo_key in sorted(combo_gap_results.keys()):
    for tr in ['2025-H1','2025-H2','2026']:
        st = summary(combo_gap_results[combo_key]['(1,10)'][tr])
        if st['n'] < 3: continue
        print(f"  {combo_key:<32s} {tr:<10s} {st['n']:>6d} {st['wr']:>5.1f}% {st['avg']:>+6.2f}% {st['cum']:>+7.1f}%")

# Save
output = {
    'meta': {'version':'V6 L2-backtest', 'date':time.strftime('%Y-%m-%d'), 'stocks':processed, 'elapsed':round(elapsed)},
    'by_combo': {ck: {gw: {tr: summary(v[tr]) for tr in v} for gw,v in gwd.items()} 
                 for ck, gwd in combo_gap_results.items()},
}
json.dump(output, open(OUT/'l2_combo_backtest_v6.json','w'), ensure_ascii=False, indent=2)
print(f"\n  保存: {OUT/'l2_combo_backtest_v6.json'}")
