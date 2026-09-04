#!/usr/bin/env python3
"""V535 one frozen strict-T+1 replay for V533/V534 selling-climax ontology."""
from __future__ import annotations
import csv,json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
ROOT=Path('/root/.hermes');KDIR=ROOT/'kline_cache';AUD=ROOT/'smc_audit';V533=AUD/'v533_selling_climax_ar_st_sos_seed_gate_latest.json';V534=AUD/'v534_selling_climax_ar_st_sos_independent_oracle_latest.json';OUT=AUD/f'v535_selling_climax_ar_st_sos_frozen_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}';LATEST=AUD/'v535_selling_climax_ar_st_sos_frozen_t1_replay_latest.json'
L=R=3;BUF=.99;HOLD=20;FEE=.20;YEARS=('2023','2024','2025','2026');GATE={'n_min':300,'year_n_min':40,'gross_wr_pct_min':55.,'avg_net_pnl_pct_min':.5,'pf_min':1.15,'payoff_min':.7,'year_avg_net_pnl_pct_min':0.}
def n(x:Any)->float|None:
 try:x=float(x);return x if x>0 else None
 except(ValueError,TypeError):return None
def d(x:Any)->str:
 x=''.join(c for c in str(x or '') if c.isdigit());return x[:8] if len(x)>=8 else ''
def load(s:str)->list[dict[str,Any]]:
 code,ex=s.split('.')
 try:r=json.loads((KDIR/f'{code}_{ex}_daily_750.json').read_text())
 except Exception:return []
 o=[]
 for x in r if isinstance(r,list) else []:
  t=d(x.get('t') or x.get('date'));q=[n(x.get(k)) for k in ('o','h','l','c')]
  if t and all(z is not None for z in q):o.append(dict(zip(('t','o','h','l','c'),(t,*q))))
 return sorted(o,key=lambda x:x['t'])
def ph(b:list[dict[str,Any]],i:int)->bool:return i>=L and i+R<len(b) and b[i]['h']>max(b[j]['h'] for j in range(i-L,i)) and b[i]['h']>=max(b[j]['h'] for j in range(i+1,i+R+1))
def target(b:list[dict[str,Any]],sos:int,e:float)->tuple[int,float]|None:
 for i in range(sos-R-1,L-1,-1):
  if ph(b,i) and b[i]['h']>e:return i,b[i]['h']
 return None
def pct(x:float,b:float)->float:return(x/b-1)*100
def replay(x:dict[str,str],b:list[dict[str,Any]])->dict[str,Any]:
 p={z['t']:i for i,z in enumerate(b)};ks=('climax_date','ar_date','st_date','sos_date','entry_eligible_date')
 if any(x[k] not in p for k in ks):return {'status':'SKIP','reason':'SEED_DATE_NOT_IN_CACHE'}
 ci,ar,st,sos,ei=(p[x[k]] for k in ks)
 if not ci<ar<st<sos<ei:return {'status':'SKIP','reason':'INVALID_EVENT_ORDER'}
 entry=b[ei]['o'];stop=float(x['climax_low'])*BUF
 if stop>=entry:return {'status':'SKIP','reason':'INVALID_STRUCTURAL_STOP'}
 t=target(b,sos,entry)
 if t is None:return {'status':'SKIP','reason':'NO_VISIBLE_UPSIDE_TARGET'}
 ti,tp=t;path=b[ei+1:ei+1+HOLD]
 if not path:return {'status':'OPEN_DATA','reason':'NO_POST_ENTRY_BAR'}
 for hold,z in enumerate(path,1):
  if z['o']<=stop:price,reason=z['o'],'GAP_SL';break
  if z['l']<=stop:price,reason=stop,'SL';break
  if z['h']>=tp:price,reason=tp,'TP_STRUCTURAL';break
 else:
  if len(path)<HOLD:return {'status':'OPEN_DATA','reason':'INSUFFICIENT_FORWARD_BARS'}
  hold=len(path);z=path[-1];price,reason=z['c'],'TIME20'
 return {'status':'CLOSED','reason':reason,'entry_date':b[ei]['t'],'entry_price':round(entry,6),'exit_date':z['t'],'exit_price':round(price,6),'stop':round(stop,6),'target':round(tp,6),'target_swing_idx':ti,'target_swing_date':b[ti]['t'],'hold_bars':hold,'gross_pnl_pct':round(pct(price,entry),6),'net_pnl_pct':round(pct(price,entry)-FEE,6),'same_day_exit_violation':b[ei]['t']==z['t']}
