#!/usr/bin/env python3
"""V342 fast no-write: BSL room signal-layer frontier.

Focused rerun of V342 after the broad grid timed out. It tests whether a true
pre-entry SMC target-room feature (prior buy-side liquidity room) can recover the
production gate using only two already validated exit contracts.
"""
from __future__ import annotations
import itertools, json, math
from datetime import datetime
from pathlib import Path
from typing import Any
import pandas as pd
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; KDIR=ROOT/'kline_cache'; V333=AUD/'v333_full_universe_rule_search_after_breadth_refresh_latest.json'
OUT=AUD/f"v342_fast_bsl_room_signal_layer_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"; LATEST=AUD/'v342_fast_bsl_room_signal_layer_latest.json'
WEAK={'C27医药制造业','C32有色金属冶炼和压延加工业'}
GATE={'n':570,'min_year_n':70,'wr':93.0,'avg':7.6,'min_year_wr':91.0,'micro':1.0,'t1':0,'current_open':1}

def dn(x:Any)->str:
 s=''.join(ch for ch in str(x or '').replace('-','')[:10] if ch.isdigit()); return s[:8] if len(s)>=8 else ''
def sf(x:Any, default=None):
 try:
  if x is None or x=='': return default
  v=float(x); return default if math.isnan(v) or math.isinf(v) else v
  return v
 except Exception: return default
def boolish(x:Any)->bool: return str(x).strip().lower() in {'true','1','yes'}
def load_json(p:Path, default:Any)->Any:
 try: return json.loads(p.read_text())
 except Exception: return default
def bars(sym:str):
 out=[]; p=KDIR/f"{sym.replace('.','_')}_daily_750.json"
 for b in load_json(p,[]):
  d=dn(b.get('t') or b.get('date')); o,h,l,c=sf(b.get('o')),sf(b.get('h')),sf(b.get('l')),sf(b.get('c'))
  if d and None not in (o,h,l,c): out.append((d,float(o),float(h),float(l),float(c)))
 return sorted(out)
def metrics(vals,yrs,reasons):
 s=pd.Series(vals); y=pd.Series(yrs); rr=pd.Series(reasons); ok=s.notna(); s=s[ok].astype(float); y=y[ok]; rr=rr[ok]
 if len(s)==0: return {'n':0,'wr':0,'avg':0,'min_year_n':0,'year_counts':{},'year_wr':{},'min_year_wr':0,'micro':0,'t1':0,'exit_counts':{}}
 yc={str(k):int(v) for k,v in y[y>='2023'].value_counts().sort_index().to_dict().items()}; ywr={str(k):round(float((s[y==k]>0).mean()*100),2) for k in sorted(yc)}
 return {'n':int(len(s)),'wr':round(float((s>0).mean()*100),4),'avg':round(float(s.mean()),4),'min_year_n':int(min(yc.values()) if yc else 0),'year_counts':yc,'year_wr':ywr,'min_year_wr':round(float(min(ywr.values()) if ywr else 0),2),'micro':round(float(((s>0)&(s<1)).mean()*100),4),'t1':0,'exit_counts':{str(k):int(v) for k,v in rr.value_counts().to_dict().items()}}
def gate(m): return m['n']>=GATE['n'] and m['min_year_n']>=GATE['min_year_n'] and m['wr']>=GATE['wr'] and m['avg']>=GATE['avg'] and m['min_year_wr']>=GATE['min_year_wr'] and m['micro']<=GATE['micro']

