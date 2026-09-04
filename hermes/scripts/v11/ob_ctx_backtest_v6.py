#!/usr/bin/env python3
"""
V6 OB上下文矩阵回测 — 每个OB_Bull按ctx类型分组回测
验证: 有前序信号的OB是否优于独立OB
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

# ═══ Time ranges ═══
TIMERANGES = {
    '2024-H1': ('20240101','20240630'),
    '2024-H2': ('20240701','20241231'),
    '2025-H1': ('20250101','20250630'),
    '2025-H2': ('20250701','20251231'),
    '2026':     ('20260101','99999999'),
    'All':      ('00000000','99999999'),
}

# ═══ MAIN ═══
t0 = time.time()
files = sorted(KLINE.glob('*_daily_300.json'))

# ctx_key -> {timerange: [trades]}
ctx_results = defaultdict(lambda: defaultdict(list))
ctx_labels = {}  # ctx_key -> human label

processed = 0; total_ob = 0
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
    w_trend = weekly_trend(weekly)
    if w_trend != 'bullish': continue
    
    sigs, st, _, swings_dict = detect_all_signals_v20(daily)
    pinbars = detect_pinbars(daily)
    all_sigs = list(sigs) + pinbars
    n = len(daily)
    
    sbb = defaultdict(list)
    for s in all_sigs: sbb[s.idx].append(s)
    
    for i in sorted(sbb.keys()):
        types_i = [s.type for s in sbb[i]]
        if 'OB_Bull' not in types_i: continue
        
        entry_bar = i + 1
        if entry_bar >= n - 2: continue
        ep = daily[entry_bar]['o']
        if ep == 0: continue
        
        total_ob += 1
        
        # Context
        ctx_signals = []
        for prev in range(max(0, i-10), i):
            if prev in sbb:
                for s in sbb[prev]:
                    if s.type in ALL_START:
                        ctx_signals.append({'type': s.type, 'gap': i-prev})
        
        # Build ctx keys
        ctx_types = sorted(set(c['type'] for c in ctx_signals))
        ctx_count = len(ctx_signals)
        
        # Primary ctx key: first context type, or 'alone'
        if ctx_count == 0:
            ctx_key = 'alone'
        elif ctx_count == 1:
            ctx_key = ctx_types[0]
        else:
            ctx_key = '+'.join(ctx_types)
        
        # Also track by ctx_count
        tp, _, _ = find_tps(ep, sigs, swings_dict, daily)
        sl, _, _ = find_sls(ep, sigs, swings_dict, daily)
        if tp is None: tp = ep * TP_CAP
        if tp > ep * TP_CAP: tp = ep * TP_CAP
        if sl is None: sl = ep * 0.97
        
        tpd = abs(tp-ep)/ep*100; sld = abs(sl-ep)/ep*100
        if sld == 0 or tpd/sld < 1.0: continue
        
        # Execute trade
        exit_idx=-1; exit_price=0; exit_method='eod'
        for k in range(entry_bar+1, n):
            bk = daily[k]
            if bk['h'] >= tp: exit_idx=k; exit_price=tp; exit_method='tp'; break
            if bk['l'] <= sl: exit_idx=k; exit_price=sl; exit_method='sl'; break
        if exit_idx<0: exit_idx=n-1; exit_price=daily[exit_idx]['c']
        if exit_idx<=entry_bar: continue
        
        pnl=(exit_price-ep)/ep*100
        entry_date = str(daily[entry_bar].get('t',''))[:8]
        
        trade = {'pnl':pnl,'exit':exit_method,'date':entry_date,'hold':exit_idx-entry_bar,
                 'ctx_key':ctx_key, 'ctx_count':ctx_count, 'gap':ctx_signals[0]['gap'] if ctx_signals else 0}
        
        for tr_name, (d0, d1) in TIMERANGES.items():
            if d0 <= entry_date <= d1:
                ctx_results[ctx_key][tr_name].append(trade)
                # Also by count
                ctx_results[f'count={ctx_count}'][tr_name].append(trade)
    
    processed += 1
    if processed % 1000 == 0:
        print(f"  [{processed} stocks] {time.time()-t0:.0f}s total_ob={total_ob}")

elapsed = time.time()-t0
print(f"\n{'='*100}")
print(f"  V6 OB上下文矩阵回测 — {processed} stocks, {total_ob} OB — {elapsed:.0f}s")
print(f"{'='*100}")

# ═══ REPORT ═══
# By ctx type, show All range
print(f"\n  OB上下文 vs WR/PnL (All range):")
print(f"  {'Context':<30s} {'Trades':>6s} {'WR':>6s} {'AvgPnL':>7s} {'CumPnL':>8s} {'PF':>6s} {'TP%':>5s}")
print(f"  {'-'*75}")

# Sort by trade count
ctx_order = ['alone', 'Sweep_SSL', 'BOS_Bull', 'MSS_Bull', 'CHOCH_Bull', 'EQL']
multi_ctx = sorted([k for k in ctx_results.keys() if '+' in k and not k.startswith('count')],
                   key=lambda k: -len(ctx_results[k].get('All',[])))

for key in ctx_order + multi_ctx:
    if key not in ctx_results: continue
    s = summary(ctx_results[key].get('All', []))
    if s['n'] < 5: continue
    label = f"{key}" if '+' not in key else f"  {key}"
    print(f"  {label:<30s} {s['n']:>6d} {s['wr']:>5.1f}% {s['avg']:>+6.2f}% {s['cum']:>+7.1f}% {s['pf']:>5.1f} {s['tp%']:>4.1f}%")

# By ctx_count
print(f"\n  OB by ctx_count:")
for c in ['count=0','count=1','count=2','count=3','count=4','count=5']:
    s = summary(ctx_results[c].get('All', []))
    if s['n'] == 0: continue
    print(f"  {c:20s} {s['n']:>6d} {s['wr']:>5.1f}% {s['avg']:>+6.2f}% {s['cum']:>+7.1f}% {s['pf']:>5.1f}")

# By timerange per main ctx types
print(f"\n{'='*100}")
print(f"  OB上下文 × 时间范围")
print(f"{'='*100}")
print(f"  {'Context':<20s} {'Range':<12s} {'Trades':>6s} {'WR':>6s} {'AvgPnL':>7s}")
print(f"  {'-'*65}")
for key in ['alone','Sweep_SSL','BOS_Bull','MSS_Bull','CHOCH_Bull','EQL']:
    for tr in ['2024-H1','2024-H2','2025-H1','2025-H2','2026']:
        s = summary(ctx_results[key].get(tr, []))
        if s['n'] < 3: continue
        print(f"  {key:<20s} {tr:<12s} {s['n']:>6d} {s['wr']:>5.1f}% {s['avg']:>+6.2f}%")

# Save
output = {
    'meta': {'version':'V6 ctx-backtest', 'date':time.strftime('%Y-%m-%d'), 'stocks':processed,
             'total_ob':total_ob, 'elapsed':round(elapsed)},
    'by_ctx': {k: {tr: summary(v[tr]) for tr in v} for k,v in ctx_results.items()},
}
json.dump(output, open(OUT/'ob_ctx_backtest_v6.json','w'), ensure_ascii=False, indent=2)
print(f"\n  保存: {OUT/'ob_ctx_backtest_v6.json'}")
