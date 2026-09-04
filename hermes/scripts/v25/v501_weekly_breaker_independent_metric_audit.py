#!/usr/bin/env python3
"""V501 independent metrics, chronology, and serial-position audit for V500."""
import csv,json,statistics
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes');AUD=ROOT/'smc_audit';SRC=AUD/'v500_weekly_breaker_daily_transfer_frozen_t1_replay_latest.json';LATEST=AUD/'v501_weekly_breaker_independent_metric_audit_latest.json'

def stats(rows):
    if not rows:return {'n':0}
    gross=[float(r['gross_pnl_pct']) for r in rows];net=[float(r['net_pnl_pct']) for r in rows];wins=[x for x in net if x>0];losses=[x for x in net if x<=0]
    aw=sum(wins)/len(wins) if wins else 0;al=sum(losses)/len(losses) if losses else 0;planned=[float(r['planned_rr']) for r in rows if r.get('planned_rr')]
    stop={'WEEKLY_BREAKER_SL_T1','SL_GAP_T1','SL_TP_COLLISION_CONSERVATIVE_T1'}
    return {'n':len(rows),'gross_wr_pct':round(sum(x>0 for x in gross)/len(rows)*100,4),'net_wr_ge_0_8_pct':round(sum(x>=.8 for x in net)/len(rows)*100,4),'avg_net_pnl_pct':round(sum(net)/len(rows),4),'median_net_pnl_pct':round(statistics.median(net),4),'avg_win_pct':round(aw,4),'avg_loss_pct':round(al,4),'payoff_rr':round(aw/abs(al),4) if al else 0,'profit_factor':round(sum(wins)/abs(sum(losses)),4) if losses and sum(losses) else 0,'cum_net_pnl_pct':round(sum(net),4),'avg_planned_rr':round(sum(planned)/len(planned),4) if planned else 0,'avg_realized_r':round(sum(float(r['realized_r']) for r in rows)/len(rows),4),'sl_pct':round(sum(r['exit_reason'] in stop for r in rows)/len(rows)*100,4)}

def main():
    report=json.loads(SRC.read_text())
    with open(report['artifacts']['rows']) as h:raw=list(csv.DictReader(h))
    closed=[r for r in raw if r.get('status')=='CLOSED' and r['entry_date'][:4] in {'2023','2024','2025','2026'}]
    overall=stats(closed);yearly={y:stats([r for r in closed if r['entry_date'][:4]==y]) for y in ('2023','2024','2025','2026')}
    exact={'overall':overall==report['overall'],'yearly':{y:yearly[y]==report['yearly'][y] for y in yearly},'exit_reason_counts':dict(Counter(r['exit_reason'] for r in closed))==report['exit_reason_counts']}
    chronology={'entry_not_after_hold':sum(r['entry_date']<=r['hold_date'] for r in closed),'exit_not_after_entry':sum(r['exit_date']<=r['entry_date'] for r in closed),'duplicate_symbol_entry':len(closed)-len(set((r['symbol'],r['entry_date']) for r in closed)),'t1_violations':sum(str(r.get('t1_violation')).lower()=='true' for r in closed)}
    grouped=defaultdict(list)
    for r in closed:grouped[r['symbol']].append(r)
    overlaps=0
    for rows in grouped.values():
        rows.sort(key=lambda r:int(r['entry_idx']))
        overlaps+=sum(int(b['entry_idx'])<=int(a['exit_idx']) for a,b in zip(rows,rows[1:]))
    chronology['serial_overlap_failures']=overlaps
    passed=exact['overall'] and exact['exit_reason_counts'] and all(exact['yearly'].values()) and not any(chronology.values())
    result={'version':'V501_WEEKLY_BREAKER_INDEPENDENT_METRIC_AUDIT_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source_version':report['version'],'closed_rows':len(closed),'overall':overall,'yearly':yearly,'matches':exact,'invariants':{**chronology,'search_count':report['invariants']['search_count']},'audit_pass':passed,'promotion_gate_pass':bool(report['promotion_gate_pass'] and passed),'decision':'WEEKLY_BREAKER_TRANSFER_VERIFIED_ECONOMIC_FAIL__CLOSE_ONTOLOGY_NO_VARIANTS' if passed and not report['promotion_gate_pass'] else ('WEEKLY_BREAKER_TRANSFER_INDEPENDENT_PASS__PROMOTION_CONFIRMED' if passed else 'INDEPENDENT_AUDIT_FAIL__DO_NOT_USE_RESULT'),'closure_reason':'High aggregate WR is purchased with average losses larger than average wins; 2023 and 2026 expectancy are negative. Do not tune BOS, OB, activation, SL, TP, hold, year, or regime variants.','artifacts':{'rows':report['artifacts']['rows'],'latest':str(LATEST)}}
    LATEST.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
