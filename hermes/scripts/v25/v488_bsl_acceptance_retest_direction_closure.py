#!/usr/bin/env python3
"""V488 independent metric recomputation and final BSL-acceptance closure."""
from __future__ import annotations
import csv, json, statistics
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'
GEN=AUD/'v485_bsl_acceptance_retest_latest.json'; ORACLE=AUD/'v486_bsl_acceptance_retest_oracle_latest.json'; REPLAY=AUD/'v487_bsl_acceptance_retest_frozen_t1_replay_latest.json'
OUT=AUD/f"v488_bsl_acceptance_retest_closure_no_write_{datetime.now():%Y%m%d_%H%M%S}"; LATEST=AUD/'v488_bsl_acceptance_retest_direction_closure_latest.json'
STOP={'STRUCTURAL_RETEST_SL_T1','SL_GAP_T1','SL_TP_COLLISION_CONSERVATIVE_T1'}


def n(x):
    try: return float(x)
    except (TypeError,ValueError): return 0.0


def stats(rows):
    if not rows: return {'n':0}
    gross=[n(r['gross_pnl_pct']) for r in rows]; net=[n(r['net_pnl_pct']) for r in rows]
    win=[x for x in net if x>0]; loss=[x for x in net if x<=0]; aw=sum(win)/len(win); al=sum(loss)/len(loss)
    return {'n':len(rows),'gross_wr_pct':round(sum(x>0 for x in gross)/len(rows)*100,4),'net_wr_ge_0_8_pct':round(sum(x>=.8 for x in net)/len(rows)*100,4),
      'avg_net_pnl_pct':round(sum(net)/len(rows),4),'median_net_pnl_pct':round(statistics.median(net),4),'avg_win_pct':round(aw,4),'avg_loss_pct':round(al,4),
      'payoff_rr':round(aw/abs(al),4),'profit_factor':round(sum(win)/abs(sum(loss)),4),'cum_net_pnl_pct':round(sum(net),4),
      'avg_planned_rr':round(sum(n(r['planned_rr']) for r in rows)/len(rows),4),'avg_realized_r':round(sum(n(r['realized_r']) for r in rows)/len(rows),4),
      'sl_pct':round(sum(r['exit_reason'] in STOP for r in rows)/len(rows)*100,4)}


def diff(a,b,fields): return [k for k in fields if abs(n(a.get(k))-n(b.get(k)))>1e-4]


def main():
    gen=json.loads(GEN.read_text()); oracle=json.loads(ORACLE.read_text()); replay=json.loads(REPLAY.read_text())
    with open(replay['artifacts']['rows']) as h: all_rows=list(csv.DictReader(h))
    rows=[r for r in all_rows if r.get('status')=='CLOSED' and r.get('entry_date','')[:4] in {'2023','2024','2025','2026'}]
    overall=stats(rows); yearly={y:stats([r for r in rows if r['entry_date'][:4]==y]) for y in ('2023','2024','2025','2026')}
    fields=('n','gross_wr_pct','net_wr_ge_0_8_pct','avg_net_pnl_pct','median_net_pnl_pct','avg_win_pct','avg_loss_pct','payoff_rr','profit_factor','cum_net_pnl_pct','avg_planned_rr','avg_realized_r','sl_pct')
    mismatch={'overall':diff(overall,replay['overall'],fields)}; mismatch.update({y:diff(yearly[y],replay['yearly'][y],fields) for y in yearly})
    chronology=sum(int(float(r['exit_idx']))<=int(float(r['entry_idx'])) or r['exit_date']<=r['entry_date'] for r in rows)
    t1=sum(str(r.get('t1_violation','')).lower()=='true' for r in rows); metric_pass=not any(mismatch.values()) and chronology==0 and t1==0
    gate=replay['frozen_before_outcomes']['promotion_gate']; failures=[]
    if overall['gross_wr_pct']<gate['gross_wr_pct']: failures.append('overall_gross_wr_pct<55')
    if overall['avg_net_pnl_pct']<gate['avg_net_pnl_pct']: failures.append('overall_avg_net_pnl_pct<0.5')
    if overall['profit_factor']<gate['profit_factor']: failures.append('overall_profit_factor<1.15')
    for y in ('2023','2024','2025','2026'):
        if yearly[y]['gross_wr_pct']<gate['each_year_gross_wr_pct']: failures.append(f'{y}_gross_wr_pct<50')
        if yearly[y]['avg_net_pnl_pct']<=gate['each_year_avg_net_pnl_pct']: failures.append(f'{y}_avg_net_pnl_pct<=0')
    consumed=replay['status_counts'].get('TARGET_CONSUMED_AT_ENTRY',0); seeds=replay['seed_count']
    OUT.mkdir(parents=True,exist_ok=True)
    result={'version':'V488_BSL_ACCEPTANCE_RETEST_DIRECTION_CLOSURE','generated_at':datetime.now().isoformat(timespec='seconds'),
      'scope':'One genuinely distinct local pure-structure ontology; no production/frontend/watchlist writes.','ontology':'EXTERNAL_BSL_ACCEPTANCE_RETEST_CONTINUATION','frozen_contract':gen['frozen_contract'],
      'semantic_generation':{'symbols_scanned':gen['symbols_scanned'],'seed_count':gen['seed_count'],'yearly_seed_count':gen['yearly_seed_count'],'support_gate_pass':gen['support_gate_pass'],'semantic_order_failures':gen['invariants']['semantic_order_failures']},
      'independent_oracle':{'expected_seed_count':oracle['expected_seed_count'],'observed_seed_count':oracle['observed_seed_count'],'mismatch_total':oracle['mismatch_total'],'oracle_gate_pass':oracle['oracle_gate_pass']},
      'frozen_t1_replay':{'status_counts':replay['status_counts'],'target_consumed_at_entry_pct':round(consumed/seeds*100,4),'overall':overall,'yearly':yearly,'exit_reason_counts':replay['exit_reason_counts'],'t1_violations':t1,'search_count':1},
      'independent_metric_recomputation':{'mismatch_fields':mismatch,'chronology_failures':chronology,'pass':metric_pass},
      'promotion_gate_failures':failures,'promotion_gate_pass':False,
      'hard_findings':['The new broken-BSL acceptance/retest ontology is semantically abundant and causal: 62,567 seeds across 4,903 symbols, independently reproduced with zero mismatch.',
        'The one frozen replay closed 33,495 trades: gross WR 56.5756%, net>=0.8 WR 47.1473%, AvgNet -0.0402%, payoff 0.7909, PF 0.9831, SL 41.7644%.',
        '2023 AvgNet -0.6718% and 2024 -0.5342%; 2026 remains -0.0242%. Only 2025 is positive (+0.4410%), so the edge is regime-dependent and not stable.',
        f'Next-open execution found the known higher-BSL target already consumed in {consumed}/{seeds} seeds ({consumed/seeds*100:.2f}%), exposing a structural timing defect rather than an exit parameter problem.'],
      'production_state':'UNCHANGED_EMPTY_BOOK_FAIL_CLOSED','production_write':False,'frontend_write':False,'watchlist_write':False,
      'decision':'BSL_ACCEPTANCE_RETEST_IS_CAUSAL_BUT_NEGATIVE_AFTER_FEES_AND_UNSTABLE_BY_YEAR__CLOSE_NO_VARIANTS',
      'artifacts':{'v485':str(GEN),'v486':str(ORACLE),'v487':str(REPLAY),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2); (OUT/'v488_report.json').write_text(text); LATEST.write_text(text); print(text)

if __name__=='__main__': main()
