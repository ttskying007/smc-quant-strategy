#!/usr/bin/env python3
"""V699 single frozen strict-T+1 replay for V697 effort-result absorption.

Execution contract, frozen before outcomes:
- execute at the eligible session open;
- stop = sweep low * 0.99 (structural sweep-failure buffer);
- target = nearest *already visible* prior confirmed swing high above entry;
- no same-day exit: evaluate exits from the following session only;
- conservative intraday collision ordering: stop before target;
- time exit at the 20th eligible post-entry close; round-trip cost 0.20%;
- one serial position per symbol (later signals while occupied are skipped).

No threshold, stop, target, or holding-period alternatives are evaluated.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from backtest_period_report import write_period_reports

ROOT=Path('/root/.hermes')
KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
V697=AUD/'v697_pure_smc_ssl_reclaim_seed_gate_latest.json'
V698=AUD/'v698_pure_smc_ssl_reclaim_oracle_latest.json'
OUT=AUD/f'v699_pure_smc_ssl_reclaim_frozen_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST=AUD/'v699_pure_smc_ssl_reclaim_replay_latest.json'
LEFT=RIGHT=3; STOP_BUFFER=0.99; MAX_HOLD=20; FEE_PCT=0.20
YEARS=('2023','2024','2025','2026')
# Release gates are fixed safety requirements.  Per-year checks prevent an
# aggregate result or a single favourable regime from licensing production.
GATE={
    'n_min':300,
    'yearly_n_min':300,
    'yearly_avg_net_pnl_pct_min_exclusive':0.0,
    'monthly_trade_count_min_exclusive':4,
    'gross_wr_pct_min':55.0,
    'avg_net_pnl_pct_min':0.5,
    'pf_min':1.15,
    'payoff_min':0.7,
}


def num(x:Any)->float|None:
    try:
        v=float(x); return v if v>0 else None
    except (TypeError,ValueError): return None

def day(x:Any)->str:
    s=''.join(c for c in str(x or '') if c.isdigit()); return s[:8] if len(s)>=8 else ''

def load_bars(symbol:str)->list[dict[str,Any]]:
    code,ex=symbol.split('.')
    p=KDIR/f'{code}_{ex}_daily_750.json'
    try:data=json.loads(p.read_text())
    except Exception:return []
    out=[]
    for r in data if isinstance(data,list) else []:
        d=day(r.get('t') or r.get('date') or r.get('day'))
        o,h,l,c=(num(r.get(k)) for k in ('o','h','l','c'))
        if d and None not in(o,h,l,c):out.append({'t':d,'o':o,'h':h,'l':l,'c':c})
    return sorted(out,key=lambda x:x['t'])

def high_pivot(b:list[dict[str,Any]],j:int)->bool:
    if j-LEFT<0 or j+RIGHT>=len(b):return False
    h=b[j]['h']
    return all(h>b[k]['h'] for k in range(j-LEFT,j)) and all(h>=b[k]['h'] for k in range(j+1,j+RIGHT+1))

def visible_target(b:list[dict[str,Any]], sweep_idx:int, response_idx:int, entry:float)->tuple[int,float]|None:
    # A pivot is visible by sweep time only if all RIGHT bars were completed before sweep.
    # Its liquidity must also remain unbroken through the response bar; an already
    # consumed swing high is not an upside structural target.
    minimum_target = max(entry, b[response_idx]['h'])
    for j in range(sweep_idx-RIGHT-1, LEFT-1, -1):
        if high_pivot(b,j) and b[j]['h']>minimum_target:
            return j,b[j]['h']
    return None

def pct(x:float,base:float)->float:return (x/base-1.0)*100.0

def replay(row:dict[str,str], b:list[dict[str,Any]])->dict[str,Any]:
    # Persisted bar indices are cache-relative: the rolling 750-bar cache moves
    # whenever a new session arrives. Rebind every frozen event to its immutable
    # trading date before accessing current raw bars; never reinterpret an old
    # index as a new event.
    by_date={bar['t']:index for index,bar in enumerate(b)}
    entry_date, sweep_date=row['entry_eligible_date'],row['sweep_date']
    if entry_date not in by_date or sweep_date not in by_date:
        return {'status':'SKIP','reason':'SEED_DATE_NOT_IN_CACHE'}
    idx, sweep_idx=by_date[entry_date],by_date[sweep_date]
    if not sweep_idx < idx:
        return {'status':'SKIP','reason':'INVALID_SEED_DATE_ORDER'}
    entry=b[idx]['o']; stop=float(row['sweep_low'])*STOP_BUFFER
    if stop>=entry:return {'status':'SKIP','reason':'INVALID_STRUCTURAL_STOP'}
    target_info=visible_target(b,sweep_idx,idx-1,entry)
    if target_info is None:return {'status':'SKIP','reason':'NO_VISIBLE_UPSIDE_TARGET'}
    target_idx,target=target_info
    if target<=entry:return {'status':'SKIP','reason':'TARGET_NOT_ABOVE_ENTRY'}
    risk=entry-stop
    path=b[idx+1:idx+1+MAX_HOLD] # strict A-share: no entry-session exit.
    if not path:return {'status':'OPEN_DATA','reason':'NO_POST_ENTRY_BAR','entry_date':b[idx]['t'],'entry_price':entry,'stop':stop,'target':target}
    best=max(x['h'] for x in path); worst=min(x['l'] for x in path)
    for hold,bar in enumerate(path,1):
        if bar['o']<=stop:
            exit_price=bar['o']; reason='GAP_SL'; break
        if bar['l']<=stop:
            exit_price=stop; reason='SL'; break
        if bar['h']>=target:
            exit_price=target; reason='TP_STRUCTURAL'; break
    else:
        if len(path)<MAX_HOLD:
            return {'status':'OPEN_DATA','reason':'INSUFFICIENT_FORWARD_BARS','entry_date':b[idx]['t'],'entry_price':entry,'stop':stop,'target':target,'hold_bars':len(path),'mark_date':path[-1]['t'],'mark_price':path[-1]['c'],'mfe_pct':pct(best,entry),'mae_pct':pct(worst,entry)}
        bar=path[-1]; hold=MAX_HOLD; exit_price=bar['c']; reason='TIME20'
    gross=pct(exit_price,entry); net=gross-FEE_PCT
    return {'status':'CLOSED','reason':reason,'entry_date':b[idx]['t'],'entry_price':round(entry,6),'exit_date':bar['t'],'exit_price':round(exit_price,6),'stop':round(stop,6),'target':round(target,6),'target_swing_idx':target_idx,'target_swing_date':b[target_idx]['t'],'hold_bars':hold,'gross_pnl_pct':round(gross,6),'net_pnl_pct':round(net,6),'mfe_pct':round(pct(best,entry),6),'mae_pct':round(pct(worst,entry),6),'mfe_r':round((best-entry)/risk,6),'mae_r':round((worst-entry)/risk,6),'same_day_exit_violation':b[idx]['t']==bar['t']}

def stats(rows:list[dict[str,Any]])->dict[str,Any]:
    pnl=[r['net_pnl_pct'] for r in rows]; wins=[x for x in pnl if x>0]; losses=[x for x in pnl if x<0]
    gross=sum(wins); loss_abs=abs(sum(losses))
    return {'n':len(rows),'gross_wr_pct':round(100*len(wins)/len(rows),4) if rows else 0.0,'avg_net_pnl_pct':round(sum(pnl)/len(rows),4) if rows else 0.0,'avg_win_pct':round(sum(wins)/len(wins),4) if wins else 0.0,'avg_loss_pct':round(sum(losses)/len(losses),4) if losses else 0.0,'payoff_rr':round((sum(wins)/len(wins))/abs(sum(losses)/len(losses)),4) if wins and losses else 0.0,'profit_factor':round(gross/loss_abs,4) if loss_abs else 0.0,'total_net_pnl_pct':round(sum(pnl),4),'exit_counts':dict(Counter(r['reason'] for r in rows))}

def monthly_trade_count_gate(rows:list[dict[str,Any]])->tuple[dict[str,Any],bool]:
    # The sample-count gate is monthly, not yearly. Include zero-trade calendar
    # months between the first and last closed entry so sparse months cannot be
    # hidden by omitting them from the ledger aggregation.
    months=Counter(r['entry_date'][:6] for r in rows)
    start,end=min(months,default=''),max(months,default='')
    observed=[]
    if start and end:
        year,month=int(start[:4]),int(start[4:])
        while f'{year:04d}{month:02d}'<=end:
            observed.append(f'{year:04d}{month:02d}')
            year,month=(year+1,1) if month==12 else (year,month+1)
    counts={month:months[month] for month in observed}
    failed=[month for month,count in counts.items() if count<=4]
    detail={'entry_month_start':start,'entry_month_end':end,'months_checked':observed,'monthly_trade_counts':counts,'failed_months_n<=4':failed,'min_monthly_trade_count':min(counts.values(),default=0),'rule':'every completed entry month from the first through the last closed entry requires trade_count > 4; zero-trade months inside that interval fail'}
    return detail,not failed

def main()->None:
    OUT.mkdir(parents=True,exist_ok=True)
    g=json.loads(V697.read_text()); o=json.loads(V698.read_text())
    if not g.get('support_gate_pass') or not o.get('oracle_pass') or o.get('outcomes_opened'):
        raise RuntimeError('V697/V698 gates not satisfied; frozen replay blocked')
    with Path(g['artifacts']['seeds']).open(newline='') as h:seeds=list(csv.DictReader(h))
    seeds.sort(key=lambda r:(r['entry_eligible_date'],r['symbol'],int(r['sweep_idx'])))
    bars_cache={}; busy_until:dict[str,str]={}; executed=[]; skipped=Counter(); open_data=[]
    for r in seeds:
        sym=r['symbol']; entry_date=r['entry_eligible_date']
        if busy_until.get(sym,'')>=entry_date:
            skipped['SYMBOL_ALREADY_OPEN']+=1; continue
        b=bars_cache.setdefault(sym,load_bars(sym))
        x=replay(r,b)
        if x['status']=='SKIP':skipped[x['reason']]+=1; continue
        record={**r,**x}
        if x['status']=='OPEN_DATA':open_data.append(record); skipped[x['reason']]+=1; continue
        executed.append(record); busy_until[sym]=x['exit_date']
    overall=stats(executed); yearly={y:stats([r for r in executed if r['entry_date'][:4]==y]) for y in YEARS}
    invariant={'seed_count_matches_oracle':g['seed_count']==o['generator_seed_count']==o['oracle_seed_count'],'all_entries_strictly_after_response':all(r['entry_eligible_date']>r['response_date'] for r in executed),'t1_violations':sum(bool(r['same_day_exit_violation']) for r in executed),'all_structural_targets_prior_to_sweep':all(r['target_swing_idx']<int(r['sweep_idx']) for r in executed),'all_production_writes_false':True}
    monthly_gate,monthly_trade_count_pass=monthly_trade_count_gate(executed)
    promotion={
        'n>=300':overall['n']>=GATE['n_min'],
        'each_year_n>=300':all(yearly[y]['n']>=GATE['yearly_n_min'] for y in YEARS),
        'each_year_avg_net>0':all(yearly[y]['avg_net_pnl_pct']>GATE['yearly_avg_net_pnl_pct_min_exclusive'] for y in YEARS),
        'each_month_n>4':monthly_trade_count_pass,
        'gross_wr>=55':overall['gross_wr_pct']>=GATE['gross_wr_pct_min'],
        'avg_net>=0.5':overall['avg_net_pnl_pct']>=GATE['avg_net_pnl_pct_min'],
        'pf>=1.15':overall['profit_factor']>=GATE['pf_min'],
        'payoff>=0.7':overall['payoff_rr']>=GATE['payoff_min'],
        't1_violations==0':invariant['t1_violations']==0,
    }
    csv_path=OUT/'v699_frozen_t1_trades.csv'; fields=list(executed[0].keys()) if executed else []
    if fields:
        with csv_path.open('w',newline='',encoding='utf-8') as h:
            w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(executed)
    period_artifacts = write_period_reports(
        executed, out_dir=OUT, stem='v699', engine='V699_FROZEN_STRICT_T1_REPLAY',
        input_ledger=str(csv_path), contract='eligible-day open; structural stop/target fixed before entry; exits begin following session; strict T+1',
    )
    report={'version':'V699_PURE_SMC_SSL_RECLAIM_FROZEN_T1_REPLAY_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'frozen_execution_contract':'eligible-day open; stop=sweep low*0.99; nearest prior visible confirmed swing high target; exits begin following session; SL-first collision; time20; round-trip fee0.20%; serial one-position-per-symbol','source_contract':'confirmed unmitigated SSL -> price sweep and reclaim -> next completed close breaks sweep high -> following open eligible; volume diagnostic-only','seed_count':len(seeds),'closed_trade_count':len(executed),'open_data_count':len(open_data),'nontradable_or_serial_skip_counts':dict(skipped),'overall':overall,'yearly':yearly,'promotion_gate':GATE,'monthly_trade_count_gate':monthly_gate,'monthly_trade_count_gate_pass':monthly_trade_count_pass,'promotion_checks':promotion,'invariants':invariant,'promotion_gate_pass':all(promotion.values()),'decision':'V699_PROMOTION_GATE_PASS__SCANNER_TIME_CONTRACT_REQUIRED' if all(promotion.values()) else 'V699_FROZEN_REPLAY_FAIL__CLOSE_ONTOLOGY__NO_VARIANTS','artifacts':{'out_dir':str(OUT),'trades':str(csv_path),'period_metrics':period_artifacts['json'],'yearly_metrics':period_artifacts['yearly_csv'],'monthly_metrics':period_artifacts['monthly_csv'],'latest':str(LATEST),'v697':str(V697),'v698':str(V698)}}
    text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v699_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
