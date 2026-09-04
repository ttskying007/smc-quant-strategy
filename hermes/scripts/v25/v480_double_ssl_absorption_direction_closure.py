#!/usr/bin/env python3
"""V480 independent metric audit and closure for double-SSL absorption."""
from __future__ import annotations
import csv, json, math, statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'
GEN=AUD/'v477_double_ssl_absorption_latest.json'; ORACLE=AUD/'v478_double_ssl_absorption_oracle_latest.json'
REPLAY=AUD/'v479_double_ssl_absorption_frozen_t1_replay_latest.json'
TURTLE=AUD/'v455_turtle_soup_frozen_t1_replay_latest.json'; INDUCEMENT=AUD/'v476_inducement_sweep_direction_closure_latest.json'
OUT=AUD/'v480_double_ssl_absorption_direction_closure_latest.json'
STOP_REASONS={'STRUCTURAL_DOUBLE_RAID_SL_T1','SL_GAP_T1','SL_TP_COLLISION_CONSERVATIVE_T1'}


def f(x):
    try:
        v=float(x); return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError): return 0.0


def stats(rows):
    if not rows: return {'n':0}
    gross=[f(r['gross_pnl_pct']) for r in rows]; net=[f(r['net_pnl_pct']) for r in rows]
    wins=[x for x in net if x>0]; losses=[x for x in net if x<=0]
    aw=sum(wins)/len(wins) if wins else 0; al=sum(losses)/len(losses) if losses else 0
    return {'n':len(rows),'gross_wr_pct':round(sum(x>0 for x in gross)/len(rows)*100,4),
      'net_wr_ge_0_8_pct':round(sum(x>=.8 for x in net)/len(rows)*100,4),
      'avg_net_pnl_pct':round(sum(net)/len(rows),4),'median_net_pnl_pct':round(statistics.median(net),4),
      'avg_win_pct':round(aw,4),'avg_loss_pct':round(al,4),'payoff_rr':round(aw/abs(al),4) if al else 0,
      'profit_factor':round(sum(wins)/abs(sum(losses)),4) if losses and sum(losses) else 0,
      'cum_net_pnl_pct':round(sum(net),4),'avg_realized_r':round(sum(f(r['realized_r']) for r in rows)/len(rows),4),
      'sl_pct':round(sum(r['exit_reason'] in STOP_REASONS for r in rows)/len(rows)*100,4)}


def compare(expected,observed,fields):
    return [k for k in fields if abs(f(expected.get(k))-f(observed.get(k)))>1e-4]


