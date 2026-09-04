#!/usr/bin/env python3
"""V522 production-license audit for the V517-V521 volume/price ontology.

This is a gate aggregation audit, not a new backtest. When every outcome-blind,
Oracle, frozen replay, independent metric, and scanner-time contract passes, it
licenses V517 as the production strategy. Each individual buy remains separately
restricted to a current committed scanner row and its exact next-open validation.
"""
from __future__ import annotations
import csv,json
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes');AUD=ROOT/'smc_audit';OUT=AUD/f'v522_effort_result_release_audit_no_write_{datetime.now():%Y%m%d_%H%M%S}';LATEST=AUD/'v522_effort_result_release_audit_latest.json'
PATHS={k:AUD/v for k,v in {'v517':'v517_daily_effort_result_absorption_seed_gate_latest.json','v518':'v518_daily_effort_result_absorption_independent_oracle_latest.json','v519':'v519_daily_effort_result_absorption_frozen_t1_replay_latest.json','v520':'v520_daily_effort_result_absorption_independent_metric_audit_latest.json','v521':'v521_daily_effort_result_absorption_scanner_time_dry_run_latest.json'}.items()}
def load(p):return json.loads(p.read_text())
def main():
    OUT.mkdir(parents=True,exist_ok=True);x={k:load(p) for k,p in PATHS.items()}
    with Path(x['v519']['artifacts']['trades']).open(newline='') as h:tr=list(csv.DictReader(h))
    keys=[(r['symbol'],r['entry_date']) for r in tr];by=defaultdict(list)
    for r in tr:by[r['symbol']].append(r)
    overlaps=[]
    for sym,arr in by.items():
        arr.sort(key=lambda r:r['entry_date'])
        overlaps += [(sym,a['entry_date'],a['exit_date'],b['entry_date']) for a,b in zip(arr,arr[1:]) if b['entry_date']<=a['exit_date']]
    checks={
      'v517_outcome_blind_support_pass':x['v517'].get('support_gate_pass') is True and x['v517'].get('outcomes_opened') is False,
      'v518_raw_bar_oracle_pass':x['v518'].get('oracle_pass') is True and x['v518'].get('outcomes_opened') is False,
      'v519_frozen_replay_gate_pass':x['v519'].get('promotion_gate_pass') is True,
      # Defend release aggregation against an older replay artifact that might
      # predate the V519 yearly gate fields.  A valid production license needs
      # sufficient support and positive average net result in every declared year.
      'v519_each_year_n>=300':all((x['v519'].get('yearly',{}).get(y,{}) or {}).get('n',0)>=300 for y in ('2023','2024','2025','2026')),
      'v519_each_year_avg_net>0':all((x['v519'].get('yearly',{}).get(y,{}) or {}).get('avg_net_pnl_pct',0)>0 for y in ('2023','2024','2025','2026')),
      'v520_independent_metric_pass':x['v520'].get('audit_pass') is True,
      'all_research_writes_false':all(not any(v.get(k,False) for k in ('production_write','frontend_write','watchlist_write')) for v in x.values()),
      'serial_no_symbol_entry_duplicates':len(keys)==len(set(keys)),
      'serial_no_overlap':not overlaps,
      # V520 exits early when V519 fails another promotion condition, so it has
      # no independent T+1 field in that state. T+1 is decided from the frozen
      # replay invariant rather than being reported falsely as failed.
      'all_t1_clean':x['v519'].get('invariants',{}).get('t1_violations')==0,
      'monthly_trade_count_support_pass':x['v519'].get('monthly_trade_count_gate_pass') is True,
      'scanner_has_no_historical_fallback':x['v521']['invariants']['no_historical_trade_source'] is True,
      'scanner_rows_are_current_epoch_only':x['v521']['invariants']['all_rows_response_on_market_date'] is True,
      'scanner_has_no_premature_buy':x['v521']['buy_valid_count']==0,
    }
    research_pass=all(checks.values())
    production_license = research_pass
    live_state = ('PRODUCTION_LICENSED_PENDING_NEXT_OPEN' if x['v521']['pending_next_open_count'] else
                  'PRODUCTION_LICENSED_NO_CURRENT_SIGNAL') if production_license else 'BLOCKED'
    report={'version':'V522_EFFORT_RESULT_PRODUCTION_LICENSE_AUDIT','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'ontology':'DAILY_EFFORT_RESULT_ABSORPTION','research_result':'RESEARCH_PROMOTABLE' if research_pass else 'RESEARCH_BLOCKED','production_license_state':'V517_PRODUCTION_BUY_LICENSED' if production_license else 'V517_PRODUCTION_BUY_BLOCKED','production_license_granted':production_license,'live_release_state':live_state,'live_release_rule':'V517 is licensed as the production strategy. A buy is permitted only from a newest-committed-epoch scanner row, persisted as PENDING_NEXT_OPEN, then only at its exact following-session opening quote when open > structural stop and open < pre-known target. No historical replay row may be substituted.','checks':checks,'metrics':x['v519']['overall'],'yearly':x['v519']['yearly'],'trade_integrity':{'closed_trades':len(tr),'symbols':len(by),'max_trades_per_symbol':max(map(len,by.values()),default=0),'duplicate_symbol_entry':len(keys)-len(set(keys)),'overlap_count':len(overlaps),'gap_sl_count':sum(r['reason']=='GAP_SL' for r in tr)},'current_scanner':{'epoch_id':x['v521']['epoch_id'],'market_date':x['v521']['market_date'],'pending_next_open_count':x['v521']['pending_next_open_count'],'pending_rows':x['v521']['rows'],'buy_valid_count':x['v521']['buy_valid_count']},'decision':'V522_PRODUCTION_LICENSE_PASS__CURRENT_SCANNER_AND_EXACT_NEXT_OPEN_REQUIRED' if production_license else 'V522_PRODUCTION_LICENSE_BLOCKED','artifacts':{'out_dir':str(OUT),'latest':str(LATEST),**{k:str(v) for k,v in PATHS.items()}}}
    text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v522_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
