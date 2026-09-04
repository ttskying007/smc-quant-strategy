#!/usr/bin/env python3
from __future__ import annotations
import itertools, json
from datetime import datetime
from pathlib import Path
from typing import Any
import pandas as pd
ROOT=Path('/root/.hermes')
SRC=ROOT/'smc_audit'/'v154_cancel_addback_no_micro_20260622'/'v154_chosen_rows.csv'
OUT=ROOT/'smc_audit'/'v160_v158_robust_monthly_rule_search_20260622'
OUT.mkdir(parents=True, exist_ok=True)

def bool_s(s): return s.astype(str).str.strip().str.lower().isin({'true','1','yes'})
def num_s(s, default=0.0): return pd.to_numeric(s, errors='coerce').fillna(default)
def date_key(v): return str(v or '').replace('-','')[:8]
def add_time(df):
    df=df.copy(); df['entry_date_key']=df['v154_entry_date'].map(date_key); df['entry_year']=df.entry_date_key.str[:4]; df['entry_month']=df.entry_date_key.str[:6]; return df
def metrics(df):
    n=len(df)
    if n==0: return dict(n=0,wr=0.0,avg=0.0,median=0.0,loss=0.0,min_year_n=0,year_counts={},year_wr={},t1=0)
    pnl=num_s(df['v154_pnl_pct']); years=df.entry_year.astype(str)
    yc={str(k):int(v) for k,v in years.value_counts().sort_index().items()}
    yw={}
    for y in sorted(yc):
        yp=pnl[years.eq(y)]; yw[y]=round(float((yp>0).mean()*100),2)
    return dict(n=int(n),wr=round(float((pnl>0).mean()*100),2),avg=round(float(pnl.mean()),4),median=round(float(pnl.median()),4),loss=round(float((pnl<=0).mean()*100),2),min_year_n=int(min(yc.values())) if yc else 0,year_counts=yc,year_wr=yw,t1=int(bool_s(df.get('v154_t1_violation', pd.Series(False,index=df.index))).sum()))
def release(m): return m['n']>=200 and m['wr']>=82 and m['avg']>=3 and m['min_year_n']>=35 and float(m['year_wr'].get('2024',0))>=78 and m['t1']==0
def monthly_bad(df):
    rows=[]
    for mon,g in df.groupby('entry_month'):
        m=metrics(g); rows.append({'entry_month':mon, **m, 'bad60': m['n']>=3 and m['wr']<60, 'weak78': m['n']>=3 and m['wr']<78})
    md=pd.DataFrame(rows).sort_values('entry_month') if rows else pd.DataFrame()
    return md, int(md.bad60.sum()) if not md.empty else 0, int(md.weak78.sum()) if not md.empty else 0
def rolling_bad(df, window=30):
    o=df.sort_values(['entry_date_key','symbol']).reset_index(drop=True)
    rows=[]
    for i in range(max(0,len(o)-window+1)):
        g=o.iloc[i:i+window]; m=metrics(g); rows.append({'start_rank':i+1,'end_rank':i+window,'start_date':g.entry_date_key.iloc[0],'end_date':g.entry_date_key.iloc[-1],**m,'bad70':m['wr']<70})
    rd=pd.DataFrame(rows)
    return rd, int(rd.bad70.sum()) if not rd.empty else 0

