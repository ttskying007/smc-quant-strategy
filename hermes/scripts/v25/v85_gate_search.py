#!/usr/bin/env python3
from __future__ import annotations
import json,itertools
from pathlib import Path
import numpy as np
import pandas as pd

rows=json.loads(Path('/root/.hermes/smc_opt_v85_mixed_accumulation_generator/v85_candidates.json').read_text())
df=pd.DataFrame(rows)
for col in ['pnl_pct','v85_zone_width_pct','risk_pct','hold_bars']:
    df[col]=pd.to_numeric(df[col], errors='coerce').fillna(999 if col!='pnl_pct' else 0)
df['year']=df['entry_date'].astype(str).str[:4]
df=df[df['year'].isin(['2023','2024','2025','2026'])].reset_index(drop=True)
years=['2023','2024','2025','2026']
year_masks={y:(df['year'].values==y) for y in years}
pnl=df['pnl_pct'].values
win=pnl>0
poi=(df['exit_reason'].values=='EXIT_POI_CLOSE_BREAK')
trend=(df['exit_reason'].values=='EXIT_TREND_STRUCTURE_DAMAGE')

def calc(mask):
    n=int(mask.sum())
    if n==0: return None
    return {'n':n,'wr':round(float(win[mask].mean()*100),2),'avg':round(float(pnl[mask].mean()),4),'cum':round(float(pnl[mask].sum()),2),'poi':round(float(poi[mask].mean()*100),2),'trend':round(float(trend[mask].mean()*100),2)}

preds=[]
def add(name,mask,group): preds.append((name,mask.astype(bool),group))
for val in sorted(df['v85_path'].dropna().unique()): add(f'path={val}',df['v85_path'].values==val,'path')
for val in sorted(df['market_state'].dropna().unique()): add(f'state={val}',df['market_state'].values==val,'state')
for vals,name in [({'BULL_CONTINUATION','MIXED'},'state_BULL_MIXED'),({'BULL_CONTINUATION','MIXED','RECOVERY'},'state_no_ACC'),({'BULL_CONTINUATION','MIXED','ACCUMULATION'},'state_no_REC')]: add(name,df['market_state'].isin(vals).values,'stategrp')
for th in [1.0,1.2,1.5,1.8,2.0,2.3,2.5,3.0,4.0,5.0]: add(f'zw<={th}',df['v85_zone_width_pct'].values<=th,'zw')
for lo,hi in [(0.5,1.5),(0.8,1.8),(1,2),(1,2.5),(1.2,2.5),(1.5,3.0)]: add(f'zw_{lo}_{hi}',((df['v85_zone_width_pct'].values>lo)&(df['v85_zone_width_pct'].values<=hi)),'zwband')
for th in [1.5,2.0,2.5,3.0,4.0,5.0,6.0,8.0]: add(f'risk<={th}',df['risk_pct'].values<=th,'risk')
for lo,hi in [(1,5),(1.5,5),(1.5,4),(2,5),(2,6)]: add(f'risk_{lo}_{hi}',((df['risk_pct'].values>lo)&(df['risk_pct'].values<=hi)),'riskband')
for th in [2,3,5,8,13,20]: add(f'hold<={th}',df['hold_bars'].values<=th,'hold')

best=[]
for k in range(1,5):
    for combo in itertools.combinations(range(len(preds)),k):
        groups=[preds[i][2] for i in combo]
        if len(groups)!=len(set(groups)): continue
        mask=np.ones(len(df), dtype=bool)
        names=[]
        for i in combo:
            names.append(preds[i][0]); mask &= preds[i][1]
        if mask.sum()<500: continue
        yy={}
        ok=True
        for y in years:
            ym=mask & year_masks[y]
            if ym.sum()<50:
                ok=False; break
            yy[y]=calc(ym)
        if not ok: continue
        m=calc(mask)
        minwr=min(yy[y]['wr'] for y in years)
        minavg=min(yy[y]['avg'] for y in years)
        best.append(((minwr,m['wr'],m['avg'],m['n']),names,m,yy))
best.sort(reverse=True)
out=[]
for score,names,m,yy in best[:80]:
    out.append({'score':score,'predicates':names,'metrics':m,'year':yy})
Path('/root/.hermes/smc_opt_v85_mixed_accumulation_generator/v85_gate_search.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print('best_count',len(best))
print(json.dumps(out[:20],ensure_ascii=False,indent=2))
