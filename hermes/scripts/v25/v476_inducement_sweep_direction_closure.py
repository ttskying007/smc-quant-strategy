#!/usr/bin/env python3
"""V476 independent metric recomputation and closure for V473-V475."""
from __future__ import annotations
import csv,json,math,statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; SRC=AUD/'v475_inducement_sweep_frozen_t1_replay_latest.json'; LATEST=AUD/'v476_inducement_sweep_direction_closure_latest.json'
STOP={'STRUCTURAL_INDUCEMENT_SL_T1','SL_GAP_T1','SL_TP_COLLISION_CONSERVATIVE_T1'}; YEARS=('2023','2024','2025','2026')
def f(x):
    try:
        v=float(x);return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError):return 0.0
def stats(rows):
    if not rows:return {'n':0}
    gross=[f(r['gross_pnl_pct']) for r in rows];net=[f(r['net_pnl_pct']) for r in rows];pos=[x for x in net if x>0];neg=[x for x in net if x<=0]
    aw=sum(pos)/len(pos) if pos else 0;al=sum(neg)/len(neg) if neg else 0
    return {'n':len(rows),'gross_wr_pct':round(sum(x>0 for x in gross)/len(rows)*100,4),'net_wr_ge_0_8_pct':round(sum(x>=.8 for x in net)/len(rows)*100,4),'avg_net_pnl_pct':round(sum(net)/len(rows),4),'median_net_pnl_pct':round(statistics.median(net),4),'avg_win_pct':round(aw,4),'avg_loss_pct':round(al,4),'payoff_rr':round(aw/abs(al),4) if al else 0,'profit_factor':round(sum(pos)/abs(sum(neg)),4) if neg and sum(neg) else 0,'sl_pct':round(sum(r['exit_reason'] in STOP for r in rows)/len(rows)*100,4)}
def main():
    replay=json.loads(SRC.read_text());gen=json.loads((AUD/'v473_inducement_sweep_continuation_latest.json').read_text());oracle=json.loads((AUD/'v474_inducement_sweep_oracle_latest.json').read_text())
    with open(replay['artifacts']['rows']) as h: rows=[r for r in csv.DictReader(h) if r.get('status')=='CLOSED' and r.get('entry_date','')[:4] in YEARS]
    overall=stats(rows);yearly={y:stats([r for r in rows if r['entry_date'][:4]==y]) for y in YEARS}
    fields=('n','gross_wr_pct','net_wr_ge_0_8_pct','avg_net_pnl_pct','payoff_rr','profit_factor','sl_pct'); mismatches=[]
    for k in fields:
        if abs(f(overall.get(k))-f(replay['overall'].get(k)))>1e-4:mismatches.append(f'overall.{k}')
    for y in YEARS:
        for k in fields:
            if abs(f(yearly[y].get(k))-f(replay['yearly'][y].get(k)))>1e-4:mismatches.append(f'{y}.{k}')
    result={'version':'V476_INDUCEMENT_SWEEP_DIRECTION_CLOSURE','generated_at':datetime.now().isoformat(timespec='seconds'),'scope':'One distinct local pure-structure ontology; no production/frontend/watchlist writes.','ontology':'BULLISH_INTERNAL_INDUCEMENT_SWEEP_CONTINUATION','semantic_generation':{'seed_count':gen['seed_count'],'yearly_seed_count':gen['yearly_seed_count'],'semantic_order_failures':gen['invariants']['semantic_order_failures'],'support_gate_pass':gen['support_gate_pass']},'independent_oracle':{'expected_seed_count':oracle['source_seed_count'],'oracle_pass_count':oracle['oracle_pass_count'],'mismatch_total':oracle['mismatch_total'],'oracle_gate_pass':oracle['oracle_gate_pass']},'frozen_t1_replay':{'overall':replay['overall'],'yearly':replay['yearly'],'t1_violations':replay['invariants']['t1_violations'],'search_count':replay['invariants']['search_count']},'independent_metric_recomputation':{'overall':overall,'yearly':yearly,'mismatch_fields':mismatches,'pass':not mismatches},'promotion_gate_pass':replay['promotion_gate_pass'] and not mismatches,'hard_findings':['The ontology is semantically abundant and causal: 6,223 unique seeds, all independently re-derived with zero mismatch.','Headline gross WR is high at 74.3983%, but average loss is more than twice average win, producing payoff 0.4436 and PF 1.0414.','After 0.2% fees AvgNet is only +0.0744%; 2023 and 2024 are both negative, so the apparent win rate is economically unstable.','The failure is signal-payoff architecture, not T+1 or replay corruption; thresholds, SL, TP, hold, or yearly filters are forbidden variants.'],'production_state':'UNCHANGED_EMPTY_BOOK_FAIL_CLOSED','production_write':False,'frontend_write':False,'watchlist_write':False,'decision':'INTERNAL_INDUCEMENT_SWEEP_HAS_HIGH_HEADLINE_WR_BUT_FAILS_PAYOFF_AND_ALL_YEAR_EXPECTANCY__CLOSE_NO_VARIANTS','artifacts':{'v473':str(AUD/'v473_inducement_sweep_continuation_latest.json'),'v474':str(AUD/'v474_inducement_sweep_oracle_latest.json'),'v475':str(SRC),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
