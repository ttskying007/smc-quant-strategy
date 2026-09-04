#!/usr/bin/env python3
"""V532 one frozen strict-T+1 replay for the V530/V531 SOS-backup ontology."""
from __future__ import annotations
import csv,json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT=Path('/root/.hermes');KDIR=ROOT/'kline_cache';AUD=ROOT/'smc_audit'
V530=AUD/'v530_sos_backup_effort_result_seed_gate_latest.json';V531=AUD/'v531_sos_backup_effort_result_independent_oracle_latest.json'
OUT=AUD/f'v532_sos_backup_effort_result_frozen_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}';LATEST=AUD/'v532_sos_backup_effort_result_frozen_t1_replay_latest.json'
L=R=3;STOP_BUFFER=.99;MAX_HOLD=20;FEE=.20;YEARS=('2023','2024','2025','2026')
GATE={'n_min':300,'year_n_min':40,'gross_wr_pct_min':55.0,'avg_net_pnl_pct_min':.5,'pf_min':1.15,'payoff_min':.7,'year_avg_net_pnl_pct_min':0.0}

def n(x:Any)->float|None:
 try:x=float(x);return x if x>0 else None
 except (ValueError,TypeError):return None
def d(x:Any)->str:
 x=''.join(c for c in str(x or '') if c.isdigit());return x[:8] if len(x)>=8 else ''
def load(sym:str)->list[dict[str,Any]]:
 code,ex=sym.split('.')
 try:raw=json.loads((KDIR/f'{code}_{ex}_daily_750.json').read_text())
 except Exception:return []
 out=[]
 for x in raw if isinstance(raw,list) else []:
  date=d(x.get('t') or x.get('date') or x.get('day'));v=[n(x.get(k)) for k in ('o','h','l','c')]
  if date and all(z is not None for z in v):out.append(dict(zip(('t','o','h','l','c'),(date,*v))))
 return sorted(out,key=lambda x:x['t'])
def pivot_high(b:list[dict[str,Any]],i:int)->bool:
 return i>=L and i+R<len(b) and b[i]['h']>max(b[j]['h'] for j in range(i-L,i)) and b[i]['h']>=max(b[j]['h'] for j in range(i+1,i+R+1))
def target(b:list[dict[str,Any]],reaccept:int,entry:float)->tuple[int,float]|None:
 for i in range(reaccept-R-1,L-1,-1):
  if pivot_high(b,i) and b[i]['h']>entry:return i,b[i]['h']
 return None
def pct(value:float,base:float)->float:return(value/base-1)*100

def replay(seed:dict[str,str],b:list[dict[str,Any]])->dict[str,Any]:
 pos={x['t']:i for i,x in enumerate(b)}; dates=('swing_date','sos_date','backup_date','reaccept_date','entry_eligible_date')
 if any(seed[x] not in pos for x in dates):return {'status':'SKIP','reason':'SEED_DATE_NOT_IN_CACHE'}
 swing,sos,backup,reaccept,entry_i=(pos[seed[x]] for x in dates)
 if not swing<sos<backup<reaccept<entry_i:return {'status':'SKIP','reason':'INVALID_EVENT_ORDER'}
 entry=b[entry_i]['o'];stop=float(seed['backup_low'])*STOP_BUFFER
 if stop>=entry:return {'status':'SKIP','reason':'INVALID_STRUCTURAL_STOP'}
 anchor=target(b,reaccept,entry)
 if anchor is None:return {'status':'SKIP','reason':'NO_VISIBLE_UPSIDE_TARGET'}
 ti,tp=anchor;path=b[entry_i+1:entry_i+1+MAX_HOLD]
 if not path:return {'status':'OPEN_DATA','reason':'NO_POST_ENTRY_BAR'}
 for hold,bar in enumerate(path,1):
  if bar['o']<=stop:price,reason=bar['o'],'GAP_SL';break
  if bar['l']<=stop:price,reason=stop,'SL';break
  if bar['h']>=tp:price,reason=tp,'TP_STRUCTURAL';break
 else:
  if len(path)<MAX_HOLD:return {'status':'OPEN_DATA','reason':'INSUFFICIENT_FORWARD_BARS'}
  hold=len(path);bar=path[-1];price,reason=bar['c'],'TIME20'
 return {'status':'CLOSED','reason':reason,'entry_date':b[entry_i]['t'],'entry_price':round(entry,6),'exit_date':bar['t'],'exit_price':round(price,6),'stop':round(stop,6),'target':round(tp,6),'target_swing_idx':ti,'target_swing_date':b[ti]['t'],'hold_bars':hold,'gross_pnl_pct':round(pct(price,entry),6),'net_pnl_pct':round(pct(price,entry)-FEE,6),'same_day_exit_violation':b[entry_i]['t']==bar['t']}
