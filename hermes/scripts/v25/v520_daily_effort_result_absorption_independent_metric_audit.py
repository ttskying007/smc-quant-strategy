#!/usr/bin/env python3
"""V520 independent raw-bar metric/audit replay for V519.

Separate implementation; no imports from V519. It recomputes visible targets,
serial strict-T+1 exits, and all economics from V517 outcome-blind seeds, then
compares causal execution keys and metrics against V519's frozen trade ledger.
"""
from __future__ import annotations
import csv,json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; KD=ROOT/'kline_cache'
V517=AUD/'v517_daily_effort_result_absorption_seed_gate_latest.json'
V519=AUD/'v519_daily_effort_result_absorption_frozen_t1_replay_latest.json'
OUT=AUD/f'v520_daily_effort_result_absorption_independent_metric_audit_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST=AUD/'v520_daily_effort_result_absorption_independent_metric_audit_latest.json'
BUFFER=0.99; LEFT=RIGHT=3; HOLD=20; COST=0.20; YEARS=('2023','2024','2025','2026')


def val(x:Any):
    try:
        x=float(x); return x if x>0 else None
    except (TypeError,ValueError):return None

def keydate(x:Any):
    s=''.join(c for c in str(x or '') if c.isdigit());return s[:8] if len(s)>=8 else ''
def data(sym:str):
    code,ex=sym.split('.'); p=KD/f'{code}_{ex}_daily_750.json'
    try: raw=json.loads(p.read_text())
    except Exception:return []
    ans=[]
    for r in raw if isinstance(raw,list) else []:
        d=keydate(r.get('t') or r.get('date') or r.get('day')); z=[val(r.get(k)) for k in ('o','h','l','c')]
        if d and all(v is not None for v in z):ans.append({'d':d,'o':z[0],'h':z[1],'l':z[2],'c':z[3]})
    return sorted(ans,key=lambda x:x['d'])
def high_confirmed(b,j):
    if j<LEFT or j+RIGHT>=len(b):return False
    return b[j]['h']>max(b[x]['h'] for x in range(j-LEFT,j)) and b[j]['h']>=max(b[x]['h'] for x in range(j+1,j+RIGHT+1))
def prior_target(b,sweep,response,entry):
    # A structural target must still be above the completed response bar's high.
    # Otherwise the response already consumed that liquidity before entry.
    minimum_target=max(entry,b[response]['h'])
    possible=[j for j in range(LEFT,sweep-RIGHT) if high_confirmed(b,j) and b[j]['h']>minimum_target]
    if not possible:return None
    j=max(possible);return j,b[j]['h']
def pc(x,b):return 100*(x/b-1)
def execute(seed,b):
    by_date={bar['d']:index for index,bar in enumerate(b)}
    entry_date,sweep_date=seed['entry_eligible_date'],seed['sweep_date']
    if entry_date not in by_date or sweep_date not in by_date:return None,'SEED_DATE_NOT_IN_CACHE'
    e,s=by_date[entry_date],by_date[sweep_date]
    if not s<e:return None,'INVALID_SEED_DATE_ORDER'
    entry=b[e]['o']; stop=float(seed['sweep_low'])*BUFFER; target=prior_target(b,s,e-1,entry)
    if stop>=entry:return None,'INVALID_STOP'
    if target is None:return None,'NO_VISIBLE_UPSIDE_TARGET'
    tj,tp=target; path=b[e+1:e+1+HOLD]
    if len(path)<HOLD:return None,'OPEN_DATA'
    # Deliberately enumerate path separately, but same predeclared conservative policy.
    reason='TIME20'; exitbar=path[-1]; price=exitbar['c']
    for n,bar in enumerate(path,1):
        if bar['o']<=stop:
            reason='GAP_SL'; exitbar=bar;price=bar['o'];break
        elif bar['l']<=stop:
            reason='SL';exitbar=bar;price=stop;break
        elif bar['h']>=tp:
            reason='TP_STRUCTURAL';exitbar=bar;price=tp;break
    gross=pc(price,entry); risk=entry-stop
    return {'symbol':seed['symbol'],'sweep_date':seed['sweep_date'],'entry_date':b[e]['d'],'exit_date':exitbar['d'],'reason':reason,'entry_price':round(entry,6),'exit_price':round(price,6),'target':round(tp,6),'target_swing_idx':tj,'target_swing_date':b[tj]['d'],'net_pnl_pct':round(gross-COST,6),'mfe_pct':round(pc(max(x['h'] for x in path),entry),6),'mae_pct':round(pc(min(x['l'] for x in path),entry),6),'mfe_r':round((max(x['h'] for x in path)-entry)/risk,6),'mae_r':round((min(x['l'] for x in path)-entry)/risk,6),'same_day_exit_violation':b[e]['d']==exitbar['d']},None
