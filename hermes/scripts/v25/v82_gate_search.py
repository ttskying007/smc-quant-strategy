#!/usr/bin/env python3
import json,itertools
from pathlib import Path
rows=json.loads(Path('/root/.hermes/smc_opt_v81_contextual_smc_generator/v81_candidates.json').read_text())
def f(x,d=0.0):
    try:
        if x is None or x=='': return d
        return float(x)
    except Exception: return d
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
N=len(rows); ALL=(1<<N)-1
pnl=[f(r.get('pnl_pct')) for r in rows]
years=[str(r.get('entry_date',''))[:4] for r in rows]
exit_reasons=[r.get('exit_reason') for r in rows]
def mask_for(fn):
    mask=0
    for i,r in enumerate(rows):
        if fn(r): mask|=1<<i
    return mask
def bit_indices(mask):
    while mask:
        lsb=mask & -mask; yield lsb.bit_length()-1; mask-=lsb
def metrics(idxs):
    idxs=list(idxs); n=len(idxs)
    if not n: return {'n':0,'wr':0,'avg':0,'cum':0,'poi_break':0,'trend_damage':0,'tp':0}
    return {'n':n,'wr':sum(pnl[i]>0 for i in idxs)/n*100,'avg':sum(pnl[i] for i in idxs)/n,'cum':sum(pnl[i] for i in idxs),'poi_break':sum(exit_reasons[i]=='EXIT_POI_CLOSE_BREAK' for i in idxs)/n*100,'trend_damage':sum(exit_reasons[i]=='EXIT_TREND_STRUCTURE_DAMAGE' for i in idxs)/n*100,'tp':sum(exit_reasons[i]=='TAKE_PROFIT_LIQUIDITY_TARGET' for i in idxs)/n*100}
def eval_mask(mask):
    idxs=list(bit_indices(mask)); m=metrics(idxs); y={}
    for yy in ['2023','2024','2025','2026']:
        yi=[i for i in idxs if years[i]==yy]; y[yy]=metrics(yi)
    return m,y
pred_defs=[]
for states_name,states in [('env_bull_bear',{'BULL_CONTINUATION','BEAR_RISK'}),('env_no_acc_rec',{'BULL_CONTINUATION','BEAR_RISK','DISTRIBUTION','MIXED'}),('env_bull_only',{'BULL_CONTINUATION'}),('env_bear_only',{'BEAR_RISK'}),('env_no_mixed_rec_acc',{'BULL_CONTINUATION','BEAR_RISK','DISTRIBUTION'})]:
    pred_defs.append((states_name,'env',lambda r,states=states:r.get('market_state') in states))
for story in ['UP_CONTINUATION_BOS_PULLBACK_TO_POI_RECLAIM','DOWN_REVERSAL_SSL_SWEEP_CHOCH_PULLBACK_TO_POI_RECLAIM']:
    pred_defs.append((story.split('_')[0].lower()+'_story','story',lambda r,story=story:r.get('story')==story))
for trend in ['RANGE_TRANSITION','RECOVERY_TRANSITION','UP_CONTINUATION','DOWN_REVERSAL_REQUIRED']:
    pred_defs.append((trend.lower(),'trend',lambda r,trend=trend:r.get('trend_regime')==trend))
for pd in ['DEEP_DISCOUNT','DISCOUNT']:
    pred_defs.append((pd.lower(),'pd',lambda r,pd=pd:r.get('pd_zone')==pd))
