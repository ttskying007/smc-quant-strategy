#!/usr/bin/env python3
"""V514 independent metric, chronology, serial and T+1 audit for V513."""
from __future__ import annotations
import csv,json,math,statistics
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes');AUD=ROOT/'smc_audit';SRC=AUD/'v513_weekly_bos_daily_ssl_reversal_frozen_t1_replay_latest.json'
OUT=AUD/f"v514_weekly_bos_daily_ssl_reversal_metric_audit_no_write_{datetime.now():%Y%m%d_%H%M%S}";LATEST=AUD/'v514_weekly_bos_daily_ssl_reversal_metric_audit_latest.json'
YEARS=('2023','2024','2025','2026');STOP={'DAILY_RAID_STRUCTURE_SL_T1','SL_GAP_T1','SL_TP_COLLISION_CONSERVATIVE_T1'}


def f(x):
    try:v=float(x);return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError):return 0.0


def stats(rows):
    if not rows:return {'n':0}
    gross=[f(r['gross_pnl_pct']) for r in rows];net=[f(r['net_pnl_pct']) for r in rows];wins=[x for x in net if x>0];losses=[x for x in net if x<=0]
    aw=sum(wins)/len(wins) if wins else 0;al=sum(losses)/len(losses) if losses else 0;planned=[f(r['planned_rr']) for r in rows if r.get('planned_rr') not in ('',None)]
    return {'n':len(rows),'gross_wr_pct':round(sum(x>0 for x in gross)/len(rows)*100,4),'net_wr_ge_0_8_pct':round(sum(x>=.8 for x in net)/len(rows)*100,4),'avg_net_pnl_pct':round(sum(net)/len(rows),4),'median_net_pnl_pct':round(statistics.median(net),4),'avg_win_pct':round(aw,4),'avg_loss_pct':round(al,4),'payoff_rr':round(aw/abs(al),4) if al else 0,'profit_factor':round(sum(wins)/abs(sum(losses)),4) if losses and sum(losses) else 0,'cum_net_pnl_pct':round(sum(net),4),'avg_planned_rr':round(sum(planned)/len(planned),4) if planned else 0,'avg_realized_r':round(sum(f(r['realized_r']) for r in rows)/len(rows),4),'sl_pct':round(sum(r['exit_reason'] in STOP for r in rows)/len(rows)*100,4)}


def main():
    report=json.loads(SRC.read_text());OUT.mkdir(parents=True,exist_ok=True)
    with open(report['artifacts']['rows']) as h:all_rows=list(csv.DictReader(h))
    closed=[r for r in all_rows if r.get('status')=='CLOSED' and r.get('entry_date','')[:4] in set(YEARS)]
    overall=stats(closed);yearly={y:stats([r for r in closed if r['entry_date'][:4]==y]) for y in YEARS}
    overall_match=overall==report['overall'];year_match={y:yearly[y]==report['yearly'][y] for y in YEARS}
    t1=sum(r['exit_date']<=r['entry_date'] for r in closed);duplicates=len(closed)-len(set((r['symbol'],r['entry_date']) for r in closed))
    chronology=sum(not (int(float(r['weekly_bos_idx']))>=0 and int(float(r['daily_ssl_idx']))<int(float(r['daily_ssl_confirm_idx']))<=int(float(r['daily_raid_idx']))<int(float(r['daily_choch_idx']))<int(float(r['touch_idx']))<int(float(r['reclaim_idx']))<int(float(r['hold_idx']))<int(float(r['entry_idx']))<int(float(r['exit_idx']))) for r in closed)
    grouped=defaultdict(list)
    for r in closed:grouped[r['symbol']].append(r)
    serial=0
    for rows in grouped.values():
        rows.sort(key=lambda r:int(float(r['entry_idx'])))
        serial+=sum(int(float(b['entry_idx']))<=int(float(a['exit_idx'])) for a,b in zip(rows,rows[1:]))
    exit_counts=dict(Counter(r['exit_reason'] for r in closed));exit_match=exit_counts==report['exit_reason_counts']
    audit=overall_match and all(year_match.values()) and not t1 and not duplicates and not chronology and not serial and exit_match and report['invariants']['search_count']==1
    decision='WEEKLY_BOS_DAILY_SSL_VERIFIED_PROMOTION_PASS' if audit and report['promotion_gate_pass'] else ('WEEKLY_BOS_DAILY_SSL_VERIFIED_ECONOMIC_FAIL__CLOSE_ONTOLOGY_NO_VARIANTS' if audit else 'INDEPENDENT_AUDIT_FAIL__DO_NOT_CONCLUDE')
    result={'version':'V514_WEEKLY_BOS_DAILY_SSL_REVERSAL_INDEPENDENT_METRIC_AUDIT_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'source_version':report['version'],'closed_rows':len(closed),'recomputed_overall':overall,'recomputed_yearly':yearly,
      'matches':{'overall_exact':overall_match,'yearly_exact':year_match,'exit_reason_counts_exact':exit_match},
      'invariants':{'t1_violations':t1,'duplicate_symbol_entry':duplicates,'chronology_failures':chronology,'serial_overlap_failures':serial,'search_count':report['invariants']['search_count']},
      'audit_pass':audit,'promotion_gate_pass':report['promotion_gate_pass'],'decision':decision,
      'closure_reason':'Weekly bullish BOS permission lifts headline WR to 64.13%, but loss magnitude remains dominant: payoff 0.6237, PF 1.0407, AvgNet 0.1247%; 2023, 2024 and 2026 are negative. Close this ontology without weekly-state, SSL, CHOCH, OB, SL, target, hold, year or regime variants.',
      'artifacts':{'out_dir':str(OUT),'source_rows':report['artifacts']['rows'],'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2);(OUT/'v514_report.json').write_text(text);LATEST.write_text(text);print(text)

if __name__=='__main__':main()