def metric(a:list[dict[str,Any]])->dict[str,Any]:
 p=[x['net_pnl_pct'] for x in a];w=[x for x in p if x>0];l=[x for x in p if x<0]
 return {'n':len(a),'gross_wr_pct':round(100*len(w)/len(a),4) if a else 0,'avg_net_pnl_pct':round(sum(p)/len(a),4) if a else 0,'avg_win_pct':round(sum(w)/len(w),4) if w else 0,'avg_loss_pct':round(sum(l)/len(l),4) if l else 0,'payoff_rr':round((sum(w)/len(w))/abs(sum(l)/len(l)),4) if w and l else 0,'profit_factor':round(sum(w)/abs(sum(l)),4) if l else 0,'total_net_pnl_pct':round(sum(p),4),'exit_counts':dict(Counter(x['reason'] for x in a))}
def main()->None:
 source,oracle=json.loads(V533.read_text()),json.loads(V534.read_text())
 if not source.get('support_gate_pass') or not oracle.get('oracle_pass') or source.get('outcomes_opened') or oracle.get('outcomes_opened'):raise RuntimeError('pre-outcome contract failed')
 with Path(source['artifacts']['seeds']).open(newline='',encoding='utf8')as h:s=list(csv.DictReader(h))
 s.sort(key=lambda x:(x['entry_eligible_date'],x['symbol'],int(x['climax_idx'])));cache={};busy={};closed=[];opens=[];skip=Counter()
 for x in s:
  sym=x['symbol'];ed=x['entry_eligible_date']
  if busy.get(sym,'')>=ed:skip['SYMBOL_ALREADY_OPEN']+=1;continue
  z=replay(x,cache.setdefault(sym,load(sym)))
  if z['status']=='SKIP':skip[z['reason']]+=1;continue
  if z['status']=='OPEN_DATA':opens.append({**x,**z});skip[z['reason']]+=1;continue
  z={**x,**z};closed.append(z);busy[sym]=z['exit_date']
 over=metric(closed);year={y:metric([x for x in closed if x['entry_date'].startswith(y)]) for y in YEARS};inv={'seed_count_matches_oracle':len(s)==oracle['generator_seed_count']==oracle['oracle_seed_count'],'all_entries_after_sos':all(x['entry_eligible_date']>x['sos_date'] for x in closed),'all_targets_visible_pre_sos':all(x['target_swing_date']<x['sos_date'] for x in closed),'t1_violations':sum(x['same_day_exit_violation'] for x in closed),'duplicate_symbol_entry':len(closed)-len({(x['symbol'],x['entry_date']) for x in closed}),'all_production_writes_false':True}
 checks={'n>=300':over['n']>=GATE['n_min'],'each_year_n>=40':all(year[y]['n']>=GATE['year_n_min'] for y in YEARS),'gross_wr>=55':over['gross_wr_pct']>=55,'avg_net>=0.5':over['avg_net_pnl_pct']>=.5,'pf>=1.15':over['profit_factor']>=1.15,'payoff>=0.7':over['payoff_rr']>=.7,'each_year_avg_net>0':all(year[y]['avg_net_pnl_pct']>0 for y in YEARS),'t1_violations==0':inv['t1_violations']==0,'duplicate_symbol_entry==0':inv['duplicate_symbol_entry']==0};OUT.mkdir(parents=True,exist_ok=True);cp=OUT/'v535_frozen_t1_trades.csv'
 if closed:
  with cp.open('w',newline='',encoding='utf8')as h:w=csv.DictWriter(h,fieldnames=list(closed[0]));w.writeheader();w.writerows(closed)
 report={'version':'V535_SELLING_CLIMAX_AR_ST_SOS_FROZEN_T1_REPLAY_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'frozen_execution_contract':'eligible-day open; stop=climax low*0.99; nearest prior visible confirmed swing high above entry target; exits begin following session; SL-first collision; time20; round-trip fee0.20%; serial one-position-per-symbol','seed_count':len(s),'closed_trade_count':len(closed),'open_data_count':len(opens),'skip_counts':dict(skip),'overall':over,'yearly':year,'promotion_gate':GATE,'promotion_checks':checks,'invariants':inv,'promotion_gate_pass':all(checks.values()),'decision':'V535_PROMOTION_GATE_PASS__INDEPENDENT_METRIC_AUDIT_REQUIRED' if all(checks.values()) else 'V535_FROZEN_REPLAY_FAIL__CLOSE_ONTOLOGY__NO_VARIANTS','artifacts':{'out_dir':str(OUT),'trades':str(cp),'v533':str(V533),'v534':str(V534)}}
 text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v535_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
