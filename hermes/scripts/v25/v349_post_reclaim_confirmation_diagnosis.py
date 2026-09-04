#!/usr/bin/env python3
"""V349 no-write: causal V348 post-reclaim confirmation diagnosis.
Tests confirmation mechanics, not TP/SL changes or production promotion.
"""
from __future__ import annotations
import itertools,json,math
from datetime import datetime
from pathlib import Path
import pandas as pd

ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; KDIR=ROOT/'kline_cache'
SRC=AUD/'v348_causal_sequence_latest.json'; OUT=AUD/f"v349_confirmation_mechanism_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"; LATEST=AUD/'v349_confirmation_mechanism_latest.json'
GATE={'n':570,'min_year_n':70,'wr':93.0,'avg':7.6,'min_year_wr':91.0,'micro':1.0,'top5_share':35.0,'weak_quarters':0}
def ds(x):return ''.join(c for c in str(x or '') if c.isdigit())[:8]
def f(x,d=0.):
 try:return float(x)
 except:return d
def load(p):
 try:return json.loads(Path(p).read_text())
 except:return []
def bars(sym):
 out=[]
 for b in load(KDIR/f"{sym.replace('.','_')}_daily_750.json"):
  d=ds(b.get('t') or b.get('date'))
  if d:out.append((d,f(b.get('o')),f(b.get('h')),f(b.get('l')),f(b.get('c'))))
 return sorted(out)
def met(x):
 if x.empty:return {'n':0,'wr':0,'avg':0,'micro':0,'min_year_n':0,'min_year_wr':0,'top5_share':999,'weak_q':99}
 p=x.pnl; ys=x.groupby('year').pnl.agg(n='size',wr=lambda q:(q>0).mean()*100); qs=x.groupby('quarter').pnl.agg(n='size',wr=lambda q:(q>0).mean()*100,avg='mean'); q=p.quantile(.95,interpolation='lower'); share=p[p>=q].sum()/p.sum()*100 if p.sum()>0 else 999
 return {'n':len(x),'wr':(p>0).mean()*100,'avg':p.mean(),'micro':((p>0)&(p<1)).mean()*100,'min_year_n':int(ys.n.min()),'min_year_wr':ys.wr.min(),'top5_share':share,'weak_q':len(qs[(qs.n>=10)&((qs.wr<91)|(qs.avg<3))])}
def ok(m):return m['n']>=570 and m['min_year_n']>=70 and m['wr']>=93 and m['avg']>=7.6 and m['min_year_wr']>=91 and m['micro']<=1 and m['top5_share']<=35 and m['weak_q']==0
def main():
 OUT.mkdir(parents=True,exist_ok=True); rep=load(SRC); d=pd.read_csv(rep['artifacts']['trades']); cache={}; feats=[]
 for r in d.itertuples(index=False):
  if r.symbol not in cache:cache[r.symbol]=bars(r.symbol)
  m={x[0]:x for x in cache[r.symbol]}; rb=m.get(ds(r.reclaim_date)); tb=m.get(ds(r.takeover_date)); eb=m.get(ds(r.entry_date))
  if not rb or not tb or not eb:continue
  rng=max(tb[2]-tb[3],1e-9); body=(tb[4]-tb[1])/rng; closepos=(tb[4]-tb[3])/rng
  feats.append({**r._asdict(),'risk_pct':(f(r.entry_price)/f(r.zone_low)-1)*100,'zone_width_pct':(f(r.zone_high)/f(r.zone_low)-1)*100,'takeover_body_pct':body*100,'takeover_close_pos_pct':closepos*100,'takeover_low_above_zone_high':tb[3]>=f(r.zone_high),'reclaim_body_pct':(rb[4]-rb[1])/max(rb[2]-rb[3],1e-9)*100,'entry_gap_pct':(eb[1]/f(r.zone_high)-1)*100})
 fdf=pd.DataFrame(feats); fdf['year']=fdf.entry_date.astype(str).str[:4]; fdf['quarter']=pd.to_datetime(fdf.entry_date.astype(str),format='%Y%m%d').dt.to_period('Q').astype(str); fdf['pnl']=pd.to_numeric(fdf.pnl)
 base=fdf.event_type.eq('BOS_CONTINUATION')&fdf.market_state.eq('BULL_CONTINUATION')
 rules=[]
 for body,cp,low,risk,width,gap in itertools.product([0,20,40,55,70],[0,50,65,80],[False,True],[99,3,4,5],[99,1.5,2.5,4],[5,3,1]):
  mask=base&(fdf.takeover_body_pct>=body)&(fdf.takeover_close_pos_pct>=cp)&(fdf.risk_pct<=risk)&(fdf.zone_width_pct<=width)&(fdf.entry_gap_pct<=gap)
  if low:mask&=fdf.takeover_low_above_zone_high
  x=fdf[mask]; full=met(x); train=met(x[x.year.isin(['2023','2024'])]); test=met(x[x.year.isin(['2025','2026'])]);
  rules.append({'rule':f'BOS+BULL|body>={body}|closepos>={cp}|low>zh={low}|risk<={risk}|width<={width}|gap<={gap}','full':full,'train':train,'oos':test,'pass':ok(full) and train['n']>=140 and train['wr']>=91 and test['wr']>=91 and test['avg']>=3})
 rules.sort(key=lambda r:(r['pass'],r['oos']['wr'],r['oos']['avg'],r['full']['n']),reverse=True); out=[]
 for r in rules[:500]:out.append({'rule':r['rule'],'pass':r['pass'],**{f'full_{k}':v for k,v in r['full'].items()},**{f'oos_{k}':v for k,v in r['oos'].items()}})
 pd.DataFrame(out).to_csv(OUT/'v349_confirmation_frontier_top500.csv',index=False); fdf.to_csv(OUT/'v349_causal_trade_features.csv',index=False)
 report={'version':'V349_CAUSAL_CONFIRMATION_MECHANISM_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'input':rep['artifacts']['trades'],'base_bos_bull':met(fdf[base]),'features':len(fdf),'rules':len(rules),'passing':sum(r['pass'] for r in rules),'top_rules':rules[:20],'decision':'V349_POST_RECLAIM_CONFIRMATION_PASS__SHADOW_ONLY' if any(r['pass'] for r in rules) else 'V349_POST_RECLAIM_CONFIRMATION_FAIL__EVENT_DEFINITION_NOT_FILTERING','artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'frontier':str(OUT/'v349_confirmation_frontier_top500.csv'),'features':str(OUT/'v349_causal_trade_features.csv')}}
 text=json.dumps(report,ensure_ascii=False,indent=2,default=lambda x:x.item() if hasattr(x,'item') else str(x));(OUT/'v349_report.json').write_text(text);LATEST.write_text(text);print(json.dumps({'decision':report['decision'],'features':len(fdf),'rules':len(rules),'passing':report['passing'],'base':report['base_bos_bull'],'top':rules[:3],'artifacts':report['artifacts']},ensure_ascii=False,indent=2,default=str))
if __name__=='__main__':main()
