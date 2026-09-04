#!/usr/bin/env python3
"""
V6.3 100次迭代引擎 — 多参数组合 × 全量股票对比
参数轴: MAX_WAIT(3/5/7/10/15) × SL_mul(0.96/0.97/0.98/0.99) × zone_type(lower/close/mid)
"""
import json, sys, time, itertools
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20, Signal
from v11.v19_backtest_engine import find_tps, find_sls

KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v21')
TP_CAP = 1.05

# Parameter grid
MAX_WAITS = [3, 5, 7, 10, 15]
SL_MULS = [0.96, 0.97, 0.98, 0.99]
ZONE_DEFS = ['lower', 'close']  # 'mid' = avg(lower, close)

# Generate all parameter combos
ALL_PARAMS = []
for mw in MAX_WAITS:
    for sm in SL_MULS:
        for zd in ZONE_DEFS:
            ALL_PARAMS.append({'max_wait': mw, 'sl_mul': sm, 'zone_def': zd})

print(f"Parameter combos: {len(ALL_PARAMS)}")

def get_zone_entry(ob, daily, i, zone_def):
    """Calculate zone entry price based on definition"""
    lower = ob.lower if hasattr(ob,'lower') and ob.lower > 0 else ob.price * 0.99
    close = ob.price
    if zone_def == 'lower': return lower
    if zone_def == 'close': return close
    if zone_def == 'mid': return (lower + close) / 2
    return lower

def summary(trades):
    if not trades: return {}
    n=len(trades); wins=sum(1 for t in trades if t['pnl']>0)
    avg=sum(t['pnl'] for t in trades)/n; cum=sum(t['pnl'] for t in trades)
    tp=sum(1 for t in trades if t['exit']=='tp')/n*100
    sl=sum(1 for t in trades if t['exit']=='sl')/n*100
    return {'n':n,'wr':round(wins/n*100,1),'avg':round(avg,2),'cum':round(cum,1),'tp%':round(tp,1),'sl%':round(sl,1)}

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

# ═══ MAIN ═══
t0 = time.time()
files = sorted(KLINE.glob('*_daily_300.json'))
N_STOCKS = 2000  # Limited for speed
files = files[:N_STOCKS]

# Store: param_idx -> {OB: [trades], FVG: [trades]}
param_results = {pi: {'OB': [], 'FVG': []} for pi in range(len(ALL_PARAMS))}

processed = 0
for fpath in files:
    sym = fpath.stem.replace('_daily_300', '')
    try:
        daily = json.loads(fpath.read_bytes())
        if len(daily) < 50: continue
    except: continue
    
    sigs, st, _, swings_dict = detect_all_signals_v20(daily)
    n = len(daily)
    sbb = defaultdict(list)
    for s in sigs: sbb[s.idx].append(s)
    
    processed += 1
    if processed % 500 == 0:
        elapsed = time.time() - t0
        total_trades = sum(len(param_results[pi]['OB']) + len(param_results[pi]['FVG']) for pi in range(len(ALL_PARAMS)))
        print(f"  [{processed}/{N_STOCKS}] {elapsed:.0f}s trades={total_trades}")
    
    for i in sorted(sbb.keys()):
        types_i = [s.type for s in sbb[i]]
        
        # OB_Bull: test all param combos
        if 'OB_Bull' in types_i:
            ob = next(s for s in sbb[i] if s.type == 'OB_Bull')
            entry_bar = i + 1
            if entry_bar >= n - 2: continue
            
            ep_open = daily[entry_bar]['o']
            tp, _, _ = find_tps(ep_open, sigs, swings_dict, daily)
            if tp is None: tp = ep_open * TP_CAP
            if tp > ep_open * TP_CAP: tp = ep_open * TP_CAP
            
            for pi, params in enumerate(ALL_PARAMS):
                mw = params['max_wait']; sm = params['sl_mul']; zd = params['zone_def']
                zone_entry = get_zone_entry(ob, daily, i, zd)
                
                # Find retrace
                retrace_bar = -1
                for k in range(entry_bar, min(entry_bar + mw, n)):
                    if daily[k]['l'] <= zone_entry:
                        retrace_bar = k; break
                if retrace_bar < 0: continue
                
                ep = zone_entry
                sl = ep * sm; actual_entry = retrace_bar
                
                exit_idx=-1; exit_price=0; exit_method='eod'
                for k in range(actual_entry+1, n):
                    bk = daily[k]
                    if bk['h'] >= tp: exit_idx=k; exit_price=tp; exit_method='tp'; break
                    if bk['l'] <= sl: exit_idx=k; exit_price=sl; exit_method='sl'; break
                if exit_idx<0: exit_idx=n-1; exit_price=daily[exit_idx]['c']
                if exit_idx<=actual_entry: continue
                
                pnl=(exit_price-ep)/ep*100
                param_results[pi]['OB'].append({'pnl':pnl,'exit':exit_method})
        
        # FVG_Bull: always immediate (retrace harmful)
        if 'FVG_Bull' in types_i and 'OB_Bull' not in types_i:
            entry_bar = i + 1
            if entry_bar >= n - 2: continue
            ep = daily[entry_bar]['o']
            if ep == 0: continue
            
            tp, _, _ = find_tps(ep, sigs, swings_dict, daily)
            sl, _, _ = find_sls(ep, sigs, swings_dict, daily)
            if tp is None: tp = ep * TP_CAP
            if tp > ep * TP_CAP: tp = ep * TP_CAP
            if sl is None: sl = ep * 0.97
            
            exit_idx=-1; exit_price=0; exit_method='eod'
            for k in range(entry_bar+1, n):
                bk = daily[k]
                if bk['h'] >= tp: exit_idx=k; exit_price=tp; exit_method='tp'; break
                if bk['l'] <= sl: exit_idx=k; exit_price=sl; exit_method='sl'; break
            if exit_idx<0: exit_idx=n-1; exit_price=daily[exit_idx]['c']
            if exit_idx<=entry_bar: continue
            
            pnl=(exit_price-ep)/ep*100
            for pi in range(len(ALL_PARAMS)):
                param_results[pi]['FVG'].append({'pnl':pnl,'exit':exit_method})

