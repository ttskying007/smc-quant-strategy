#!/usr/bin/env python3
"""V529 one-shot frozen strict-T+1 replay for the V527/V528 validated ontology."""
from __future__ import annotations
import csv,json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
V527=AUD/'v527_spring_test_effort_result_seed_gate_latest.json'; V528=AUD/'v528_spring_test_effort_result_independent_oracle_latest.json'
OUT=AUD/f'v529_spring_test_effort_result_frozen_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'; LATEST=AUD/'v529_spring_test_effort_result_frozen_t1_replay_latest.json'
STOP_BUFFER=.99; MAX_HOLD=20; FEE=.20; YEARS=('2023','2024','2025','2026')
GATE={'n_min':300,'year_n_min':40,'gross_wr_pct_min':55.0,'avg_net_pnl_pct_min':.5,'pf_min':1.15,'payoff_min':.7,'year_avg_net_pnl_pct_min':0.0}

def num(x:Any)->float|None:
    try:
        y=float(x); return y if y>0 else None
    except (TypeError,ValueError): return None

def day(x:Any)->str:
    x=''.join(c for c in str(x or '') if c.isdigit()); return x[:8] if len(x)>=8 else ''
def load(symbol:str)->list[dict[str,Any]]:
    code,ex=symbol.split('.')
    try: src=json.loads((KDIR/f'{code}_{ex}_daily_750.json').read_text())
    except Exception:return []
    out=[]
    for r in src if isinstance(src,list) else []:
        d=day(r.get('t') or r.get('date')); vals=[num(r.get(k)) for k in ('o','h','l','c')]
        if d and all(x is not None for x in vals):out.append(dict(zip(('o','h','l','c'),vals))|{'t':d})
    return sorted(out,key=lambda x:x['t'])
def high_pivot(b:list[dict[str,Any]],i:int)->bool:
    return i>=3 and i+3<len(b) and all(b[i]['h']>b[k]['h'] for k in range(i-3,i)) and all(b[i]['h']>=b[k]['h'] for k in range(i+1,i+4))
def target(b:list[dict[str,Any]],spring:int,entry:float)->tuple[int,float]|None:
    for i in range(spring-4,2,-1):
        if high_pivot(b,i) and b[i]['h']>entry:return i,b[i]['h']
    return None
def pct(x:float,b:float)->float:return (x/b-1)*100

def replay(seed:dict[str,str],b:list[dict[str,Any]])->dict[str,Any]:
    pos={x['t']:i for i,x in enumerate(b)}; ed=seed['entry_eligible_date']; sd=seed['spring_date']
    if ed not in pos or sd not in pos:return {'status':'SKIP','reason':'SEED_DATE_NOT_IN_CACHE'}
    entry_i,spring_i=pos[ed],pos[sd]
    if not spring_i<entry_i:return {'status':'SKIP','reason':'INVALID_EVENT_ORDER'}
    entry=b[entry_i]['o']; stop=float(seed['spring_low'])*STOP_BUFFER
    if stop>=entry:return {'status':'SKIP','reason':'INVALID_STRUCTURAL_STOP'}
    t=target(b,spring_i,entry)
    if t is None:return {'status':'SKIP','reason':'NO_VISIBLE_UPSIDE_TARGET'}
    ti,tp=t; path=b[entry_i+1:entry_i+1+MAX_HOLD]
    if not path:return {'status':'OPEN_DATA','reason':'NO_POST_ENTRY_BAR'}
    for hold,bar in enumerate(path,1):
        if bar['o']<=stop: price,reason=bar['o'],'GAP_SL';break
        if bar['l']<=stop: price,reason=stop,'SL';break
        if bar['h']>=tp: price,reason=tp,'TP_STRUCTURAL';break
    else:
        if len(path)<MAX_HOLD:return {'status':'OPEN_DATA','reason':'INSUFFICIENT_FORWARD_BARS'}
        hold=len(path);bar=path[-1];price,reason=bar['c'],'TIME20'
    return {'status':'CLOSED','reason':reason,'entry_date':ed,'entry_price':round(entry,6),'exit_date':bar['t'],'exit_price':round(price,6),'stop':round(stop,6),'target':round(tp,6),'target_swing_idx':ti,'target_swing_date':b[ti]['t'],'hold_bars':hold,'gross_pnl_pct':round(pct(price,entry),6),'net_pnl_pct':round(pct(price,entry)-FEE,6),'same_day_exit_violation':ed==bar['t']}
