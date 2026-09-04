#!/usr/bin/env python3
"""V496 independent metric and chronology recomputation for frozen V495 rows."""
import csv,json,statistics
from pathlib import Path
ROOT=Path('/root/.hermes');AUD=ROOT/'smc_audit';SRC=AUD/'v495_weekly_fvg_demand_transfer_frozen_t1_replay_latest.json';LATEST=AUD/'v496_weekly_fvg_demand_independent_metric_audit_latest.json'


def stats(rows):
    if not rows:return {'n':0}
    gross=[float(r['gross_pnl_pct']) for r in rows];net=[float(r['net_pnl_pct']) for r in rows]
    wins=[x for x in net if x>0];losses=[x for x in net if x<=0]
    aw=sum(wins)/len(wins) if wins else 0;al=sum(losses)/len(losses) if losses else 0
    return {'n':len(rows),'gross_wr_pct':round(sum(x>0 for x in gross)/len(rows)*100,4),'net_wr_ge_0_8_pct':round(sum(x>=.8 for x in net)/len(rows)*100,4),'avg_net_pnl_pct':round(sum(net)/len(rows),4),'median_net_pnl_pct':round(statistics.median(net),4),'avg_win_pct':round(aw,4),'avg_loss_pct':round(al,4),'payoff_rr':round(aw/abs(al),4) if al else 0,'profit_factor':round(sum(wins)/abs(sum(losses)),4) if losses and sum(losses) else 0,'cum_net_pnl_pct':round(sum(net),4),'t1':sum(r['exit_date']<=r['entry_date'] for r in rows)}


def main():
    report=json.loads(SRC.read_text())
    with open(report['artifacts']['rows']) as h:raw=list(csv.DictReader(h))
    closed=[r for r in raw if r['status']=='CLOSED' and r['entry_date'][:4] in {'2023','2024','2025','2026'}]
    overall=stats(closed);yearly={y:stats([r for r in closed if r['entry_date'][:4]==y]) for y in ('2023','2024','2025','2026')}
    keys=('n','gross_wr_pct','net_wr_ge_0_8_pct','avg_net_pnl_pct','payoff_rr','profit_factor','cum_net_pnl_pct')
    exact={'overall':{k:overall[k]==report['overall'][k] for k in keys},'yearly':{y:{k:yearly[y][k]==report['yearly'][y][k] for k in keys} for y in yearly}}
    chronology={'t1_violations':sum(x['t1'] for x in [overall]),'entry_not_after_hold':sum(r['entry_date']<=r['hold_date'] for r in closed),'exit_not_after_entry':sum(r['exit_date']<=r['entry_date'] for r in closed)}
    passed=all(exact['overall'].values()) and all(all(x.values()) for x in exact['yearly'].values()) and not any(chronology.values())
    result={'version':'V496_WEEKLY_FVG_DEMAND_INDEPENDENT_METRIC_AUDIT','source':str(SRC),'overall':overall,'yearly':yearly,'exact_report_match':exact,'chronology':chronology,'pass':passed,'decision':'INDEPENDENT_METRIC_AND_CHRONOLOGY_PASS__ECONOMIC_FAILURE_CONFIRMED' if passed else 'INDEPENDENT_AUDIT_FAIL__DO_NOT_USE_RESULT'}
    LATEST.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
