#!/usr/bin/env python3
"""V348 no-write causal SMC sequence rebuild audit.

Causal contract: context -> event -> pre-event OB -> later touch -> later reclaim
-> later takeover -> next-open entry.  All POI/target inputs are known before entry.
No production, frontend, or watchlist writes.
"""
from __future__ import annotations
import json, math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
import pandas as pd

ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
ENV=ROOT/'smc_opt_v74_env_state_machine'/'v74_env_by_date.json'
OUT=AUD/f"v348_causal_sequence_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
LATEST=AUD/'v348_causal_sequence_latest.json'
GATE={'n':570,'min_year_n':70,'wr':93.0,'avg':7.6,'min_year_wr':91.0,'micro':1.0,'top5_share':35.0,'weak_quarters':0}


def f(x:Any,d:float=0.0)->float:
 try:
  v=float(x); return d if math.isnan(v) or math.isinf(v) else v
 except Exception:return d

def ds(x:Any)->str:
 return ''.join(c for c in str(x or '') if c.isdigit())[:8]

def bv(b:dict,k:str)->float:return f(b.get(k))
def date(b:dict)->str:return ds(b.get('t') or b.get('date'))
def bars(path:Path)->list[dict]:
 try: raw=json.loads(path.read_text())
 except Exception:return []
 out=[]
 for x in raw:
  if date(x) and all(bv(x,k)>0 for k in ('o','h','l','c')):out.append(x)
 return sorted(out,key=date)
def symbol(path:Path)->str:
 a=path.name.replace('_daily_750.json','').split('_');return f'{a[0]}.{a[1]}' if len(a)==2 else path.stem

def trend(ks:list[dict],i:int)->str:
 w=ks[i-5:i]
 if len(w)<5:return 'RANGE'
 hs=[bv(x,'h') for x in w]; ls=[bv(x,'l') for x in w]; cs=[bv(x,'c') for x in w]
 if hs[-1]>hs[0] and ls[-1]>ls[0] and cs[-1]>cs[0]:return 'UP'
 if hs[-1]<hs[0] and ls[-1]<ls[0]:return 'DOWN'
 return 'RANGE'
def last_bearish(ks:list[dict],i:int)->int|None:
 for j in range(i-1,max(-1,i-9),-1):
  if bv(ks[j],'c')<=bv(ks[j],'o'):return j
 return None
def ssl_sweep(ks:list[dict],i:int)->int|None:
 for j in range(max(8,i-5),i):
  prev=min(bv(x,'l') for x in ks[j-8:j])
  if bv(ks[j],'l')<prev and bv(ks[j],'c')>prev:return j
 return None
def event(ks:list[dict],i:int,state:str)->dict|None:
 prior_hi=max(bv(x,'h') for x in ks[i-5:i]); b=ks[i]
 bull=bv(b,'c')>prior_hi and bv(b,'c')>bv(b,'o')
 if not bull:return None
 tr=trend(ks,i); sw=ssl_sweep(ks,i)
 if tr=='UP' and state in {'BULL_CONTINUATION','RECOVERY','ACCUMULATION'}:
  return {'type':'BOS_CONTINUATION','sweep_idx':None,'trend':tr,'break_level':prior_hi}
 if sw is not None and tr in {'DOWN','RANGE'} and state in {'BEAR_RISK','DISTRIBUTION','MIXED','ACCUMULATION','RECOVERY'}:
  return {'type':'SSL_SWEEP_CHOCH_REVERSAL','sweep_idx':sw,'trend':tr,'break_level':prior_hi}
 return None
def poi(ks:list[dict],i:int,ev:dict)->dict|None:
 j=last_bearish(ks,i)
 if j is None:return None
 b=ks[j]; zl=min(bv(b,'l'),bv(b,'o'),bv(b,'c')); zh=max(bv(b,'o'),bv(b,'c'))
 start=ev['sweep_idx'] if ev['sweep_idx'] is not None else max(0,i-8)
 low=min(bv(x,'l') for x in ks[start:i+1]); high=max(bv(x,'h') for x in ks[start:i+1])
 if high<=low or zh>low+(high-low)*.79:return None
 # Only historic highs known at event time and above the prospective zone are valid targets.
 known=[bv(x,'h') for x in ks[max(0,i-60):i] if bv(x,'h')>zh]
 return {'idx':j,'low':zl,'high':zh,'target':min(known) if known else 0.0}
