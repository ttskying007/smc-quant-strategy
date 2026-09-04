#!/usr/bin/env python3
"""One frozen strict-T+1 replay for V585 after V586 exact oracle equality."""
from __future__ import annotations
import csv, json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from v579_v577_frozen_strict_t1_replay import bars, structural_target, exit_trade, metrics

ROOT=Path('/root/.hermes'); AUDIT=ROOT/'smc_audit'
SEED=AUDIT/'v585_insider_reduction_plan_ssl_exhaustion_seed_latest.json'
ORACLE=AUDIT/'v586_v585_independent_raw_oracle_latest.json'
LATEST=AUDIT/'v587_v585_frozen_strict_t1_replay_latest.json'
OUT=AUDIT/f'v587_v585_frozen_strict_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
YEARS=('2023','2024','2025'); FEE,HOLD=0.20,20
GATE={'n_min':1000,'year_n_min':300,'wr_pct_min':55.0,'avg_net_pct_min':0.5,'pf_min':1.15,'payoff_min':0.7,'each_year_avg_net_positive':True,'t1_violations':0}

def main():
    oracle=json.loads(ORACLE.read_text())
    if oracle['decision']!='V586_ORACLE_PASS__ONE_FROZEN_STRICT_T1_REPLAY_AUTHORIZED': raise RuntimeError('V586 exact oracle equality required')
    meta=json.loads(SEED.read_text())
    with Path(meta['artifacts']['seeds']).open(encoding='utf-8',newline='') as h: seeds=list(csv.DictReader(h))
    grouped=defaultdict(list)
    for x in seeds: grouped[x['symbol']].append(x)
    OUT.mkdir(parents=True,exist_ok=False); trades=[]; skipped=Counter()
    for n,(symbol,items) in enumerate(sorted(grouped.items()),1):
        xs=bars(symbol); ix={x['d']:i for i,x in enumerate(xs)}; busy=-1
        for seed in sorted(items,key=lambda x:(x['planned_entry_date'],x['event_date'])):
            signal,entry_i=ix.get(seed['reclaim_date']),ix.get(seed['planned_entry_date'])
            if signal is None or entry_i is None or entry_i!=signal+1: skipped['NO_EXACT_RECLAIM_NEXT_OPEN']+=1; continue
            if entry_i<=busy: skipped['SERIAL_SYMBOL_POSITION_OPEN']+=1; continue
            if entry_i+1>=len(xs): skipped['NO_T1_FORWARD_BAR']+=1; continue
            entry,stop=xs[entry_i]['o'],float(seed['zone_low'])*.99
            if not 0<stop<entry: skipped['INVALID_STRUCTURAL_STOP']+=1; continue
            target=structural_target(xs,signal,entry,stop)
            if target is None: skipped['NO_UNCONSUMED_PREENTRY_TARGET_RR_1P5']+=1; continue
            exit_i,exit_date,exit_price,reason=exit_trade(xs,entry_i,entry,stop,target)
            if exit_i<=entry_i: raise RuntimeError('strict T+1 violation')
            busy=exit_i
            trades.append({'symbol':symbol,'event_date':seed['event_date'],'signal_date':seed['reclaim_date'],'entry_date':xs[entry_i]['d'],'entry_price':round(entry,8),'stop_price':round(stop,8),'target_price':round(target,8),'planned_rr':round((target-entry)/(entry-stop),6),'exit_date':exit_date,'exit_price':round(exit_price,8),'exit_reason':reason,'hold_bars':exit_i-entry_i,'net_pnl_pct':round((exit_price/entry-1)*100-FEE,6),'execution_contract':'PIT_REDUCTION_PLAN_D_PRIOR>SSL_EXHAUSTION>BSL_BREAK>DEMAND_RECLAIM>D_PLUS_1_OPEN>STRICT_T1_STRUCTURE_SL_TP_TIME20_FEE0P2'})
        if n%500==0: print(json.dumps({'symbols':n,'trades':len(trades)}),flush=True)
    overall=metrics(trades); yearly={y:metrics([x for x in trades if x['entry_date'].startswith(y)]) for y in YEARS}; exits=Counter(x['exit_reason'] for x in trades)
    checks={'n>=1000':overall['n']>=GATE['n_min'],'each_year_n>=300':all(yearly[y]['n']>=GATE['year_n_min'] for y in YEARS),'wr>=55':overall['wr_pct']>=GATE['wr_pct_min'],'avg_net>=0.5':overall['avg_net_pct']>=GATE['avg_net_pct_min'],'pf>=1.15':(overall['profit_factor'] or 0)>=GATE['pf_min'],'payoff>=0.7':(overall['payoff'] or 0)>=GATE['payoff_min'],'each_year_avg_net>0':all(yearly[y]['avg_net_pct']>0 for y in YEARS),'t1_violations==0':True}
    path=OUT/'v587_frozen_t1_trades.csv'
    with path.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=list(trades[0]) if trades else ['symbol']);w.writeheader();w.writerows(trades)
    passed=all(checks.values())
    report={'version':'V587_V585_ONE_FROZEN_STRICT_T1_REPLAY','generated_at':datetime.now().isoformat(timespec='seconds'),'research_only':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'input_contract':'V585 outcome-blind reduction-plan+SMC seeds after V586 exact independent raw Oracle identity equality.','frozen_execution_contract':'entry=first daily open after reclaim; stop=demand POI low*0.99; target=nearest unconsumed pre-entry right-confirmed daily swing high RR>=1.5; exits start entry+1 only; gap-aware conservative stop-first collision; time20; fee0.20%; serial positions.','seed_count':len(seeds),'closed_trade_count':len(trades),'skip_counts':dict(skipped),'overall':overall,'yearly':yearly,'exit_reason_counts':dict(exits),'promotion_gate':GATE,'promotion_checks':checks,'invariants':{'oracle_identity_pass':True,'all_targets_preentry':all(x['planned_rr']>=1.5 for x in trades),'t1_violations':0,'all_writes_false':True,'search_count':1},'decision':'V587_RESEARCH_GATE_PASS__INDEPENDENT_METRIC_AUDIT_REQUIRED' if passed else 'V587_FROZEN_REPLAY_GATE_FAIL__CLOSE_V585_ONTOLOGY_NO_VARIANTS','artifacts':{'out_dir':str(OUT),'trades':str(path),'latest':str(LATEST),'v585':str(SEED),'v586':str(ORACLE)}}
    text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v587_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
