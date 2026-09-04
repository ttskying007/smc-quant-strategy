#!/usr/bin/env python3
"""V350 no-write: confirmed-swing + displacement causal SMC sequence audit.
Replaces V348's five-bar breakout event with confirmed pivot structure; no promotion.
"""
from __future__ import annotations
import importlib.util,json,math
from collections import Counter
from datetime import datetime
from pathlib import Path
import pandas as pd
ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'; ENV=ROOT/'smc_opt_v74_env_state_machine'/'v74_env_by_date.json'; OUT=AUD/f"v350_confirmed_swing_sequence_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"; LATEST=AUD/'v350_confirmed_swing_sequence_latest.json'
spec=importlib.util.spec_from_file_location('v348','/root/.hermes/scripts/v25/v348_causal_sequence_rebuild_audit.py'); v348=importlib.util.module_from_spec(spec);spec.loader.exec_module(v348)
def atr(ks,i):
 return sum(max(v348.bv(ks[j],'h')-v348.bv(ks[j],'l'),abs(v348.bv(ks[j],'h')-v348.bv(ks[j-1],'c')),abs(v348.bv(ks[j],'l')-v348.bv(ks[j-1],'c'))) for j in range(max(1,i-14),i))/max(1,min(14,i-1))
def pivots(ks,i):
 hs=[];ls=[]
 for j in range(3,i-2):
  h=v348.bv(ks[j],'h');l=v348.bv(ks[j],'l')
  if h>max(v348.bv(x,'h') for x in ks[j-3:j]) and h>=max(v348.bv(x,'h') for x in ks[j+1:j+4]):hs.append(j)
  if l<min(v348.bv(x,'l') for x in ks[j-3:j]) and l<=min(v348.bv(x,'l') for x in ks[j+1:j+4]):ls.append(j)
 return hs,ls
def event(ks,i,state,all_hs,all_ls):
 hs=[j for j in all_hs if j<=i-3]; ls=[j for j in all_ls if j<=i-3]
 if len(hs)<2 or len(ls)<2:return None
 h0,h1=hs[-2],hs[-1]; l0,l1=ls[-2],ls[-1]; b=ks[i]; a=atr(ks,i)
 displacement=v348.bv(b,'c')>v348.bv(ks[h1],'h')+a*.20 and (v348.bv(b,'c')-v348.bv(b,'o'))>=a*.80
 if not displacement:return None
 up=v348.bv(ks[h1],'h')>v348.bv(ks[h0],'h') and v348.bv(ks[l1],'l')>v348.bv(ks[l0],'l')
 sweeps=[j for j in range(max(h1+3,i-8),i) if v348.bv(ks[j],'l')<v348.bv(ks[l1],'l') and v348.bv(ks[j],'c')>v348.bv(ks[l1],'l')]
 if up and state in {'BULL_CONTINUATION','RECOVERY','ACCUMULATION'}:return {'type':'CONFIRMED_BOS_CONTINUATION','sweep_idx':None,'break_level':v348.bv(ks[h1],'h'),'swing_high_idx':h1,'swing_low_idx':l1}
 if sweeps and state in {'BEAR_RISK','DISTRIBUTION','MIXED','ACCUMULATION','RECOVERY'}:return {'type':'CONFIRMED_SSL_CHOCH_REVERSAL','sweep_idx':sweeps[-1],'break_level':v348.bv(ks[h1],'h'),'swing_high_idx':h1,'swing_low_idx':l1}
 return None
def main():
 OUT.mkdir(parents=True,exist_ok=True); env=json.loads(ENV.read_text()); rows=[]; counts=Counter(); t1=0
 for path in sorted(KDIR.glob('*_daily_750.json')):
  ks=v348.bars(path); sym=v348.symbol(path)
  if len(ks)<100:continue
  all_hs,all_ls=pivots(ks,len(ks)-2)
  for i in range(20,len(ks)-16):
   state=str((env.get(v348.date(ks[i]),{}) or {}).get('market_state_v74') or '')
   ev=event(ks,i,state,all_hs,all_ls)
   if not ev:continue
   counts['confirmed_displacement_events']+=1; p=v348.poi(ks,i,ev)
   if not p:counts['no_discount_pre_event_ob']+=1;continue
   e=v348.entry(ks,i,p)
   if not e:counts['no_touch_reclaim_takeover']+=1;continue
   counts['complete_sequence']+=1; pnl,reason,hold,xi=v348.replay(ks,e,p)
   if not math.isfinite(pnl):counts[reason]+=1;continue
   ed=v348.date(ks[e['idx']]);xd=v348.date(ks[xi])
   if xd<=ed:t1+=1;continue
   rows.append({'symbol':sym,'event_type':ev['type'],'market_state':state,'event_date':v348.date(ks[i]),'swing_high_date':v348.date(ks[ev['swing_high_idx']]),'swing_low_date':v348.date(ks[ev['swing_low_idx']]),'zone_date':v348.date(ks[p['idx']]),'touch_date':v348.date(ks[e['touch']]),'reclaim_date':v348.date(ks[e['reclaim']]),'takeover_date':v348.date(ks[e['takeover']]),'entry_date':ed,'exit_date':xd,'entry_price':e['price'],'zone_low':p['low'],'zone_high':p['high'],'known_target':e['target'],'pnl':pnl,'reason':reason,'hold_bars':hold,'year':ed[:4],'quarter':str(pd.to_datetime(ed,format='%Y%m%d').to_period('Q'))})
 df=pd.DataFrame(rows); hist=df[df.year.isin(['2023','2024','2025','2026'])].copy() if not df.empty else df; full=v348.metrics(hist);train=v348.metrics(hist[hist.year.isin(['2023','2024'])]);test=v348.metrics(hist[hist.year.isin(['2025','2026'])])
 if not hist.empty:hist.to_csv(OUT/'v350_confirmed_swing_trades.csv',index=False)
 by=[]
 if not hist.empty:
  for (typ,state),x in hist.groupby(['event_type','market_state']):by.append({'event_type':typ,'market_state':state,**v348.metrics(x)})
 report={'version':'V350_CONFIRMED_SWING_DISPLACEMENT_SEQUENCE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'symbols_scanned':len(list(KDIR.glob('*_daily_750.json'))),'stage_counts':dict(counts),'causality_invariants':{'confirmed_pivots_before_break':True,'displacement_before_poi':True,'poi_before_touch':True,'entry_after_takeover':True,'target_known_before_entry':True,'t_plus_1_violations':t1},'full_2023_26':full,'train_2023_24':train,'oos_2025_26':test,'by_event_state':by,'decision':'V350_CONFIRMED_SEQUENCE_PASS__SHADOW_ONLY' if v348.passed(full) and not t1 else 'V350_CONFIRMED_SEQUENCE_FAIL__NO_PROMOTION','artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'trades':str(OUT/'v350_confirmed_swing_trades.csv')}}
 text=json.dumps(report,ensure_ascii=False,indent=2,default=lambda x:x.item() if hasattr(x,'item') else str(x));(OUT/'v350_report.json').write_text(text);LATEST.write_text(text);print(json.dumps({'decision':report['decision'],'stages':report['stage_counts'],'invariants':report['causality_invariants'],'full':full,'oos':test,'by_event_state':by,'artifacts':report['artifacts']},ensure_ascii=False,indent=2,default=str))
if __name__=='__main__':main()