def entry(ks:list[dict],i:int,p:dict)->dict|None:
 touch=None; reclaim=None
 for j in range(i+1,min(len(ks)-2,i+13)):
  b=ks[j]; lo,hi,cl=bv(b,'l'),bv(b,'h'),bv(b,'c')
  if touch is None and lo<=p['high'] and hi>=p['low']:
   touch=j
   if cl<p['low']:return None
   continue
  if touch is None:continue
  if cl<p['low']:return None
  if reclaim is None and j>touch and cl>p['high']:
   reclaim=j;continue
  if reclaim is not None and j>reclaim and cl>p['high'] and lo>=p['low']:
   ei=j+1; ep=bv(ks[ei],'o')
   if ep<=0 or ep>p['high']*1.05:return None
 # The target is selected at entry time from confirmed (two bars on each side)
   # buy-side swing highs; it never reads post-entry candles.
   pivots=[bv(ks[k],'h') for k in range(2,ei-2) if bv(ks[k],'h')>=max(bv(x,'h') for x in ks[k-2:k]) and bv(ks[k],'h')>max(bv(x,'h') for x in ks[k+1:k+3])]
   targets=[x for x in pivots if x>ep*1.04]
   return {'touch':touch,'reclaim':reclaim,'takeover':j,'idx':ei,'price':ep,'target':min(targets) if targets else 0.0}
 return None
def replay(ks:list[dict],e:dict,p:dict)->tuple[float,str,int,int]:
 ep=e['price']; sl=p['low']*.99; target=e['target']; got=False; pnl1=0.0
 # A target must have enough ex-ante room to clear the first structural objective.
 if target<=ep*1.04:return float('nan'),'NO_TARGET_SPACE',0,0
 for n,j in enumerate(range(e['idx']+1,min(len(ks),e['idx']+51)),1):
  b=ks[j]; hi,lo,cl=bv(b,'h'),bv(b,'l'),bv(b,'c')
  if not got:
   if lo<=sl:return (sl/ep-1)*100,'SL',n,j
   if hi>=ep*1.04:
    got=True;pnl1=1.2
    if lo<=ep:return pnl1,'SAME_BAR_BE',n,j
   elif n>=50:return (cl/ep-1)*100,'TIME_PRE_TP1',n,j
  else:
   if lo<=ep:return pnl1,'BE',n,j
   if hi>=target:return pnl1+(target/ep-1)*100*.7,'KNOWN_BSL_TARGET',n,j
   if n>=50:return pnl1+(cl/ep-1)*100*.7,'TIME_RUNNER',n,j
 return float('nan'),'OPEN',0,0

def metrics(df:pd.DataFrame)->dict:
 if df.empty:return {'n':0,'wr':0,'avg':0,'micro':0,'min_year_n':0,'min_year_wr':0,'top5_share':999,'weak_quarter_count':99,'exit_counts':{}}
 p=df.pnl.astype(float); ys=df.groupby('year').pnl.agg(n='size',wr=lambda x:(x>0).mean()*100); qs=df.groupby('quarter').pnl.agg(n='size',wr=lambda x:(x>0).mean()*100,avg='mean')
 weak=qs[(qs.n>=10)&((qs.wr<91)|(qs.avg<3))]; q=p.quantile(.95,interpolation='lower'); share=p[p>=q].sum()/p.sum()*100 if p.sum()>0 else 999
 return {'n':len(df),'wr':(p>0).mean()*100,'avg':p.mean(),'micro':((p>0)&(p<1)).mean()*100,'min_year_n':int(ys.n.min()),'min_year_wr':ys.wr.min(),'top5_share':share,'weak_quarter_count':len(weak),'weak_quarters':qs.reset_index().to_dict('records'),'exit_counts':df.reason.value_counts().to_dict()}