def measures(rows):
    pnl=[r['net_pnl_pct'] for r in rows];win=[x for x in pnl if x>0];loss=[x for x in pnl if x<0]
    return {'n':len(rows),'gross_wr_pct':round(100*len(win)/len(rows),4) if rows else 0,'avg_net_pnl_pct':round(sum(pnl)/len(rows),4) if rows else 0,'profit_factor':round(sum(win)/abs(sum(loss)),4) if loss else 0,'payoff_rr':round((sum(win)/len(win))/abs(sum(loss)/len(loss)),4) if win and loss else 0,'exit_counts':dict(Counter(r['reason'] for r in rows))}
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    g=json.loads(V517.read_text()); p=json.loads(V519.read_text())
    if not p.get('promotion_gate_pass'):
        report={'version':'V520_DAILY_EFFORT_RESULT_ABSORPTION_INDEPENDENT_METRIC_AUDIT_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'audit_pass':False,'blocked_by_v519_gate':True,'v519_promotion_checks':p.get('promotion_checks',{}),'decision':'V520_BLOCKED__V519_FROZEN_GATE_FAILED__NO_STALE_AUDIT_REUSE','artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'v517':str(V517),'v519':str(V519)}}
        text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v520_report.json').write_text(text);LATEST.write_text(text);print(text);return
    with Path(g['artifacts']['seeds']).open(newline='') as h:seeds=list(csv.DictReader(h))
    seeds.sort(key=lambda x:(x['entry_eligible_date'],x['symbol'],int(x['sweep_idx'])))
    cache={};busy={}; actual=[]; skips=Counter()
    for seed in seeds:
        sym=seed['symbol']
        if busy.get(sym,'')>=seed['entry_eligible_date']:
            skips['SYMBOL_ALREADY_OPEN']+=1;continue
        b=cache.setdefault(sym,data(sym)); r,why=execute(seed,b)
        if r is None:skips[why]+=1;continue
        actual.append(r);busy[sym]=r['exit_date']
    with Path(p['artifacts']['trades']).open(newline='') as h: reported=list(csv.DictReader(h))
    def compact(r):return (r['symbol'],r['sweep_date'],r['entry_date'],r['exit_date'],r['reason'],round(float(r['entry_price']),6),round(float(r['exit_price']),6),round(float(r['net_pnl_pct']),6))
    ac={compact(r) for r in actual}; rp={compact(r) for r in reported}
    overall=measures(actual); yearly={y:measures([r for r in actual if r['entry_date'][:4]==y]) for y in YEARS}
    source_overall=p['overall']; metric_delta={k:round(overall[k]-source_overall[k],8) for k in ('n','gross_wr_pct','avg_net_pnl_pct','profit_factor','payoff_rr')}
    inv={'exact_trade_set_match':ac==rp,'missing_from_independent_count==0':len(rp-ac)==0,'extra_from_independent_count==0':len(ac-rp)==0,'all_t1_clean':not any(r['same_day_exit_violation'] for r in actual),'all_targets_visible_pre_sweep':all(r['target_swing_date']<r['sweep_date'] for r in actual),'all_metric_deltas_zero':all(abs(v)<1e-7 for v in metric_delta.values())}
    report={'version':'V520_DAILY_EFFORT_RESULT_ABSORPTION_INDEPENDENT_METRIC_AUDIT_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'independent_overall':overall,'independent_yearly':yearly,'v519_overall':source_overall,'metric_delta':metric_delta,'independent_skip_counts':dict(skips),'invariants':inv,'audit_pass':all(inv.values()),'decision':'V520_INDEPENDENT_AUDIT_PASS__SCANNER_TIME_CONTRACT_NEXT' if all(inv.values()) else 'V520_INDEPENDENT_AUDIT_FAIL__BLOCK_PROMOTION','artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'v517':str(V517),'v519':str(V519)}}
    text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v520_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