df=add_time(pd.read_csv(SRC, low_memory=False))
strict3=bool_s(df['v132_true_takeover_3_strict']); nonstrict=~strict3
pbg=df['v143_lifecycle_status'].astype(str).eq('PRE_BUY_GAP_NOTE_ONLY')
prebuy=bool_s(df['v141_pre_buy_cancel_available'])
chase=num_s(df['entry_chase_above_zone_pct']); body=num_s(df['v132_reclaim_bull_body_pct'])
above=num_s(df['reclaim_close_above_zone_pct']); pos=num_s(df['reclaim_close_pos'])
risk=num_s(df['risk_pct']); gap=num_s(df['source_gap_atr']); mid=num_s(df['source_mid_body_atr'])
# candidate predicates: all non-leak/pre-entry or reclaim-confirm fields already persisted by research generator.
preds={
 'TT2_CONFIRM_OR_CHASE_LE_3': strict3|chase.le(3.0),
 'TT2_CONFIRM_OR_CHASE_LE_3_5': strict3|chase.le(3.5),
 'NONSTRICT_BODY_LE_86_6': (~nonstrict)|body.le(86.6124),
 'NONSTRICT_BODY_LE_80': (~nonstrict)|body.le(80),
 'PBG_RECLAIM_ABOVE_GE_1_3': (~pbg)|above.ge(1.3),
 'PBG_RECLAIM_POS_GE_75': (~pbg)|pos.ge(0.75),
 'PBG_CHASE_LE_3_5': (~pbg)|chase.le(3.5),
 'RISK_LE_7_5': risk.le(7.5),
 'RISK_LE_7': risk.le(7.0),
 'SOURCE_GAP_LE_1_316': gap.le(1.316),
 'MID_BODY_LE_2_577': mid.le(2.5767),
 'PREBUY_GAP_WATCH_ONLY_ALL': ~prebuy,
}
rows=[]
keys=list(preds)
for r in range(1,5):
  for combo in itertools.combinations(keys,r):
    mask=pd.Series(True,index=df.index)
    for k in combo: mask &= preds[k]
    g=df[mask].copy()
    if len(g)<180: continue
    m=metrics(g); md,bad60,weak78=monthly_bad(g); rd,rbad=rolling_bad(g)
    rows.append({'rule': '+'.join(combo), **m, 'release_pass':release(m), 'bad_months_wr_lt60_n_ge3':bad60, 'weak_months_wr_lt78_n_ge3':weak78, 'rolling30_wr_lt70_count':rbad, 'robust_pass': release(m) and bad60==0 and rbad==0})
res=pd.DataFrame(rows).sort_values(['robust_pass','release_pass','bad_months_wr_lt60_n_ge3','rolling30_wr_lt70_count','n','wr','avg'], ascending=[False,False,True,True,False,False,False])
res.to_csv(OUT/'v160_rule_search.csv', index=False)
# materialize top robust or best fallback
best=res.head(1).iloc[0].to_dict() if len(res) else {}
chosen_rule=best.get('rule','')
mask=pd.Series(True,index=df.index)
for k in chosen_rule.split('+') if chosen_rule else []: mask &= preds[k]
chosen=df[mask].copy(); rejected=df[~mask].copy()
chosen.to_csv(OUT/'v160_chosen_rows.csv', index=False); rejected.to_csv(OUT/'v160_rejected_rows.csv', index=False)
md,bad60,weak78=monthly_bad(chosen); rd,rbad=rolling_bad(chosen)
md.to_csv(OUT/'v160_monthly_metrics.csv', index=False); rd.to_csv(OUT/'v160_rolling_30_trade_metrics.csv', index=False)
summary={'decision':'V160_ROBUST_RULE_FOUND_RESEARCH_ONLY_NO_PRODUCTION_WRITE' if best.get('robust_pass') else 'V160_NO_ROBUST_RULE_KEEP_V158_RESEARCH_ONLY','generated_at':datetime.now().isoformat(timespec='seconds'),'production_write':False,'source':str(SRC),'out':str(OUT),'best_rule':best,'best_metrics':metrics(chosen),'bad_months_wr_lt60_n_ge3':bad60,'weak_months_wr_lt78_n_ge3':weak78,'rolling30_wr_lt70_count':rbad,'top_rules':res.head(20).to_dict(orient='records')}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
report=['# V160 Robust monthly rule search','',f"Decision: `{summary['decision']}`。只读研究；未写生产/前端/watchlist。",'', '## Best rule', pd.DataFrame([best]).to_markdown(index=False) if best else 'None','', '## Best metrics', pd.DataFrame([summary['best_metrics']]).to_markdown(index=False),'','## Worst months for best', md[md.n.ge(3)].sort_values(['wr','avg']).head(12).to_markdown(index=False),'','## Worst rolling windows for best', rd.sort_values(['wr','avg']).head(12).to_markdown(index=False) if not rd.empty else 'None','','## Top rule search rows', res.head(20).to_markdown(index=False)]
(OUT/'report.md').write_text('\n'.join(report), encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2,default=str))
