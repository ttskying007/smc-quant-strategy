#!/usr/bin/env python3
from __future__ import annotations
import json, math, glob, bisect
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import pandas as pd

BASE=Path('/root/.hermes')
AUDIT=BASE/'smc_audit'
KDIR=BASE/'kline_cache'
OUT=AUDIT/('v244_post_v243_industry_participation_probe_no_write_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
OUT.mkdir(parents=True, exist_ok=True)
V236= AUDIT/'v236_v235_independent_audit_current_smoke_no_write_20260627_114943/v236_independent_combined_rows.csv'
V230= AUDIT/'v230_v228_plus_new_supply_expansion_probe_no_write_20260627_053747/v230_candidate_pool_enriched.csv'
INDMAP= AUDIT/'v225_baostock_industry_participation_probe_20260627_031854/baostock_stock_industry.json'

def dn(x):
    s=''.join(ch for ch in str(x or '').replace('-','')[:10] if ch.isdigit())
    return s[:8] if len(s)>=8 else ''
def sf(x, default=math.nan):
    try:
        if x is None or x=='': return default
        v=float(x)
        return v if not math.isnan(v) else default
    except Exception: return default

def metrics(df):
    if len(df)==0:
        return dict(n=0, wr=0, avg=0, median=0, min_year_n=0, year_counts={}, year_wr={}, all_year_wr_min=0, micro_profit_pct=0, loss_n=0, t1=0)
    pnl=pd.to_numeric(df['pnl_pct'], errors='coerce')
    won=pnl>0
    years=df['entry_date'].astype(str).str[:4]
    yc=years.value_counts().sort_index().to_dict()
    ywr={str(y): round(float((pnl[years==y]>0).mean()*100),2) for y in sorted(years.dropna().unique())}
    t1=0
    if 'exit_date' in df.columns:
        t1=int(((df['exit_date'].map(dn)==df['entry_date'].map(dn)) & df['exit_date'].map(dn).ne('')).sum())
    return dict(n=int(len(df)), wr=round(float(won.mean()*100),4), avg=round(float(pnl.mean()),4), median=round(float(pnl.median()),4), min_year_n=int(min(yc.values()) if yc else 0), year_counts={str(k):int(v) for k,v in yc.items()}, year_wr=ywr, all_year_wr_min=round(float(min(ywr.values()) if ywr else 0),2), micro_profit_pct=round(float(((pnl>0)&(pnl<1)).mean()*100),4), loss_n=int((pnl<=0).sum()), t1=t1)

def pass_gate(m, gate):
    return (m['n']>=gate['n'] and m['min_year_n']>=gate['min_year_n'] and m['wr']>=gate['wr'] and m['avg']>=gate['avg'] and m['all_year_wr_min']>=gate['all_year_wr_min'] and m['micro_profit_pct']<=gate['micro'] and m['t1']==0)

items=json.loads(INDMAP.read_text())
sym_ind={r.get('symbol'): (r.get('industry') or 'UNKNOWN') for r in items if r.get('symbol')}
industry_daily=defaultdict(lambda: defaultdict(list))
for fp in glob.glob(str(KDIR/'*_daily_750.json')):
    name=Path(fp).name.split('_')
    if len(name)<2 or not name[0].isdigit(): continue
    sym=name[0]+'.'+name[1]
    ind=sym_ind.get(sym,'UNKNOWN')
    if not ind or ind=='UNKNOWN': continue
    try: data=json.loads(Path(fp).read_text())
    except Exception: continue
    bars=[]
    for b in data:
        d=dn(b.get('t') or b.get('date')); c=sf(b.get('c'))
        if d and not math.isnan(c): bars.append((d,c))
    bars.sort()
    for i in range(1,len(bars)):
        d,c=bars[i]; pc=bars[i-1][1]
        if pc: industry_daily[d][ind].append((c/pc-1)*100)
feature_by_date_ind={}
for d, mp in industry_daily.items():
    for ind, vals in mp.items():
        if not vals: continue
        s=pd.Series(vals)
        feature_by_date_ind[(d,ind)]={
            'v244_ind_n': int(len(vals)),
            'v244_ind_up1_pct': float((s>1).mean()*100),
            'v244_ind_down1_pct': float((s<-1).mean()*100),
            'v244_ind_strong1_pct': float((s>3).mean()*100),
            'v244_ind_weak1_pct': float((s<-3).mean()*100),
            'v244_ind_mean_ret1': float(s.mean()),
            'v244_ind_median_ret1': float(s.median()),
        }
all_dates=sorted({d for d,_ in feature_by_date_ind.keys()})
def prev_date(d):
    i=bisect.bisect_left(all_dates, dn(d))-1
    return all_dates[i] if i>=0 else ''
def attach_ind(df):
    df=df.copy()
    inds=[]; pds=[]; feats=[]
    for _,r in df.iterrows():
        sym=str(r.get('symbol'))
        ind=sym_ind.get(sym,'UNKNOWN')
        pdte=prev_date(r.get('entry_date'))
        f=feature_by_date_ind.get((pdte,ind),{})
        inds.append(ind); pds.append(pdte); feats.append(f)
    df['v244_industry']=inds; df['v244_industry_prev_date']=pds
    for col in ['v244_ind_n','v244_ind_up1_pct','v244_ind_down1_pct','v244_ind_strong1_pct','v244_ind_weak1_pct','v244_ind_mean_ret1','v244_ind_median_ret1']:
        df[col]=[f.get(col, math.nan) for f in feats]
    if 'v236_all_strong1_pct' in df.columns:
        df['v244_ind_vs_all_strong1']=pd.to_numeric(df['v244_ind_strong1_pct'],errors='coerce')-pd.to_numeric(df['v236_all_strong1_pct'],errors='coerce')
    elif 'v230_all_strong1_pct' in df.columns:
        df['v244_ind_vs_all_strong1']=pd.to_numeric(df['v244_ind_strong1_pct'],errors='coerce')-pd.to_numeric(df['v230_all_strong1_pct'],errors='coerce')
    return df

v236=attach_ind(pd.read_csv(V236, low_memory=False))
v230=attach_ind(pd.read_csv(V230, low_memory=False))
v236['entry_date']=v236['entry_date'].map(dn); v230['entry_date']=v230['entry_date'].map(dn)
hist=set(zip(v236.symbol.astype(str), v236.entry_date.astype(str)))
v239_base=v236[pd.to_numeric(v236['v236_br_above_ma20'], errors='coerce')>=13.8778].copy()
child_pool=v230.copy()
mask=(
    child_pool['market_state'].astype(str).isin(['ACCUMULATION','BEAR_RISK']) &
    (child_pool['event_type'].astype(str)=='SSL_SWEEP_CHOCH_REVERSAL') &
    child_pool['poi_source'].astype(str).isin(['DEMAND_OB','OB+FVG']) &
    (pd.to_numeric(child_pool['v132_bull_count_3'],errors='coerce')>=3) &
    (pd.to_numeric(child_pool['v132_post_zone_pullback_depth_pct_3'],errors='coerce')<=40) &
    (pd.to_numeric(child_pool['v230_all_strong1_pct'],errors='coerce').between(10,55)) &
    (pd.to_numeric(child_pool['entry_chase_above_zone_pct'],errors='coerce')<=2.5)
)
child_pool=child_pool[mask].copy()
child_pool=child_pool[~pd.MultiIndex.from_frame(child_pool[['symbol','entry_date']]).isin(pd.MultiIndex.from_tuples(list(hist), names=['symbol','entry_date']))]
pri_poi={'DEMAND_OB':0,'OB+FVG':1,'FVG_Demand':2}
child_pool['_poi_pri']=child_pool['poi_source'].map(pri_poi).fillna(9)
child_pool['_risk']=pd.to_numeric(child_pool['risk_pct'],errors='coerce').fillna(999)
child_pool['_chase']=pd.to_numeric(child_pool['entry_chase_above_zone_pct'],errors='coerce').fillna(999)
child_pool=child_pool.sort_values(['symbol','entry_date','_poi_pri','_risk','_chase']).drop_duplicates(['symbol','entry_date'], keep='first')
for c in set(v236.columns)-set(child_pool.columns): child_pool[c]=math.nan
for c in set(child_pool.columns)-set(v236.columns): v239_base[c]=math.nan
base_options=[]
for brmin in [0,10,13.8778,20,25]:
    base=v236[pd.to_numeric(v236['v236_br_above_ma20'], errors='coerce')>=brmin].copy()
    base_options.append((f'base_br>={brmin}', base))
    for ind_min in [0,5,10,15,20,25,30]:
      for ind_max in [55,65,75,85,100]:
        b=base[pd.to_numeric(base['v244_ind_strong1_pct'],errors='coerce').between(ind_min, ind_max)].copy()
        if len(b)>=450: base_options.append((f'base_br>={brmin};ind_strong1={ind_min}..{ind_max}', b))
    for rel_min in [-30,-20,-10,0,5,10]:
        b=base[pd.to_numeric(base['v244_ind_vs_all_strong1'],errors='coerce')>=rel_min].copy()
        if len(b)>=450: base_options.append((f'base_br>={brmin};ind_vs_all>={rel_min}', b))
child_options=[('child_none', child_pool.iloc[0:0].copy())]
for ind_min in [0,5,10,15,20,25,30]:
  for ind_max in [55,65,75,85,100]:
    c=child_pool[pd.to_numeric(child_pool['v244_ind_strong1_pct'],errors='coerce').between(ind_min,ind_max)].copy()
    child_options.append((f'child_ind_strong1={ind_min}..{ind_max}', c))
for rel_min in [-30,-20,-10,0,5,10]:
    c=child_pool[pd.to_numeric(child_pool['v244_ind_vs_all_strong1'],errors='coerce')>=rel_min].copy()
    child_options.append((f'child_ind_vs_all>={rel_min}', c))
for upmax in [80,90,95,100]:
    c=child_pool[pd.to_numeric(child_pool['v244_ind_up1_pct'],errors='coerce')<=upmax].copy()
    child_options.append((f'child_ind_up1<={upmax}', c))
PROD={'n':570,'min_year_n':70,'wr':93.0,'avg':7.6,'all_year_wr_min':91.0,'micro':1.0}
RESEARCH={'n':550,'min_year_n':65,'wr':92.8,'avg':7.45,'all_year_wr_min':90.0,'micro':1.0}
front=[]; best_rows=None; best_rec=None; best_score=None; specs=0; seen=set()
for bname,b in base_options:
  for cname,c in child_options:
    specs+=1
    if len(c):
      bk=set(zip(b.symbol.astype(str), b.entry_date.astype(str)))
      cc=c[~pd.MultiIndex.from_frame(c[['symbol','entry_date']]).isin(pd.MultiIndex.from_tuples(list(bk), names=['symbol','entry_date']))]
    else: cc=c
    combo=pd.concat([b,cc[v236.columns]], ignore_index=True, sort=False).drop_duplicates(['symbol','entry_date'], keep='first')
    key=(bname,cname,len(combo))
    if key in seen: continue
    seen.add(key)
    m=metrics(combo)
    if m['n']<500: continue
    prod=pass_gate(m,PROD); research=pass_gate(m,RESEARCH)
    if prod or research or (m['wr']>=92.5 and m['avg']>=7.35 and m['min_year_n']>=60):
      rec={**m,'base_rule':bname,'child_rule':cname,'base_n':len(b),'child_n':len(cc),'production_pass':prod,'research_pass':research}
      front.append(rec)
      score=(prod, research, m['wr'], m['avg'], m['all_year_wr_min'], m['n'])
      if best_score is None or score>best_score:
        best_score=score; best_rows=combo.copy(); best_rec=rec
front_df=pd.DataFrame(front).sort_values(['production_pass','research_pass','wr','avg','all_year_wr_min','n'], ascending=[False,False,False,False,False,False]) if front else pd.DataFrame()
front_df.to_csv(OUT/'v244_industry_frontier.csv', index=False)
if best_rows is not None:
    best_rows.to_csv(OUT/'v244_best_rows.csv', index=False)
    rows=[]
    for year in ['2023','2026','ALL']:
      d=best_rows if year=='ALL' else best_rows[best_rows.entry_date.astype(str).str.startswith(year)]
      pnl=pd.to_numeric(d.pnl_pct,errors='coerce'); win=d[pnl>0]; loss=d[pnl<=0]
      for f in ['v244_ind_strong1_pct','v244_ind_vs_all_strong1','v244_ind_up1_pct','v244_ind_mean_ret1','v244_ind_median_ret1','v236_br_above_ma20','v236_all_strong1_pct','risk_pct','entry_chase_above_zone_pct','mae_pct','mfe_pct','hold_bars']:
        if f in d.columns:
          rows.append({'year':year,'feature':f,'win_mean':pd.to_numeric(win[f],errors='coerce').mean(),'loss_mean':pd.to_numeric(loss[f],errors='coerce').mean(),'delta_loss_minus_win':pd.to_numeric(loss[f],errors='coerce').mean()-pd.to_numeric(win[f],errors='coerce').mean(),'win_median':pd.to_numeric(win[f],errors='coerce').median(),'loss_median':pd.to_numeric(loss[f],errors='coerce').median()})
    pd.DataFrame(rows).to_csv(OUT/'v244_best_feature_deltas.csv', index=False)
v239_approx=pd.concat([v239_base, child_pool[v236.columns]], ignore_index=True).drop_duplicates(['symbol','entry_date'])
summary={
 'version':'V244_POST_V243_INDUSTRY_PARTICIPATION_PROBE_NO_WRITE',
 'generated_at':datetime.now().isoformat(timespec='seconds'),
 'out_dir':str(OUT),
 'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
 'source_layer':'baostock industry classification + previous-day industry participation from kline cache',
 'rows':{'v236':len(v236),'v230_pool_after_v239_source_spec':len(child_pool)},
 'features':['v244_ind_n','v244_ind_up1_pct','v244_ind_down1_pct','v244_ind_strong1_pct','v244_ind_weak1_pct','v244_ind_mean_ret1','v244_ind_median_ret1','v244_ind_vs_all_strong1'],
 'specs_tested':specs,
 'frontier_rows':int(len(front_df)),
 'production_gate':PROD,'research_gate':RESEARCH,
 'production_pass_count':int(front_df.production_pass.sum()) if len(front_df) else 0,
 'research_pass_count':int(front_df.research_pass.sum()) if len(front_df) else 0,
 'best':best_rec,
 'standing_baselines':{'V236':metrics(v236),'V239_APPROX':metrics(v239_approx)},
 'selector_leak_fields':[],
}
if summary['production_pass_count']>0:
    summary['decision']='V244_INDUSTRY_SOURCE_LAYER_PRODUCTION_GATE_PASS__NEEDS_INDEPENDENT_AUDIT_AND_CURRENT_SMOKE'
elif summary['research_pass_count']>0:
    summary['decision']='V244_INDUSTRY_SOURCE_LAYER_RESEARCH_ONLY__NO_PRODUCTION_PASS'
else:
    summary['decision']='V244_INDUSTRY_SOURCE_LAYER_NO_RESEARCH_PASS__CLOSE_INDUSTRY_DIRECTION'
(OUT/'v244_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
(AUDIT/'v244_post_v243_industry_participation_probe_latest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps(summary, ensure_ascii=False, indent=2))
