#!/usr/bin/env python3
from __future__ import annotations
import sys, json, itertools, math
from pathlib import Path
sys.path.insert(0,'/root/.hermes/scripts/v25')
import v99_economic_autopsy as vea
_orig_kline=vea.kline
_cache={}
def kline_cached(symbol):
    if symbol not in _cache:
        _cache[symbol]=_orig_kline(symbol)
    return _cache[symbol]
vea.kline=kline_cached
sim=vea.sim
rows=json.loads(Path('/root/.hermes/smc_opt_v98_reachable_5r_probability_gate/v98_structural_trades.json').read_text())
base=[r for r in rows if r.get('production_grade')=='A_PRODUCTION']
def f(x,d=0):
    try:
        if x in (None,''): return d
        v=float(x); return v if math.isfinite(v) else d
    except Exception: return d
def metrics(rs):
    if not rs: return {'n':0}
    pn=[f(r.get('pnl_pct')) for r in rs]
    wins=[x for x in pn if x>0]; net=[x for x in pn if x>=0.8]; losses=[x for x in pn if x<=0]
    yrs=[]
    for y in ['2023','2024','2025','2026']:
        yp=[f(r.get('pnl_pct')) for r in rs if str(r.get('entry_date') or '').startswith(y)]
        if yp: yrs.append((len(yp),sum(x>=0.8 for x in yp)/len(yp)*100))
    return {'n':len(rs),'gross':round(len(wins)/len(rs)*100,2),'net':round(len(net)/len(rs)*100,2),'small':round(sum(0<x<0.8 for x in pn)/len(rs)*100,2),'loss':round(len(losses)/len(rs)*100,2),'avg':round(sum(pn)/len(pn),4),'pf':round(sum(wins)/abs(sum(losses)),2) if losses and abs(sum(losses))>1e-9 else None,'min_year_n':min([x[0] for x in yrs] or [0]),'worst_year_net':round(min([x[1] for x in yrs] or [0]),2)}
def b(r,name):
    return {
    'risk_le_0_8': f(r.get('risk_pct'))<=0.8, 'risk_le_1_0': f(r.get('risk_pct'))<=1.0, 'risk_le_1_2': f(r.get('risk_pct'))<=1.2,
    'risk_ge_0_8': f(r.get('risk_pct'))>=0.8, 'vol_le_0_8': f(r.get('volatility_pct'))<=0.8, 'vol_le_1_0': f(r.get('volatility_pct'))<=1.0,
    'tp2_le_5_2': f(r.get('tp2_rr'))<=5.2, 'tp2_le_5_5': f(r.get('tp2_rr'))<=5.5, 'tp2_le_6_0': f(r.get('tp2_rr'))<=6.0,
    'tp2_ge_5_2': f(r.get('tp2_rr'))>=5.2, 'tp3_le_12': f(r.get('tp3_rr'))<=12, 'tp3_le_14': f(r.get('tp3_rr'))<=14,
    'mixed': r.get('market_state')=='MIXED', 'bull': r.get('market_state')=='BULL_CONTINUATION', 'not_recovery': r.get('market_state')!='RECOVERY',
    'deep': r.get('pd_zone')=='DEEP_DISCOUNT', 'discount': r.get('pd_zone')=='DISCOUNT', 'ssl': r.get('event_type')=='SSL_SWEEP_CHOCH_REVERSAL', 'bos': r.get('event_type')=='BOS_CONTINUATION',
    'v91_pass': r.get('v91_gate_reason')=='PASS', 'sl_poi': r.get('sl_mode')=='POI_LOW_BUFFER_0_5PCT', 'sl_struct': r.get('sl_mode')!='POI_LOW_BUFFER_0_5PCT',
    }.get(name,False)
preds=['risk_le_0_8','risk_le_1_0','risk_le_1_2','risk_ge_0_8','vol_le_0_8','vol_le_1_0','tp2_le_5_2','tp2_le_5_5','tp2_le_6_0','tp2_ge_5_2','tp3_le_12','tp3_le_14','mixed','bull','not_recovery','deep','discount','ssl','bos','v91_pass','sl_poi','sl_struct']
contr=[('mixed','bull'),('deep','discount'),('ssl','bos'),('sl_poi','sl_struct'),('risk_le_0_8','risk_ge_0_8'),('tp2_le_5_2','tp2_ge_5_2')]
report={}
for mode in ['no_protect','lock3_1r','lock4_2r','lock5_2r','hybrid3_1r_5_2r','hybrid4_2r_6_3r']:
    sims=[sim(r,mode) for r in base]
    best=[]
    for L in range(1,5):
      for combo in itertools.combinations(preds,L):
        if any(a in combo and b0 in combo for a,b0 in contr): continue
        rs=[r for r in sims if all(b(r,c) for c in combo)]
        if len(rs)>=50:
          m=metrics(rs); m['rule']=' & '.join(combo); best.append(m)
    report[mode]={'base':metrics(sims),'top':sorted(best,key=lambda x:(x['net']>=90, x['n']>=100, x['net'], x['avg'], x['n']), reverse=True)[:30]}
print(json.dumps(report, ensure_ascii=False, indent=2))