for th in [2,3,4,5,6,8,12]: pred_defs.append((f'risk_le_{th}','risk',lambda r,th=th:r['_risk']<=th))
for lo,hi,name in [(1,4,'risk_1_4'),(2,5,'risk_2_5'),(1,6,'risk_1_6'),(0,4,'risk_0_4')]: pred_defs.append((name,'riskband',lambda r,lo=lo,hi=hi:lo<r['_risk']<=hi))
for th in [0.5,1,1.5,2,3,5]: pred_defs.append((f'rr_ge_{th}','rr',lambda r,th=th:r['_target_rr']>=th))
for lo,hi,name in [(1,5,'rr_1_5'),(1.5,6,'rr_1p5_6'),(2,999,'rr_ge_2'),(0.5,3,'rr_0p5_3')]: pred_defs.append((name,'rrband',lambda r,lo=lo,hi=hi:lo<=r['_target_rr']<=hi))
for th in [0,1,2,5]: pred_defs.append((f'discount_depth_ge_{th}','depth',lambda r,th=th:r['_discount_depth']>=th))
for th in [0.5,1,2,3,5]: pred_defs.append((f'zone_width_le_{th}','zwidth',lambda r,th=th:r['_zone_width']<=th))
for lo,hi,name in [(0.5,3,'zone_width_0p5_3'),(1,3,'zone_width_1_3'),(1,5,'zone_width_1_5')]: pred_defs.append((name,'zwidthband',lambda r,lo=lo,hi=hi:lo<r['_zone_width']<=hi))
for th in [1,2,3,5]: pred_defs.append((f'reclaim_lag_ge_{th}','reclaim',lambda r,th=th:r['_reclaim_lag']>=th and r['_reclaim_lag']<999))
for th in [3,5,8]: pred_defs.append((f'event_to_entry_ge_{th}','e2e',lambda r,th=th:r['_event_to_entry']>=th and r['_event_to_entry']<999))
for lo,hi,name in [(-5,2,'prior_buffer_le2'),(-5,5,'prior_buffer_le5'),(0,5,'prior_buffer_0_5'),(-999,0,'prior_below_zone')]: pred_defs.append((name,'priorbuf',lambda r,lo=lo,hi=hi:lo<=r['_prior_buffer']<=hi))
preds=[]
for name,fam,fn in pred_defs:
    m=mask_for(fn); n=m.bit_count()
    if n>=50: preds.append((name,fam,m,n))
prod=[]; wide=[]; best=[]
for k in range(1,6):
    for combo in itertools.combinations(preds,k):
        fams=[c[1] for c in combo]
        if len(fams)!=len(set(fams)): continue
        mask=ALL
        for _,_,mm,_ in combo: mask &= mm
        n=mask.bit_count()
        if n<50: continue
        if k>=4 and n<350: continue
        m,y=eval_mask(mask)
        min_n=min(y[yy]['n'] for yy in ['2023','2024','2025','2026']); min_wr=min(y[yy]['wr'] if y[yy]['n'] else 0 for yy in ['2023','2024','2025','2026']); min_avg=min(y[yy]['avg'] if y[yy]['n'] else -999 for yy in ['2023','2024','2025','2026'])
        rec=(min_wr,min_n,m['wr'],m['avg'],m['n'],[c[0] for c in combo],m,y)
        best.append(rec)
        if m['n']>=500 and min_n>=50: wide.append(rec)
        if m['n']>=500 and min_n>=50 and min_wr>=65 and min_avg>0: prod.append(rec)
def clean(d): return {k:(round(v,2) if isinstance(v,float) else v) for k,v in d.items()}
def obj(r): return {'rules':r[5],'m':clean(r[6]),'years':{yy:clean(r[7][yy]) for yy in ['2023','2024','2025','2026']},'min_year_wr':round(r[0],2),'min_year_n':r[1]}
prod.sort(key=lambda r:(r[2],r[3],r[4]),reverse=True)
wide.sort(key=lambda r:(r[0],r[3],r[2],r[4]),reverse=True)
best.sort(key=lambda r:(r[0],r[1],r[3],r[2],r[4]),reverse=True)
out={'counts':{'rows':N,'preds':len(preds),'best':len(best),'wide':len(wide),'prod':len(prod)},'prod':[obj(r) for r in prod[:100]],'wide':[obj(r) for r in wide[:100]],'best':[obj(r) for r in best[:100]]}
Path('/root/.hermes/smc_opt_v81_contextual_smc_generator/v82_gate_search.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps(out['counts'],ensure_ascii=False))
for label in ['prod','wide','best']:
    print('\n'+label.upper())
    for x in out[label][:10]: print(json.dumps(x,ensure_ascii=False))
