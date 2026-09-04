#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
import pandas as pd
BASE=Path('/root/.hermes'); AUDIT=BASE/'smc_audit'
SRC=AUDIT/'v244_post_v243_industry_participation_probe_no_write_20260701_151619/v244_best_rows.csv'
OUT=AUDIT/('v246_industry_addback_candidate_no_write_'+datetime.now().strftime('%Y%m%d_%H%M%S')); OUT.mkdir(parents=True,exist_ok=True)
BAD=['pnl','exit_','won','mae','mfe','hold_bars','rr_realized','base_','v211_pnl','hit_']
def dn(x):
 s=''.join(ch for ch in str(x or '').replace('-','')[:10] if ch.isdigit()); return s[:8] if len(s)>=8 else ''
def metrics(df):
 p=pd.to_numeric(df.pnl_pct,errors='coerce'); yrs=df.entry_date.astype(str).str[:4]
 yc=yrs.value_counts().sort_index().to_dict(); ywr={str(y):round(float((p[yrs==y]>0).mean()*100),2) for y in sorted(yrs.unique())}
 t1=int(((df.exit_date.map(dn)==df.entry_date.map(dn)) & df.exit_date.map(dn).ne('')).sum()) if 'exit_date' in df else 0
 return {'n':int(len(df)),'wr':round(float((p>0).mean()*100),4),'avg':round(float(p.mean()),4),'median':round(float(p.median()),4),'min_year_n':int(min(yc.values())),'year_counts':{str(k):int(v) for k,v in yc.items()},'year_wr':ywr,'all_year_wr_min':round(float(min(ywr.values())),2),'micro_profit_pct':round(float(((p>0)&(p<1)).mean()*100),4),'loss_n':int((p<=0).sum()),'t1':t1}
def pass_gate(m,g): return m['n']>=g['n'] and m['min_year_n']>=g['min_year_n'] and m['wr']>=g['wr'] and m['avg']>=g['avg'] and m['all_year_wr_min']>=g['all_year_wr_min'] and m['micro_profit_pct']<=g['micro'] and m['t1']==0

df=pd.read_csv(SRC,low_memory=False); df.entry_date=df.entry_date.map(dn); df.exit_date=df.exit_date.map(dn)
ind=df.v244_industry.astype(str)
weak=ind.isin(['C27医药制造业','C32有色金属冶炼和压延加工业'])
addback=(pd.to_numeric(df.v244_ind_strong1_pct,errors='coerce')>=31.1688) | (pd.to_numeric(df.v236_br_above_ma20,errors='coerce')>=46.8561)
selected=df[(~weak) | (weak & addback)].copy()
excluded=df[~((~weak) | (weak & addback))].copy()
selected.to_csv(OUT/'v246_selected_rows.csv',index=False); excluded.to_csv(OUT/'v246_excluded_rows.csv',index=False)
# group diagnostics
rows=[]
for name,d in [('selected',selected),('excluded',excluded),('source_v244_best',df),('weak_industry_all',df[weak]),('weak_addback',df[weak & addback]),('weak_excluded',df[weak & ~addback])]:
 if len(d): rows.append({'bucket':name,**metrics(d)})
pd.DataFrame(rows).to_csv(OUT/'v246_bucket_metrics.csv',index=False)
PROD={'n':570,'min_year_n':70,'wr':93.0,'avg':7.6,'all_year_wr_min':91.0,'micro':1.0}
selector_fields=['v244_industry','v244_ind_strong1_pct','v236_br_above_ma20']
leak=[f for f in selector_fields if any(tok in f.lower() for tok in BAD)]
summary={'version':'V246_INDUSTRY_ADDBACK_CANDIDATE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'out_dir':str(OUT),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source_rows':str(SRC),'rule':'Keep V244 best rows except weak industries C27/C32; add weak-industry rows back only when previous-day industry strong1 >=31.1688 OR previous-day broad br_above_ma20 >=46.8561','selector_fields':selector_fields,'selector_leak_fields':leak,'baseline_v244_best':metrics(df),'selected':metrics(selected),'excluded':metrics(excluded),'bucket_metrics_csv':str(OUT/'v246_bucket_metrics.csv'),'production_gate':PROD,'production_pass':pass_gate(metrics(selected),PROD)}
summary['decision']='V246_HISTORICAL_PRODUCTION_GATE_PASS__NO_WRITE__NEEDS_INDEPENDENT_AUDIT_AND_CURRENT_SCANNER_SMOKE' if summary['production_pass'] and not leak else 'V246_FAIL'
(OUT/'v246_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)); (AUDIT/'v246_industry_addback_candidate_latest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False,indent=2))
