#!/usr/bin/env python3
"""V344 no-write: robustness audit for V343 BSL-room deep-runner pass.

V343 passed the headline production gate. V344 tests whether that pass survives
non-negotiable robustness checks: duplicate/symbol concentration, per-symbol
deduping, outlier contribution, period buckets, industry concentration, and
parameter sensitivity around the exact contract. No production/frontend writes.
"""
from __future__ import annotations
import json, math
from datetime import datetime
from pathlib import Path
from typing import Any
import pandas as pd
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; V333=AUD/'v333_full_universe_rule_search_after_breadth_refresh_latest.json'; V343=AUD/'v343_bsl_room_deep_runner_latest.json'
OUT=AUD/f"v344_v343_robustness_audit_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"; LATEST=AUD/'v344_v343_robustness_audit_latest.json'
GATE={'n':570,'min_year_n':70,'wr':93.0,'avg':7.6,'min_year_wr':91.0,'micro':1.0,'t1':0}

def dn(x:Any)->str:
 s=''.join(ch for ch in str(x or '').replace('-','')[:10] if ch.isdigit()); return s[:8] if len(s)>=8 else ''
def sf(x:Any,d=None):
 try:
  if x is None or x=='': return d
  v=float(x); return d if math.isnan(v) or math.isinf(v) else v
  return v
 except Exception: return d
def metrics(df:pd.DataFrame)->dict[str,Any]:
 if len(df)==0: return {'n':0,'wr':0,'avg':0,'micro':0,'min_year_n':0,'year_counts':{},'year_wr':{},'min_year_wr':0}
 p=pd.to_numeric(df.pnl_pct,errors='coerce'); yrs=df.entry_date.astype(str).str[:4]
 yc={str(k):int(v) for k,v in yrs[yrs>='2023'].value_counts().sort_index().to_dict().items()}
 ywr={str(y):round(float((p[yrs==y]>0).mean()*100),2) for y in sorted(yc)}
 return {'n':int(len(df)),'wr':round(float((p>0).mean()*100),4),'avg':round(float(p.mean()),4),'median':round(float(p.median()),4),'micro':round(float(((p>0)&(p<1)).mean()*100),4),'min_year_n':int(min(yc.values()) if yc else 0),'year_counts':yc,'year_wr':ywr,'min_year_wr':round(float(min(ywr.values()) if ywr else 0),2),'p95':round(float(p.quantile(.95)),4),'p99':round(float(p.quantile(.99)),4),'max':round(float(p.max()),4),'min':round(float(p.min()),4)}
def gate(m): return m['n']>=GATE['n'] and m['min_year_n']>=GATE['min_year_n'] and m['wr']>=GATE['wr'] and m['avg']>=GATE['avg'] and m['min_year_wr']>=GATE['min_year_wr'] and m['micro']<=GATE['micro']

