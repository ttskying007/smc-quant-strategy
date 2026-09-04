#!/usr/bin/env python3
"""V450 no-outcome EQH liquidity-compression release generator."""
from __future__ import annotations
import csv,json,math
from collections import Counter
from datetime import datetime
from pathlib import Path
R=Path('/root/.hermes');K=R/'kline_cache';A=R/'smc_audit';O=A/f"v450_eqh_compression_generator_no_write_{datetime.now():%Y%m%d_%H%M%S}";L=A/'v450_eqh_compression_generator_latest.json'
def f(x):
 try:v=float(x);return v if math.isfinite(v) else 0.
 except:return 0.
def d(b):return ''.join(c for c in str(b.get('t') or b.get('date') or '') if c.isdigit())[:8]
def load(p):
 try:a=json.loads(p.read_text())
 except:return []
 z=[]
 for b in a:
  q={k:f(b.get(k)) for k in ('o','h','l','c')}
  if d(b) and all(q.values()):q['t']=d(b);z.append(q)
 return sorted(z,key=lambda x:x['t'])
def piv(b,key):
 z=[]
 for i in range(3,len(b)-3):
  x=b[i][key]
  if all((b[j][key]<x if key=='h' else b[j][key]>x) for j in range(i-3,i+4) if j!=i):z.append((i,i+3,x))
 return z
def sym(p):a,b=p.name.removesuffix('_daily_750.json').split('_');return f'{a}.{b}'
def gen(s,b):
 hs,ls=piv(b,'h'),piv(b,'l');rows=[];seen=set();bad=Counter()
 for k in range(1,len(hs)):
  h1,h2=hs[k-1],hs[k]
  if not 3<=h2[0]-h1[0]<=40 or abs(h2[2]/h1[2]-1)>.003:continue
  pool_lo,pool_hi=min(h1[2],h2[2]),max(h1[2],h2[2])
  lows=[x for x in ls if h1[0]<x[0]<h2[1]+31]
  pre=[x for x in lows if x[0]<h2[1]]
  if len(pre)<3 or not(pre[-3][2]<pre[-2][2]<pre[-1][2]):bad['NO_THREE_HIGHER_LOWS']+=1;continue
  event=next((j for j in range(h2[1]+1,min(len(b),h2[1]+31)) if b[j]['c']>pool_hi*1.002),None)
  if event is None:bad['NO_EQH_BREAKOUT']+=1;continue
  protected=[x for x in ls if h1[0]<x[0]<event and x[1]<event]
  if len(protected)<3 or not(protected[-3][2]<protected[-2][2]<protected[-1][2]):bad['COMPRESSION_NOT_PERSISTENT']+=1;continue
  touch=hold=None;cancel=False
  for j in range(event+1,min(len(b),event+21)):
   if b[j]['c']<protected[-1][2]:cancel=True;break
   if touch is None:
    if b[j]['l']<=pool_hi and b[j]['c']>pool_lo:touch=j
    continue
   if j>touch and b[j]['c']>pool_hi and b[j]['l']>=pool_lo:hold=j;break
  if cancel:bad['PROTECTED_LOW_INVALIDATED']+=1;continue
  if hold is None or hold+1>=len(b):bad['NO_RETEST_HOLD']+=1;continue
  key=(s,b[hold+1]['t'])
  if key in seen:bad['DUPLICATE']+=1;continue
  seen.add(key);rows.append({'symbol':s,'ontology':'EQH_LIQUIDITY_COMPRESSION_RELEASE','eqh1_idx':h1[0],'eqh1_confirm_idx':h1[1],'eqh1_price':h1[2],'eqh2_idx':h2[0],'eqh2_confirm_idx':h2[1],'eqh2_price':h2[2],'pool_low':pool_lo,'pool_high':pool_hi,'hl1_idx':protected[-3][0],'hl1_price':protected[-3][2],'hl2_idx':protected[-2][0],'hl2_price':protected[-2][2],'protected_low_idx':protected[-1][0],'protected_low_confirm_idx':protected[-1][1],'protected_low':protected[-1][2],'event_idx':event,'event_date':b[event]['t'],'touch_idx':touch,'touch_date':b[touch]['t'],'takeover_idx':hold,'takeover_date':b[hold]['t'],'eligible_entry_idx':hold+1,'eligible_entry_date':b[hold+1]['t'],'semantic_order_valid':h1[1]<h2[0]<h2[1]<event<touch<hold<hold+1,'tradable':False,'buy_enabled':False})
 return rows,bad
def main():
 O.mkdir();rows=[];bad=Counter();sc=0
 for n,p in enumerate(sorted(K.glob('*_daily_750.json')),1):
  b=load(p)
  if len(b)<80:continue
  sc+=1;x,y=gen(sym(p),b);rows+=x;bad.update(y)
  if n%500==0:print(json.dumps({'progress':n,'seeds':len(rows)}),flush=True)
 fs=sorted({k for x in rows for k in x});sf=O/'v450_seeds.csv'
 with sf.open('w',newline='') as h:w=csv.DictWriter(h,fieldnames=fs);w.writeheader();w.writerows(rows)
 yr=Counter(x['eligible_entry_date'][:4] for x in rows);o={'version':'V450_EQH_COMPRESSION_GENERATOR_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'frozen_contract':'two confirmed EQH + three rising confirmed lows -> close breakout -> first pool retest -> hold -> next open','symbols_scanned':sc,'seed_count':len(rows),'yearly_seed_count':dict(yr),'rejection_counts':dict(bad),'semantic_order_failures':sum(not x['semantic_order_valid'] for x in rows),'duplicate_symbol_entry':len(rows)-len(set((x['symbol'],x['eligible_entry_date']) for x in rows)),'support_gate_pass':len(rows)>=300 and all(yr[y]>=40 for y in ('2023','2024','2025','2026')),'artifacts':{'out_dir':str(O),'seeds':str(sf),'latest':str(L)}}
 o['decision']='READY_FOR_ORACLE' if o['support_gate_pass'] else 'INSUFFICIENT_SUPPORT__NO_REPLAY';t=json.dumps(o,ensure_ascii=False,indent=2);(O/'v450_report.json').write_text(t);L.write_text(t);print(t)
if __name__=='__main__':main()