# ═══ Find BEST params ═══
elapsed = time.time()-t0
print(f"\n{'='*100}")
print(f"  V6.3 {len(ALL_PARAMS)}-param grid search — {processed} stocks — {elapsed:.0f}s")
print(f"{'='*100}")

# Score: WR * log(n) to balance WR and sample size
def score_func(s):
    if s['n'] < 5: return -999
    return s['wr'] * (1 + s['n']/1000)

# Best for OB
print(f"\n  TOP 10 OB_Bull params:")
ob_scores = []
for pi, params in enumerate(ALL_PARAMS):
    s = summary(param_results[pi]['OB'])
    sc = score_func(s)
    ob_scores.append((sc, pi, params, s))

ob_scores.sort(key=lambda x: -x[0])
for rank, (sc, pi, params, s) in enumerate(ob_scores[:10]):
    print(f"  #{rank+1}: mw={params['max_wait']} sl={params['sl_mul']} zone={params['zone_def']:<6s} "
          f"n={s['n']} WR={s['wr']}% avg={s['avg']:+.2f}% cum={s['cum']:+.1f}% tp={s['tp%']}% sl={s['sl%']}%")

# Worst for OB
print(f"\n  BOTTOM 5 OB_Bull params:")
for rank, (sc, pi, params, s) in enumerate(ob_scores[-5:]):
    print(f"  #{len(ob_scores)-4+rank}: mw={params['max_wait']} sl={params['sl_mul']} zone={params['zone_def']:<6s} "
          f"n={s['n']} WR={s['wr']}% avg={s['avg']:+.2f}%")

# Best per parameter dimension
print(f"\n  Best per SL multiplier (OB):")
for sm in SL_MULS:
    subset = [(pi,p,s) for sc,pi,p,s in ob_scores if p['sl_mul']==sm and summary(param_results[pi]['OB'])['n']>=10]
    if subset:
        best = max(subset, key=lambda x: score_func(summary(param_results[x[0]]['OB'])))
        s = summary(param_results[best[0]]['OB'])
        print(f"    SL={sm}: mw={best[1]['max_wait']} zone={best[1]['zone_def']} n={s['n']} WR={s['wr']}% avg={s['avg']:+.2f}%")

print(f"\n  Best per MAX_WAIT (OB):")
for mw in MAX_WAITS:
    subset = [(pi,p,s) for sc,pi,p,s in ob_scores if p['max_wait']==mw and summary(param_results[pi]['OB'])['n']>=10]
    if subset:
        best = max(subset, key=lambda x: score_func(summary(param_results[x[0]]['OB'])))
        s = summary(param_results[best[0]]['OB'])
        print(f"    MW={mw}: sl={best[1]['sl_mul']} zone={best[1]['zone_def']} n={s['n']} WR={s['wr']}% avg={s['avg']:+.2f}%")

# BEST overall
best_pi, best_params, best_s = max(
    [(pi, ALL_PARAMS[pi], summary(param_results[pi]['OB'])) for pi in range(len(ALL_PARAMS))],
    key=lambda x: score_func(x[2])
)
print(f"\n  ⭐ BEST OB: mw={best_params['max_wait']} sl={best_params['sl_mul']} zone={best_params['zone_def']} "
      f"n={best_s['n']} WR={best_s['wr']}% avg={best_s['avg']:+.2f}% cum={best_s['cum']:+.1f}%")

# Save
output = {
    'meta': {'version':'V6.3 grid','date':time.strftime('%Y-%m-%d'),'stocks':processed,
             'params':len(ALL_PARAMS),'elapsed':round(elapsed)},
    'params': ALL_PARAMS,
    'ob_top10': [{'rank':r+1,'params':ALL_PARAMS[pi],'summary':summary(param_results[pi]['OB'])} 
                 for r,(sc,pi,_,_) in enumerate(ob_scores[:10])],
    'best_ob': {'params': best_params, 'summary': best_s},
}
json.dump(output, open(OUT/'grid_search_v63.json','w'), ensure_ascii=False, indent=2)
print(f"\n  保存: {OUT/'grid_search_v63.json'}")
