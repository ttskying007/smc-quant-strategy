#!/usr/bin/env python3
"""V472 closure and independent metric check for industry lead-lag direction."""
from __future__ import annotations
import csv,json,math
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes');AUD=ROOT/'smc_audit';GEN=AUD/'v469_industry_lead_stock_lag_latest.json';ORA=AUD/'v470_industry_lead_stock_lag_oracle_latest.json';REP=AUD/'v471_industry_lead_stock_lag_frozen_t1_replay_latest.json';LATEST=AUD/'v472_industry_lead_stock_lag_closure_latest.json'

def f(x):
    try:return float(x)
    except (TypeError,ValueError):return 0.0

def stats(rows):
    pnl=[f(r['net_pnl_pct']) for r in rows];wins=[x for x in pnl if x>0];loss=[x for x in pnl if x<=0]
    gross=sum(f(r['gross_pnl_pct'])>0 for r in rows)/len(rows)*100 if rows else 0
    net=sum(x>=.8 for x in pnl)/len(rows)*100 if rows else 0;aw=sum(wins)/len(wins) if wins else 0;al=sum(loss)/len(loss) if loss else 0
    sl_reasons={'STRUCTURAL_RAID_SL_T1','SL_GAP_T1','SL_TP_COLLISION_CONSERVATIVE_T1'}
    return {'n':len(rows),'gross_wr_pct':round(gross,4),'net_wr_ge_0_8_pct':round(net,4),'avg_net_pnl_pct':round(sum(pnl)/len(pnl),4) if pnl else 0,'payoff_rr':round(aw/abs(al),4) if al else 0,'profit_factor':round(sum(wins)/abs(sum(loss)),4) if loss and sum(loss) else 0,'sl_pct':round(sum(r.get('exit_reason','') in sl_reasons for r in rows)/len(rows)*100,4) if rows else 0}

def main():
    g=json.loads(GEN.read_text());o=json.loads(ORA.read_text());r=json.loads(REP.read_text());rowfile=Path(r['artifacts']['rows'])
    with rowfile.open(newline='') as h:allrows=list(csv.DictReader(h))
    rows=[x for x in allrows if x.get('status')=='CLOSED' and x.get('entry_date','')[:4] in {'2023','2024','2025','2026'}]
    overall=stats(rows);yearly={y:stats([x for x in rows if x['entry_date'][:4]==y]) for y in ('2023','2024','2025','2026')}
    keys=('n','gross_wr_pct','net_wr_ge_0_8_pct','avg_net_pnl_pct','payoff_rr','profit_factor','sl_pct')
    mismatches=[]
    for k in keys:
        if abs(f(overall[k])-f(r['overall'][k]))>1e-4:mismatches.append('overall.'+k)
    for y in yearly:
        for k in keys:
            if abs(f(yearly[y][k])-f(r['yearly'][y][k]))>1e-4:mismatches.append(y+'.'+k)
    result={'version':'V472_INDUSTRY_LEAD_STOCK_LAG_DIRECTION_CLOSURE','generated_at':datetime.now().isoformat(timespec='seconds'),'scope':'One distinct local-data temporal industry-lead -> stock-lag SSL transmission ontology; no production/frontend/watchlist writes.',
      'ontology':'INDUSTRY_LEAD_STOCK_LAG_SSL_TRANSMISSION','semantic_generation':{'seed_count':g['seed_count'],'yearly_seed_count':g['yearly_seed_count'],'semantic_order_failures':g['invariants']['semantic_order_failures'],'support_gate_pass':g['support_gate']['pass']},
      'independent_oracle':{'expected_seed_count':o['expected_seed_count'],'oracle_pass_count':o['oracle_pass_count'],'mismatch_total':o['mismatch_total'],'oracle_gate_pass':o['oracle_gate_pass']},
      'frozen_t1_replay':{'overall':r['overall'],'yearly':r['yearly'],'epochs':r['epochs'],'baseline_delta':r['comparison_to_unconditioned_turtle_soup']['delta'],'same_day_industry_smt_delta':r['comparison_to_same_day_industry_smt']['delta'],'t1_violations':r['invariants']['t1_violations'],'search_count':r['invariants']['search_count']},
      'independent_metric_recomputation':{'overall':overall,'yearly':yearly,'mismatch_fields':mismatches,'pass':not mismatches},
      'promotion_gate_pass':r['promotion_gate_pass'],'hard_findings':['Industry-first reversal before the stock raid is materially better than same-day industry SMT: AvgNet +0.8308pp, payoff +0.1953, PF +0.4289.','Aggregate n=31,830, gross WR=71.3478%, AvgNet=+0.7101%, payoff=0.6446, PF=1.3640.','The edge is not stable: 2023 AvgNet=-0.6668% and PF=0.7068; 2026 PF=1.0885 is below the frozen 1.15 gate.','Because the schema and replay were frozen before outcomes, the negative 2023 result cannot be repaired by lag/window/SL/TP/hold tuning.'],
      'production_state':'UNCHANGED_EMPTY_BOOK_FAIL_CLOSED','production_write':False,'frontend_write':False,'watchlist_write':False,
      'decision':'TEMPORAL_INDUSTRY_LEAD_HAS_REAL_AGGREGATE_INFORMATION_BUT_FAILS_ALL_YEAR_STABILITY__CLOSE_NO_VARIANTS',
      'artifacts':{'v469':str(GEN),'v470':str(ORA),'v471':str(REP),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