def main():
 OUT.mkdir(parents=True,exist_ok=True); rep=load_json(V333,{}); df=pd.read_csv(rep['artifacts']['replayed_csv'],low_memory=False); df['entry_date']=df.entry_date.map(dn)
 n=lambda c: pd.to_numeric(df.get(c,pd.Series(index=df.index)),errors='coerce'); ss=lambda c: df.get(c,pd.Series('',index=df.index)).astype(str)
 actual=n('v333_actual_bars_since_entry'); cur_base=actual.le(10)&(~ss('v333_any_history_overlap').str.lower().isin(['true','1']))
 weak=ss('v244_industry').isin(WEAK); add=n('v244_ind_strong1_pct').ge(31.1688)|n('v236_br_above_ma20').ge(46.8561)
 base=ss('v164_rule_pass').map(boolish)&((~weak)|add)
 seed=base&n('v132_bull_count_3').ge(3)&ss('poi_source').isin(['DEMAND_OB','OB+FVG','FVG_Demand'])
 cache={}; paths={}; feats=[]
 for ix,r in df[seed.fillna(False)].iterrows():
  sym=str(r.symbol); ed=dn(r.entry_date); ep=sf(r.entry_price); zl=sf(r.zone_low)
  if sym not in cache: cache[sym]=bars(sym)
  b=cache[sym]; dates=[x[0] for x in b]
  if ed not in dates or not ep or not zl: continue
  pos=dates.index(ed); pre=b[:pos]; fut=[x for x in b if x[0]>ed][:40]
  if len(pre)<65: continue
  def hi(w): return max(x[2] for x in w)
  def lo(w): return min(x[3] for x in w)
  h20,h60=hi(pre[-20:]),hi(pre[-60:]); l20,l60=lo(pre[-20:]),lo(pre[-60:])
  atr=sum(max(x[2]-x[3],abs(x[2]-pre[max(0,pos-20+j-1)][4]),abs(x[3]-pre[max(0,pos-20+j-1)][4])) for j,x in enumerate(pre[-20:]))/20
  feat={'ix':int(ix),'symbol':sym,'year':ed[:4],'entry_date':ed,'ep':ep,'zl':zl,'actual':sf(r.v333_actual_bars_since_entry),'cur':bool(cur_base.loc[ix]),'poi_source':str(r.poi_source),'market_state':str(r.market_state),'reclaim_class':str(r.v132_reclaim_class),'zone_width':sf(r.v85_zone_width_pct),'body':sf(r.v132_reclaim_bull_body_pct),'br':sf(r.v236_br_above_ma20),'bsl20':(h20/ep-1)*100,'bsl60':(h60/ep-1)*100,'pos20':(ep-l20)/(h20-l20)*100 if h20>l20 else None,'pos60':(ep-l60)/(h60-l60)*100 if h60>l60 else None,'atr':atr/ep*100,'pre10':(pre[-1][4]/pre[-10][4]-1)*100 if pre[-10][4] else None}
  paths[int(ix)]={'feat':feat,'path':fut}; feats.append(feat)
 fdf=pd.DataFrame(feats)
 contracts=[('OB_prod_like',0.005,4,0.7,30,20),('F1_quality_like',0.005,5,0.5,20,20),('research_runner',0.005,6,0.5,20,20)]
 families={}
 for src in ['ALL','OB','FVG']:
  sm=pd.Series(True,index=fdf.index)
  if src=='OB': sm=fdf.poi_source.isin(['DEMAND_OB','OB+FVG'])
  if src=='FVG': sm=fdf.poi_source.eq('FVG_Demand')
  for room in [0,5,10,15,20,25,30]:
   for pos in [None,50,65,80]:
    for atrmax in [None,8,12,16]:
     m=sm & fdf.bsl60.ge(room)
     name=f'{src}_bsl60>={room}'
     if pos is not None: m &= fdf.pos60.le(pos); name+=f'_pos60<={pos}'
     if atrmax is not None: m &= fdf.atr.le(atrmax); name+=f'_atr<={atrmax}'
     if int(m.sum())>=120: families[name]=m
 results=[]
 def replay(i,slbuf,tp1,frac,tp2,mh):
  x=paths[i]; ep=x['feat']['ep']; zl=x['feat']['zl']; path=x['path'][:mh]; sl=zl*(1-slbuf)
  if sl>=ep: sl=ep*.985
  t1=ep*(1+tp1/100); t2=ep*(1+tp2/100); got=False; pnl1=0.0; rsl=sl
  for k,(_,_,h,l,c) in enumerate(path,1):
   if not got:
    if l<=sl: return (sl/ep-1)*100,'SL_BEFORE_TP1'
    if h>=t1:
     got=True; pnl1=tp1*(1-frac); rsl=ep
     if l<=rsl: return pnl1,'TP1_BE_SAME_BAR'
    elif k>=mh: return (c/ep-1)*100,'TIME_NO_TP1'
    continue
   if l<=rsl: return pnl1,'RUNNER_BE'
   if h>=t2: return pnl1+tp2*frac,'TP2'
   if k>=mh: return pnl1+(c/ep-1)*100*frac,'TIME_AFTER_TP1'
  return None,'OPEN'
 for fname,mask in families.items():
  idx=[int(fdf.loc[j,'ix']) for j in fdf.index[mask]]
  for cname,sl,tp1,frac,tp2,mh in contracts:
   hist=[i for i in idx if paths[i]['feat']['actual'] is not None and paths[i]['feat']['actual']>=mh]
   cur=[i for i in idx if paths[i]['feat']['cur']]
   vals=[]; yrs=[]; reasons=[]
   for i in hist:
    v,rs=replay(i,sl,tp1,frac,tp2,mh); vals.append(v); yrs.append(paths[i]['feat']['year']); reasons.append(rs)
   hm=metrics(vals,yrs,reasons)
   cvals=[]; cyrs=[]; creasons=[]; open_n=0
   for i in cur:
    v,rs=replay(i,sl,tp1,frac,tp2,mh); open_n += 1 if v is None else 0; cvals.append(v); cyrs.append(paths[i]['feat']['year']); creasons.append(rs)
   cm=metrics(cvals,cyrs,creasons)
   pg=gate(hm) and open_n>=GATE['current_open']
   score=(hm['wr']-90)*.45+hm['avg']*.9+hm['min_year_wr']*.03+min(hm['n'],570)/570-hm['micro']*.5+open_n*.05
   results.append({'family':fname,'contract':cname,'score':round(float(score),4),'hist':hm,'current_closed':cm,'current_rows':len(cur),'current_open_rows':open_n,'pass_gate':pg})
 results=sorted(results,key=lambda r:(r['pass_gate'],r['hist']['wr'],r['hist']['avg'],r['hist']['n']),reverse=True); passing=[r for r in results if r['pass_gate']]
 frontier=[]
 for need in [120,200,300,400,500,570,700,900,1200]:
  cand=[r for r in results if r['hist']['n']>=need]
  if cand: frontier.append({'min_n':need,'best':cand[0]})
 pd.DataFrame([{**{'family':r['family'],'contract':r['contract'],'score':r['score'],'current_rows':r['current_rows'],'current_open_rows':r['current_open_rows'],'pass_gate':r['pass_gate']},**{f"hist_{k}":v for k,v in r['hist'].items() if not isinstance(v,dict)},**{f"cur_{k}":v for k,v in r['current_closed'].items() if not isinstance(v,dict)}} for r in results[:1000]]).to_csv(OUT/'v342_fast_bsl_top1000.csv',index=False)
 fdf.to_csv(OUT/'v342_bsl_features.csv',index=False)
 report={'version':'V342_FAST_BSL_ROOM_SIGNAL_LAYER_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source':rep['artifacts']['replayed_csv'],'gate':GATE,'feature_rows':int(len(fdf)),'families_evaluated':len(families),'rules_evaluated':len(results),'passing_rule_count':len(passing),'top_passing':passing[:20],'coverage_frontier':frontier,'top_rules':results[:50],'decision':'V342_BSL_ROOM_RECOVERS_PRODUCTION_GATE__SHADOW_ONLY_NO_WRITE' if passing else 'V342_BSL_ROOM_FAILS_PRODUCTION_GATE__NEED_SEQUENCE_REBUILD','artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'rule_table':str(OUT/'v342_fast_bsl_top1000.csv'),'features':str(OUT/'v342_bsl_features.csv')}}
 (OUT/'v342_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); LATEST.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'latest':str(LATEST),'decision':report['decision'],'passing_rule_count':len(passing),'frontier':frontier,'top_rules':results[:8]},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
