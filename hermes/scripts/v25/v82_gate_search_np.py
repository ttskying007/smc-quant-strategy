#!/usr/bin/env python3
import json,itertools, numpy as np
from pathlib import Path
rows=json.loads(Path('/root/.hermes/smc_opt_v81_contextual_smc_generator/v81_candidates.json').read_text())
def f(x,d=0.0):
    try:
        if x is None or x=='': return d
        return float(x)
    except Exception: return d
N=len(rows)
pnl=np.array([f(r.get('pnl_pct')) for r in rows], dtype=float)
years=np.array([str(r.get('entry_date',''))[:4] for r in rows])
exit_reason=np.array([str(r.get('exit_reason')) for r in rows])
for r in rows:
    entry=f(r.get('entry_price')); zl=f(r.get('zone_low')); zh=f(r.get('zone_high')); target=f(r.get('liquidity_target')); eq=f(r.get('equilibrium')); prior=f(r.get('prior_structure_low'))
    touch=int(r.get('touch_idx') or 0); reclaim=int(r.get('reclaim_idx') or 0); event=int(r.get('event_idx') or 0); entryi=int(r.get('entry_idx') or 0)
    r['_risk']=(entry/zl-1)*100 if entry and zl else 999
    r['_zone_width']=(zh/zl-1)*100 if zl and zh else 999
    r['_target_rr']=(target-entry)/(entry-zl) if target and entry and zl and entry>zl else 0
    r['_reclaim_lag']=reclaim-touch if reclaim and touch else 999
    r['_event_to_entry']=entryi-event if entryi and event else 999
    r['_discount_depth']=(eq-zh)/eq*100 if eq and zh else -999
    r['_prior_buffer']=(zl/prior-1)*100 if prior and zl else 999
pred_defs=[]
def add(name,fam,fn): pred_defs.append((name,fam,np.fromiter((fn(r) for r in rows), dtype=bool, count=N)))
for states_name,states in [('env_bull_bear',{'BULL_CONTINUATION','BEAR_RISK'}),('env_no_acc_rec',{'BULL_CONTINUATION','BEAR_RISK','DISTRIBUTION','MIXED'}),('env_bull_only',{'BULL_CONTINUATION'}),('env_bear_only',{'BEAR_RISK'}),('env_no_mixed_rec_acc',{'BULL_CONTINUATION','BEAR_RISK','DISTRIBUTION'})]: add(states_name,'env',lambda r,states=states:r.get('market_state') in states)
for story in ['UP_CONTINUATION_BOS_PULLBACK_TO_POI_RECLAIM','DOWN_REVERSAL_SSL_SWEEP_CHOCH_PULLBACK_TO_POI_RECLAIM']:
    add(story.split('_')[0].lower()+'_story','story',lambda r,story=story:r.get('story')==story)
for trend in ['RANGE_TRANSITION','RECOVERY_TRANSITION','UP_CONTINUATION','DOWN_REVERSAL_REQUIRED']:
    add(trend.lower(),'trend',lambda r,trend=trend:r.get('trend_regime')==trend)
