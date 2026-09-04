#!/usr/bin/env python3
from __future__ import annotations
import json, math
from pathlib import Path
from datetime import datetime
import pandas as pd
BASE=Path('/root/.hermes'); AUDIT=BASE/'smc_audit'
SRC=AUDIT/'v244_post_v243_industry_participation_probe_no_write_20260701_151619/v244_best_rows.csv'
OUT=AUDIT/('v245_source_field_separator_probe_no_write_'+datetime.now().strftime('%Y%m%d_%H%M%S')); OUT.mkdir(parents=True,exist_ok=True)
PROD={'n':570,'min_year_n':70,'wr':93.0,'avg':7.6,'all_year_wr_min':91.0,'micro':1.0}
RESEARCH={'n':550,'min_year_n':65,'wr':92.8,'avg':7.45,'all_year_wr_min':90.0,'micro':1.0}
BAD_TOKENS=['pnl','exit_','won','mae','mfe','hold_bars','rr_realized','base_','v211_pnl','hit_']

def dn(x):
 s=''.join(ch for ch in str(x or '').replace('-','')[:10] if ch.isdigit()); return s[:8] if len(s)>=8 else ''
def metrics(df):
 if len(df)==0: return dict(n=0,wr=0,avg=0,median=0,min_year_n=0,year_counts={},year_wr={},all_year_wr_min=0,micro_profit_pct=0,loss_n=0,t1=0)
 pnl=pd.to_numeric(df.pnl_pct,errors='coerce'); years=df.entry_date.astype(str).str[:4]; yc=years.value_counts().sort_index().to_dict(); ywr={str(y):round(float((pnl[years==y]>0).mean()*100),2) for y in sorted(years.unique())}
 t1=int(((df.exit_date.map(dn)==df.entry_date.map(dn)) & df.exit_date.map(dn).ne('')).sum()) if 'exit_date' in df else 0
 return dict(n=int(len(df)),wr=round(float((pnl>0).mean()*100),4),avg=round(float(pnl.mean()),4),median=round(float(pnl.median()),4),min_year_n=int(min(yc.values()) if yc else 0),year_counts={str(k):int(v) for k,v in yc.items()},year_wr=ywr,all_year_wr_min=round(float(min(ywr.values()) if ywr else 0),2),micro_profit_pct=round(float(((pnl>0)&(pnl<1)).mean()*100),4),loss_n=int((pnl<=0).sum()),t1=t1)
def ok(m,g): return m['n']>=g['n'] and m['min_year_n']>=g['min_year_n'] and m['wr']>=g['wr'] and m['avg']>=g['avg'] and m['all_year_wr_min']>=g['all_year_wr_min'] and m['micro_profit_pct']<=g['micro'] and m['t1']==0

df=pd.read_csv(SRC,low_memory=False); df.entry_date=df.entry_date.map(dn); df.exit_date=df.exit_date.map(dn)
base_m=metrics(df)
num_candidates=[]
allow_prefix=('v132_','v236_','v244_')
allow_exact={'risk_pct','entry_chase_above_zone_pct','reclaim_close_pos','reclaim_close_above_zone_pct','touch_to_reclaim_bars','source_gap_atr','source_mid_body_atr'}
for c in df.columns:
    lc=c.lower()
    if any(tok in lc for tok in BAD_TOKENS): continue
    if c.startswith(allow_prefix) or c in allow_exact:
        s=pd.to_numeric(df[c],errors='coerce')
        if s.notna().sum()>=500 and s.nunique(dropna=True)>=8:
            num_candidates.append(c)
front=[]; best=None; best_rows=None; best_score=None; tested=0
# single filters <=/>= quantiles, keep enough width
for c in num_candidates:
    s=pd.to_numeric(df[c],errors='coerce')
    qs=sorted(set(float(x) for x in s.quantile([.05,.1,.15,.2,.25,.3,.35,.4,.45,.5,.55,.6,.65,.7,.75,.8,.85,.9,.95]).dropna()))
    for q in qs:
        for op in ['<=','>=']:
            tested+=1
            sub=df[s<=q] if op=='<=' else df[s>=q]
            if len(sub)<500: continue
            m=metrics(sub); prod=ok(m,PROD); research=ok(m,RESEARCH)
            if prod or research or (m['wr']>=93 and m['avg']>=7.45 and m['all_year_wr_min']>=89.5 and m['min_year_n']>=65):
                rec={**m,'rule':f'{c}{op}{q:.6g}','production_pass':prod,'research_pass':research}
                front.append(rec); score=(prod,research,m['wr'],m['avg'],m['all_year_wr_min'],m['n'])
                if best_score is None or score>best_score: best_score=score; best=rec; best_rows=sub.copy()
# categorical exclusions/inclusions for current-compatible source fields
cat_cols=[c for c in ['market_state','poi_source','event_type','source_engine','classical_structure_status','m60_state','weekly_trend_state','v132_reclaim_class','v228_source_bucket','v244_industry'] if c in df.columns]
for c in cat_cols:
    vals=df[c].astype(str).value_counts().index[:20]
    for v in vals:
        for mode in ['==','!=']:
            tested+=1
            sub=df[df[c].astype(str).eq(v)] if mode=='==' else df[~df[c].astype(str).eq(v)]
            if len(sub)<500: continue
            m=metrics(sub); prod=ok(m,PROD); research=ok(m,RESEARCH)
            if prod or research or (m['wr']>=93 and m['avg']>=7.45 and m['all_year_wr_min']>=89.5 and m['min_year_n']>=65):
                rec={**m,'rule':f'{c}{mode}{v}','production_pass':prod,'research_pass':research}
                front.append(rec); score=(prod,research,m['wr'],m['avg'],m['all_year_wr_min'],m['n'])
                if best_score is None or score>best_score: best_score=score; best=rec; best_rows=sub.copy()
front_df=pd.DataFrame(front).sort_values(['production_pass','research_pass','wr','avg','all_year_wr_min','n'],ascending=[False,False,False,False,False,False]) if front else pd.DataFrame()
front_df.to_csv(OUT/'v245_source_field_frontier.csv',index=False)
if best_rows is not None: best_rows.to_csv(OUT/'v245_best_rows.csv',index=False)
summary={'version':'V245_SOURCE_FIELD_SEPARATOR_PROBE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'out_dir':str(OUT),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source_rows':str(SRC),'baseline':base_m,'numeric_fields_tested':len(num_candidates),'categorical_fields_tested':cat_cols,'specs_tested':tested,'frontier_rows':int(len(front_df)),'production_gate':PROD,'research_gate':RESEARCH,'production_pass_count':int(front_df.production_pass.sum()) if len(front_df) else 0,'research_pass_count':int(front_df.research_pass.sum()) if len(front_df) else 0,'best':best,'selector_leak_fields':[]}
if summary['production_pass_count']>0: summary['decision']='V245_SOURCE_FIELD_PRODUCTION_PASS__NEEDS_INDEPENDENT_AUDIT_CURRENT_SMOKE'
elif summary['research_pass_count']>0: summary['decision']='V245_SOURCE_FIELD_RESEARCH_ONLY__NO_PRODUCTION_PASS'
else: summary['decision']='V245_SOURCE_FIELD_NO_GATE_PASS__CLOSE_SCANNER_FIELD_SEPARATOR_DIRECTION'
(OUT/'v245_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)); (AUDIT/'v245_source_field_separator_probe_latest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False,indent=2))