def stats(rows:list[dict[str,Any]])->dict[str,Any]:
    p=[r['net_pnl_pct'] for r in rows];w=[x for x in p if x>0];l=[x for x in p if x<0]
    return {'n':len(rows),'gross_wr_pct':round(len(w)*100/len(rows),4) if rows else 0,'avg_net_pnl_pct':round(sum(p)/len(p),4) if p else 0,'avg_win_pct':round(sum(w)/len(w),4) if w else 0,'avg_loss_pct':round(sum(l)/len(l),4) if l else 0,'payoff_rr':round((sum(w)/len(w))/abs(sum(l)/len(l)),4) if w and l else 0,'profit_factor':round(sum(w)/abs(sum(l)),4) if l else 0,'total_net_pnl_pct':round(sum(p),4),'exit_counts':dict(Counter(r['reason'] for r in rows))}
def main()->None:
    OUT.mkdir(parents=True,exist_ok=True); a=json.loads(V527.read_text());o=json.loads(V528.read_text())
    if not a.get('support_gate_pass') or not o.get('oracle_pass') or a.get('outcomes_opened') or o.get('outcomes_opened'):raise RuntimeError('pre-outcome gate failed')
    seeds=list(csv.DictReader(open(a['artifacts']['seeds'],newline='')));seeds.sort(key=lambda x:(x['entry_eligible_date'],x['symbol'],int(x['spring_idx'])))
    cache={};busy={};closed=[];skips=Counter();open_rows=[]
    for seed in seeds:
        sym=seed['symbol']; ed=seed['entry_eligible_date']
        if busy.get(sym,'')>=ed:skips['SYMBOL_ALREADY_OPEN']+=1;continue
        x=replay(seed,cache.setdefault(sym,load(sym)))
        if x['status']=='SKIP':skips[x['reason']]+=1;continue
        if x['status']=='OPEN_DATA':open_rows.append({**seed,**x});skips[x['reason']]+=1;continue
        rec={**seed,**x};closed.append(rec);busy[sym]=x['exit_date']
    overall=stats(closed);yearly={y:stats([r for r in closed if r['entry_date'].startswith(y)]) for y in YEARS}
    inv={'all_entries_after_sos':all(r['entry_eligible_date']>r['sos_date'] for r in closed),'all_targets_before_spring':all(r['target_swing_date']<r['spring_date'] for r in closed),'t1_violations':sum(r['same_day_exit_violation'] for r in closed),'duplicate_symbol_entry':len(closed)-len({(r['symbol'],r['entry_date']) for r in closed}),'production_writes_false':True}
    checks={'n>=300':overall['n']>=300,'each_year_n>=40':all(yearly[y]['n']>=40 for y in YEARS),'gross_wr>=55':overall['gross_wr_pct']>=55,'avg_net>=0.5':overall['avg_net_pnl_pct']>=.5,'pf>=1.15':overall['profit_factor']>=1.15,'payoff>=0.7':overall['payoff_rr']>=.7,'each_year_avg_net>0':all(yearly[y]['avg_net_pnl_pct']>0 for y in YEARS),'t1_violations==0':inv['t1_violations']==0,'duplicate_symbol_entry==0':inv['duplicate_symbol_entry']==0}
    fields=list(closed[0]) if closed else [];csvp=OUT/'v529_frozen_t1_trades.csv'
    if fields:
        with csvp.open('w',newline='',encoding='utf8') as h:w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(closed)
    report={'version':'V529_SPRING_TEST_EFFORT_RESULT_FROZEN_T1_REPLAY_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'frozen_execution_contract':'eligible-day open; stop=spring low*0.99; nearest prior visible confirmed swing high target; exits begin following session; SL-first collision; time20; round-trip fee0.20%; serial one-position-per-symbol','seed_count':len(seeds),'closed_trade_count':len(closed),'open_data_count':len(open_rows),'nontradable_or_serial_skip_counts':dict(skips),'overall':overall,'yearly':yearly,'promotion_gate':GATE,'promotion_checks':checks,'invariants':inv,'promotion_gate_pass':all(checks.values()),'decision':'V529_PROMOTION_GATE_PASS__SCANNER_TIME_CONTRACT_REQUIRED' if all(checks.values()) else 'V529_FROZEN_REPLAY_FAIL__CLOSE_ONTOLOGY__NO_VARIANTS','artifacts':{'out_dir':str(OUT),'trades':str(csvp),'v527':str(V527),'v528':str(V528)}}
    text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v529_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