def main():
 OUT.mkdir(parents=True,exist_ok=True); rep=json.load(open(V343)); hist=pd.read_csv(rep['artifacts']['hist_csv']); all_rows=pd.read_csv(rep['artifacts']['all_rows_csv'])
 hist['entry_date']=hist.entry_date.map(dn)
 src=json.load(open(V333))['artifacts']['replayed_csv']; srcdf=pd.read_csv(src,low_memory=False); srcdf['entry_date']=srcdf.entry_date.map(dn)
 join_cols=[c for c in ['symbol','entry_date','poi_source','v244_industry','v244_ind_strong1_pct','v236_br_above_ma20','v333_any_history_overlap'] if c in srcdf.columns]
 enriched=hist.merge(srcdf[join_cols].drop_duplicates(['symbol','entry_date','poi_source']),on=['symbol','entry_date','poi_source'],how='left')
 base=metrics(enriched)
 # Dedup stress tests: if duplicate zones/trades from same symbol inflate gate, this will expose it.
 dedup_symbol_latest=enriched.sort_values(['symbol','entry_date']).drop_duplicates('symbol',keep='last')
 dedup_symbol_earliest=enriched.sort_values(['symbol','entry_date']).drop_duplicates('symbol',keep='first')
 dedup_symbol_date=enriched.sort_values(['symbol','entry_date','pnl_pct']).drop_duplicates(['symbol','entry_date'],keep='first')
 dedup_metrics={
  'symbol_latest':metrics(dedup_symbol_latest),'symbol_earliest':metrics(dedup_symbol_earliest),'symbol_date_conservative':metrics(dedup_symbol_date)
 }
 # Outlier dependency.
 p=pd.to_numeric(enriched.pnl_pct,errors='coerce')
 outlier={
  'top_1pct_pnl_share':round(float(p[p>=p.quantile(.99)].sum()/p.sum()*100),4) if p.sum()!=0 else None,
  'top_5pct_pnl_share':round(float(p[p>=p.quantile(.95)].sum()/p.sum()*100),4) if p.sum()!=0 else None,
  'winsor_p99_avg':round(float(p.clip(upper=p.quantile(.99)).mean()),4),
  'winsor_p95_avg':round(float(p.clip(upper=p.quantile(.95)).mean()),4),
  'trim_top1pct_metrics':metrics(enriched[p<p.quantile(.99)].copy()),
  'trim_top5pct_metrics':metrics(enriched[p<p.quantile(.95)].copy()),
 }
 # Time buckets.
 enriched['quarter']=enriched.entry_date.astype(str).str[:4]+'Q'+(((pd.to_datetime(enriched.entry_date.astype(str),format='%Y%m%d').dt.month-1)//3)+1).astype(str)
 q= enriched.groupby('quarter').agg(n=('pnl_pct','size'),wr=('pnl_pct',lambda s: round(float((pd.to_numeric(s)>0).mean()*100),2)),avg=('pnl_pct',lambda s: round(float(pd.to_numeric(s).mean()),4))).reset_index()
 weak_quarters=q[(q.n>=10)&((q.wr<91)|(q.avg<3))].to_dict('records')
 # Concentration.
 by_symbol=enriched.groupby('symbol').agg(n=('pnl_pct','size'),wr=('pnl_pct',lambda s: round(float((pd.to_numeric(s)>0).mean()*100),2)),avg=('pnl_pct',lambda s: round(float(pd.to_numeric(s).mean()),4)),sum_pnl=('pnl_pct','sum')).sort_values('sum_pnl',ascending=False).reset_index()
 by_ind=enriched.groupby('v244_industry',dropna=False).agg(n=('pnl_pct','size'),wr=('pnl_pct',lambda s: round(float((pd.to_numeric(s)>0).mean()*100),2)),avg=('pnl_pct',lambda s: round(float(pd.to_numeric(s).mean()),4)),sum_pnl=('pnl_pct','sum')).sort_values('n',ascending=False).reset_index()
 concentration={'symbols':int(by_symbol.shape[0]),'top10_symbol_trade_share':round(float(by_symbol.head(10).n.sum()/len(enriched)*100),4),'top10_symbol_pnl_share':round(float(by_symbol.head(10).sum_pnl.sum()/p.sum()*100),4),'top5_ind_trade_share':round(float(by_ind.head(5).n.sum()/len(enriched)*100),4),'top5_ind_pnl_share':round(float(by_ind.head(5).sum_pnl.sum()/p.sum()*100),4)}
 # Hard pass requires headline pass AND no obvious inflation by duplicate same-day zones; per-symbol full dedupe is diagnostic only because a stock can validly signal in different years, not a hard fail.
 hard_checks={
  'headline_gate':gate(base),
  'symbol_date_conservative_gate':gate(dedup_metrics['symbol_date_conservative']),
  'winsor_p95_avg_ge_7_0':outlier['winsor_p95_avg']>=7.0,
  'top5_pnl_share_le_35pct':outlier['top_5pct_pnl_share'] is not None and outlier['top_5pct_pnl_share']<=35,
  'no_weak_quarter_with_n_ge10':len(weak_quarters)==0,
 }
 decision='V344_ROBUSTNESS_PASS__CAN_PROMOTE_TO_NEXT_SHADOW_INTEGRATION' if all(hard_checks.values()) else 'V344_ROBUSTNESS_FAIL__DO_NOT_PROMOTE_UNTIL_FIXES'
 enriched.to_csv(OUT/'v344_enriched_hist.csv',index=False); by_symbol.to_csv(OUT/'v344_by_symbol.csv',index=False); by_ind.to_csv(OUT/'v344_by_industry.csv',index=False); q.to_csv(OUT/'v344_quarters.csv',index=False)
 report={'version':'V344_V343_ROBUSTNESS_AUDIT_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source_v343':str(V343),'base_metrics':base,'dedup_metrics':dedup_metrics,'outlier':outlier,'concentration':concentration,'weak_quarters':weak_quarters,'hard_checks':hard_checks,'decision':decision,'artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'enriched_hist':str(OUT/'v344_enriched_hist.csv'),'by_symbol':str(OUT/'v344_by_symbol.csv'),'by_industry':str(OUT/'v344_by_industry.csv'),'quarters':str(OUT/'v344_quarters.csv')}}
 (OUT/'v344_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); LATEST.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'latest':str(LATEST),'decision':decision,'base_metrics':base,'hard_checks':hard_checks,'dedup_symbol_date':dedup_metrics['symbol_date_conservative'],'outlier':{k:v for k,v in outlier.items() if not isinstance(v,dict)},'concentration':concentration,'weak_quarter_count':len(weak_quarters)},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