for pd in ['DEEP_DISCOUNT','DISCOUNT']: add(pd.lower(),'pd',lambda r,pd=pd:r.get('pd_zone')==pd)
for th in [2,3,4,5,6,8,12]: add(f'risk_le_{th}','risk',lambda r,th=th:r['_risk']<=th)
for lo,hi,name in [(1,4,'risk_1_4'),(2,5,'risk_2_5'),(1,6,'risk_1_6'),(0,4,'risk_0_4')]: add(name,'riskband',lambda r,lo=lo,hi=hi:lo<r['_risk']<=hi)
for th in [0.5,1,1.5,2,3,5]: add(f'rr_ge_{th}','rr',lambda r,th=th:r['_target_rr']>=th)
for lo,hi,name in [(1,5,'rr_1_5'),(1.5,6,'rr_1p5_6'),(2,999,'rr_ge_2'),(0.5,3,'rr_0p5_3')]: add(name,'rrband',lambda r,lo=lo,hi=hi:lo<=r['_target_rr']<=hi)
for th in [0,1,2,5]: add(f'discount_depth_ge_{th}','depth',lambda r,th=th:r['_discount_depth']>=th)
for th in [0.5,1,2,3,5]: add(f'zone_width_le_{th}','zwidth',lambda r,th=th:r['_zone_width']<=th)
for lo,hi,name in [(0.5,3,'zone_width_0p5_3'),(1,3,'zone_width_1_3'),(1,5,'zone_width_1_5')]: add(name,'zwidthband',lambda r,lo=lo,hi=hi:lo<r['_zone_width']<=hi)
for th in [1,2,3,5]: add(f'reclaim_lag_ge_{th}','reclaim',lambda r,th=th:r['_reclaim_lag']>=th and r['_reclaim_lag']<999)
for th in [3,5,8]: add(f'event_to_entry_ge_{th}','e2e',lambda r,th=th:r['_event_to_entry']>=th and r['_event_to_entry']<999)
for lo,hi,name in [(-5,2,'prior_buffer_le2'),(-5,5,'prior_buffer_le5'),(0,5,'prior_buffer_0_5'),(-999,0,'prior_below_zone')]: add(name,'priorbuf',lambda r,lo=lo,hi=hi:lo<=r['_prior_buffer']<=hi)
preds=[p for p in pred_defs if int(p[2].sum())>=50]
print('N',N,'preds',len(preds), flush=True)
year_masks={yy:(years==yy) for yy in ['2023','2024','2025','2026']}
def met(mask):
    n=int(mask.sum())
    if not n: return {'n':0,'wr':0,'avg':0,'cum':0,'poi_break':0,'trend_damage':0,'tp':0}
    vals=pnl[mask]
    return {'n':n,'wr':float((vals>0).mean()*100),'avg':float(vals.mean()),'cum':float(vals.sum()),'poi_break':float((exit_reason[mask]=='EXIT_POI_CLOSE_BREAK').mean()*100),'trend_damage':float((exit_reason[mask]=='EXIT_TREND_STRUCTURE_DAMAGE').mean()*100),'tp':float((exit_reason[mask]=='TAKE_PROFIT_LIQUIDITY_TARGET').mean()*100)}
def rec(mask,names):
    m=met(mask); y={yy:met(mask & ym) for yy,ym in year_masks.items()}
    min_n=min(v['n'] for v in y.values()); min_wr=min(v['wr'] if v['n'] else 0 for v in y.values()); min_avg=min(v['avg'] if v['n'] else -999 for v in y.values())
    return (min_wr,min_n,m['wr'],m['avg'],m['n'],names,m,y,min_avg)
prod=[]; wide=[]; best=[]
for k in range(1,5):
  for combo in itertools.combinations(preds,k):
    fams=[c[1] for c in combo]
    if len(fams)!=len(set(fams)): continue
    mask=np.ones(N,dtype=bool)
    for _,_,mm in combo: mask &= mm
    n=int(mask.sum())
    if n<50: continue
    if k>=4 and n<400: continue
    r=rec(mask,[c[0] for c in combo]); best.append(r)
    if r[4]>=500 and r[1]>=50: wide.append(r)
    if r[4]>=500 and r[1]>=50 and r[0]>=65 and r[8]>0: prod.append(r)
  print('k',k,'best',len(best),'wide',len(wide),'prod',len(prod), flush=True)
def clean(d): return {k:(round(v,2) if isinstance(v,float) else v) for k,v in d.items()}
def obj(r): return {'rules':r[5],'m':clean(r[6]),'years':{yy:clean(r[7][yy]) for yy in ['2023','2024','2025','2026']},'min_year_wr':round(r[0],2),'min_year_n':r[1]}
prod.sort(key=lambda r:(r[2],r[3],r[4]),reverse=True); wide.sort(key=lambda r:(r[0],r[3],r[2],r[4]),reverse=True); best.sort(key=lambda r:(r[0],r[1],r[3],r[2],r[4]),reverse=True)
out={'counts':{'rows':N,'preds':len(preds),'best':len(best),'wide':len(wide),'prod':len(prod)},'prod':[obj(r) for r in prod[:50]],'wide':[obj(r) for r in wide[:50]],'best':[obj(r) for r in best[:50]]}
Path('/root/.hermes/smc_opt_v81_contextual_smc_generator/v82_gate_search_np.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps(out['counts'],ensure_ascii=False))
for lab in ['prod','wide','best']:
 print('\n'+lab.upper())
 for x in out[lab][:8]: print(json.dumps(x,ensure_ascii=False))