def passed(m:dict)->bool:return all([m['n']>=GATE['n'],m['min_year_n']>=GATE['min_year_n'],m['wr']>=GATE['wr'],m['avg']>=GATE['avg'],m['min_year_wr']>=GATE['min_year_wr'],m['micro']<=GATE['micro'],m['top5_share']<=GATE['top5_share'],m['weak_quarter_count']==0])
def main():
 OUT.mkdir(parents=True,exist_ok=True); env=json.loads(ENV.read_text()); rows=[]; sequence_rows=[]; counts=Counter(); bad=[]
 for path in sorted(KDIR.glob('*_daily_750.json')):
  ks=bars(path); sym=symbol(path)
  if len(ks)<100:continue
  for i in range(12,len(ks)-15):
   state=str((env.get(date(ks[i]),{}) or {}).get('market_state_v74') or (env.get(date(ks[i]),{}) or {}).get('market_state') or '')
   ev=event(ks,i,state)
   if not ev:continue
   counts['events']+=1; p=poi(ks,i,ev)
   if not p:counts['no_causal_discount_ob']+=1;continue
   counts['causal_pre_event_poi']+=1;e=entry(ks,i,p)
   if not e:counts['no_later_touch_reclaim_takeover']+=1;continue
   counts['sequence_complete']+=1
   sequence_rows.append({'symbol':sym,'event_type':ev['type'],'market_state':state,'event_date':date(ks[i]),'entry_date':date(ks[e['idx']]),'entry_price':e['price'],'zone_low':p['low'],'zone_high':p['high'],'known_target':e['target'],'target_room_pct':(e['target']/e['price']-1)*100 if e['target'] else None,'has_target_space':bool(e['target']>e['price']*1.04)})
   pnl,reason,hold,xi=replay(ks,e,p)
   if not math.isfinite(pnl):counts[reason]+=1;continue
   ed=date(ks[e['idx']]); xd=date(ks[xi]);
   if xd<=ed:bad.append({'symbol':sym,'entry':ed,'exit':xd});continue
   rows.append({'symbol':sym,'event_type':ev['type'],'market_state':state,'event_date':date(ks[i]),'zone_date':date(ks[p['idx']]),'touch_date':date(ks[e['touch']]),'reclaim_date':date(ks[e['reclaim']]),'takeover_date':date(ks[e['takeover']]),'entry_date':ed,'exit_date':xd,'entry_price':e['price'],'zone_low':p['low'],'zone_high':p['high'],'known_target':e['target'],'pnl':pnl,'reason':reason,'hold_bars':hold,'year':ed[:4],'quarter':str(pd.to_datetime(ed,format='%Y%m%d').to_period('Q'))})
 df=pd.DataFrame(rows); sq=pd.DataFrame(sequence_rows)
 hist=df[df.year.isin(['2023','2024','2025','2026'])].copy() if not df.empty else df
 full=metrics(hist); train=metrics(hist[hist.year.isin(['2023','2024'])]); test=metrics(hist[hist.year.isin(['2025','2026'])])
 target_summary=(sq.groupby(['event_type','market_state'],dropna=False).agg(n=('symbol','size'),target_space=('has_target_space','mean'),room_median=('target_room_pct','median'),room_p90=('target_room_pct',lambda x:x.quantile(.9))).reset_index().to_dict('records') if not sq.empty else [])
 if not hist.empty:hist.to_csv(OUT/'v348_causal_sequence_trades.csv',index=False)
 if not sq.empty:sq.to_csv(OUT/'v348_complete_sequences_before_target_gate.csv',index=False)
 report={'version':'V348_CAUSAL_SEQUENCE_REBUILD_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'symbols_scanned':len(list(KDIR.glob('*_daily_750.json'))),'stage_counts':dict(counts),'causality_invariants':{'pre_event_poi':True,'target_known_before_entry':True,'entry_after_takeover':bool((df.entry_date>=df.takeover_date).all()) if not df.empty else True,'t_plus_1_violations':len(bad)},'gate':GATE,'full_2023_26':full,'train_2023_24':train,'oos_2025_26':test,'target_space_by_sequence_family':target_summary,'decision':'V348_CAUSAL_SEQUENCE_PASS__SHADOW_ONLY' if passed(full) and not bad else 'V348_CAUSAL_SEQUENCE_FAIL__NO_PROMOTION','artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'trades':str(OUT/'v348_causal_sequence_trades.csv')}}
 text=json.dumps(report,ensure_ascii=False,indent=2,default=lambda x:x.item() if hasattr(x,'item') else str(x));(OUT/'v348_report.json').write_text(text);LATEST.write_text(text);print(json.dumps({'decision':report['decision'],'scanned':report['symbols_scanned'],'stages':report['stage_counts'],'invariants':report['causality_invariants'],'full':full,'oos':test,'artifacts':report['artifacts']},ensure_ascii=False,indent=2,default=str))
if __name__=='__main__':main()