def metrics(rows:list[dict[str,Any]])->dict[str,Any]:
 p=[x['net_pnl_pct'] for x in rows];w=[x for x in p if x>0];loss=[x for x in p if x<0]
 return {'n':len(rows),'gross_wr_pct':round(100*len(w)/len(rows),4) if rows else 0,'avg_net_pnl_pct':round(sum(p)/len(rows),4) if rows else 0,'avg_win_pct':round(sum(w)/len(w),4) if w else 0,'avg_loss_pct':round(sum(loss)/len(loss),4) if loss else 0,'payoff_rr':round((sum(w)/len(w))/abs(sum(loss)/len(loss)),4) if w and loss else 0,'profit_factor':round(sum(w)/abs(sum(loss)),4) if loss else 0,'total_net_pnl_pct':round(sum(p),4),'exit_counts':dict(Counter(x['reason'] for x in rows))}
def main()->None:
 source,oracle=json.loads(V530.read_text()),json.loads(V531.read_text())
 if not source.get('support_gate_pass') or not oracle.get('oracle_pass') or source.get('outcomes_opened') or oracle.get('outcomes_opened'):raise RuntimeError('pre-outcome contracts failed')
 with Path(source['artifacts']['seeds']).open(newline='',encoding='utf8') as h:seeds=list(csv.DictReader(h))
 seeds.sort(key=lambda x:(x['entry_eligible_date'],x['symbol'],int(x['sos_idx'])));cache={};busy={};closed=[];open_data=[];skips=Counter()
 for seed in seeds:
  sym=seed['symbol'];ed=seed['entry_eligible_date']
  if busy.get(sym,'')>=ed:skips['SYMBOL_ALREADY_OPEN']+=1;continue
  result=replay(seed,cache.setdefault(sym,load(sym)))
  if result['status']=='SKIP':skips[result['reason']]+=1;continue
  if result['status']=='OPEN_DATA':open_data.append({**seed,**result});skips[result['reason']]+=1;continue
  row={**seed,**result};closed.append(row);busy[sym]=row['exit_date']
 overall=metrics(closed);yearly={y:metrics([x for x in closed if x['entry_date'].startswith(y)]) for y in YEARS}
 inv={'seed_count_matches_oracle':len(seeds)==oracle['generator_seed_count']==oracle['oracle_seed_count'],'all_entries_after_reaccept':all(x['entry_eligible_date']>x['reaccept_date'] for x in closed),'all_targets_visible_pre_reaccept':all(x['target_swing_date']<x['reaccept_date'] for x in closed),'t1_violations':sum(x['same_day_exit_violation'] for x in closed),'duplicate_symbol_entry':len(closed)-len({(x['symbol'],x['entry_date']) for x in closed}),'all_production_writes_false':True}
 checks={'n>=300':overall['n']>=GATE['n_min'],'each_year_n>=40':all(yearly[y]['n']>=GATE['year_n_min'] for y in YEARS),'gross_wr>=55':overall['gross_wr_pct']>=55,'avg_net>=0.5':overall['avg_net_pnl_pct']>=.5,'pf>=1.15':overall['profit_factor']>=1.15,'payoff>=0.7':overall['payoff_rr']>=.7,'each_year_avg_net>0':all(yearly[y]['avg_net_pnl_pct']>0 for y in YEARS),'t1_violations==0':inv['t1_violations']==0,'duplicate_symbol_entry==0':inv['duplicate_symbol_entry']==0}
 OUT.mkdir(parents=True,exist_ok=True);trades=OUT/'v532_frozen_t1_trades.csv'
 if closed:
  with trades.open('w',newline='',encoding='utf8') as h:w=csv.DictWriter(h,fieldnames=list(closed[0]));w.writeheader();w.writerows(closed)
 report={'version':'V532_SOS_BACKUP_EFFORT_RESULT_FROZEN_T1_REPLAY_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'frozen_execution_contract':'eligible-day open; stop=backup low*0.99; nearest prior visible confirmed swing high above entry target; exits begin following session; SL-first collision; time20; round-trip fee0.20%; serial one-position-per-symbol','seed_count':len(seeds),'closed_trade_count':len(closed),'open_data_count':len(open_data),'skip_counts':dict(skips),'overall':overall,'yearly':yearly,'promotion_gate':GATE,'promotion_checks':checks,'invariants':inv,'promotion_gate_pass':all(checks.values()),'decision':'V532_PROMOTION_GATE_PASS__INDEPENDENT_METRIC_AUDIT_REQUIRED' if all(checks.values()) else 'V532_FROZEN_REPLAY_FAIL__CLOSE_ONTOLOGY__NO_VARIANTS','artifacts':{'out_dir':str(OUT),'trades':str(trades),'v530':str(V530),'v531':str(V531)}}
 text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v532_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