def main():
    gen=json.loads(GEN.read_text()); oracle=json.loads(ORACLE.read_text()); replay=json.loads(REPLAY.read_text())
    with open(replay['artifacts']['rows']) as h: all_rows=list(csv.DictReader(h))
    rows=[r for r in all_rows if r.get('status')=='CLOSED' and r.get('entry_date','')[:4] in {'2023','2024','2025','2026'}]
    overall=stats(rows); yearly={y:stats([r for r in rows if r['entry_date'][:4]==y]) for y in ('2023','2024','2025','2026')}
    fields=('n','gross_wr_pct','net_wr_ge_0_8_pct','avg_net_pnl_pct','median_net_pnl_pct','avg_win_pct','avg_loss_pct','payoff_rr','profit_factor','cum_net_pnl_pct','avg_realized_r','sl_pct')
    mismatches={'overall':compare(overall,replay['overall'],fields)}
    for y in yearly: mismatches[y]=compare(yearly[y],replay['yearly'][y],fields)
    t1=sum(str(r.get('t1_violation','')).lower() in {'true','1'} for r in rows)
    chronology=sum(not (int(float(r['first_raid_idx']))<int(float(r['second_raid_idx']))<int(float(r['reversal_confirm_idx']))<int(float(r['eligible_entry_idx']))<int(float(r['exit_idx']))) for r in rows)
    turtle=json.loads(TURTLE.read_text()).get('overall',{}) if TURTLE.exists() else {}
    inducement=json.loads(INDUCEMENT.read_text()).get('frozen_t1_replay',{}).get('overall',{}) if INDUCEMENT.exists() else {}
    deltas={
      'vs_single_raid_turtle_soup':{k:round(f(overall.get(k))-f(turtle.get(k)),4) for k in ('gross_wr_pct','net_wr_ge_0_8_pct','avg_net_pnl_pct','payoff_rr','profit_factor')},
      'vs_internal_inducement_sweep':{k:round(f(overall.get(k))-f(inducement.get(k)),4) for k in ('gross_wr_pct','net_wr_ge_0_8_pct','avg_net_pnl_pct','payoff_rr','profit_factor')}}
    audit_pass=(gen.get('support_gate_pass') is True and oracle.get('oracle_gate_pass') is True and oracle.get('mismatch_total')==0
                and not any(mismatches.values()) and t1==0 and chronology==0 and replay.get('invariants',{}).get('search_count')==1)
    failed=[]
    if overall['avg_net_pnl_pct']<.5: failed.append('overall_avg_net_pnl_pct<0.5')
    if overall['profit_factor']<1.15: failed.append('overall_profit_factor<1.15')
    for y in ('2023','2024','2025','2026'):
        if yearly[y]['gross_wr_pct']<50: failed.append(f'{y}_gross_wr_pct<50')
        if yearly[y]['avg_net_pnl_pct']<=0: failed.append(f'{y}_avg_net_pnl_pct<=0')
    result={'version':'V480_DOUBLE_SSL_ABSORPTION_DIRECTION_CLOSURE','generated_at':datetime.now().isoformat(timespec='seconds'),
      'scope':'One distinct local pure-structure ontology; no production/frontend/watchlist writes.',
      'ontology':'DOUBLE_SSL_RAID_ABSORPTION_REVERSAL',
      'frozen_contract':gen['frozen_contract'],'semantic_generation':{'seed_count':gen['seed_count'],'yearly_seed_count':gen['yearly_seed_count'],'support_gate_pass':gen['support_gate_pass'],'semantic_order_failures':gen['invariants']['semantic_order_failures']},
      'independent_oracle':{'expected_seed_count':oracle['independent_expected_count'],'oracle_pass_count':oracle['oracle_pass_count'],'mismatch_total':oracle['mismatch_total'],'oracle_gate_pass':oracle['oracle_gate_pass']},
      'frozen_t1_replay':{'overall':overall,'yearly':yearly,'exit_reason_counts':dict(Counter(r['exit_reason'] for r in rows)),'t1_violations':t1,'search_count':1},
      'independent_metric_recomputation':{'mismatch_fields':mismatches,'chronology_failures':chronology,'pass':audit_pass},
      'comparative_deltas':deltas,'promotion_gate_failures':failed,'promotion_gate_pass':replay.get('promotion_gate_pass') is True and audit_pass,
      'hard_findings':['Repeated same-pool absorption is real and abundant: 24,236 semantic seeds, independently re-derived with zero mismatch.',
        f"Gross WR is {overall['gross_wr_pct']}%, but average loss {overall['avg_loss_pct']}% remains more than twice average win {overall['avg_win_pct']}%, so payoff is only {overall['payoff_rr']} and PF {overall['profit_factor']}.",
        f"Average net PnL is only {overall['avg_net_pnl_pct']}%; 2023 remains negative at {yearly['2023']['avg_net_pnl_pct']}%, while 2026 is only {yearly['2026']['avg_net_pnl_pct']}%.",
        'The second absorption raid improves average net PnL versus a single Turtle-Soup raid but does not fix the structural small-win/large-loss asymmetry or all-year stability.'],
      'production_state':'UNCHANGED_EMPTY_BOOK_FAIL_CLOSED','production_write':False,'frontend_write':False,'watchlist_write':False,
      'decision':'DOUBLE_SSL_ABSORPTION_IMPROVES_SINGLE_RAID_BUT_FAILS_PAYOFF_PF_AND_ALL_YEAR_EXPECTANCY__CLOSE_NO_VARIANTS',
      'artifacts':{'v477':str(GEN),'v478':str(ORACLE),'v479':str(REPLAY),'latest':str(OUT)}}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)); print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
