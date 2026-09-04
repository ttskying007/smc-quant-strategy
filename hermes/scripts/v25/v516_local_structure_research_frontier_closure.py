#!/usr/bin/env python3
"""V516 no-write registry audit after the V515 support-gate failure."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path

AUD=Path('/root/.hermes/smc_audit')
OUT=AUD/f"v516_local_structure_frontier_closure_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST=AUD/'v516_local_structure_frontier_closure_latest.json'


def read(name): return json.loads((AUD/name).read_text())


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    daily=read('v431_local_daily_structure_frontier_closure_latest.json')
    new_daily=read('v451_local_pure_structure_new_directions_closure_latest.json')
    market=read('v464_market_smt_direction_closure_latest.json')
    industry=read('v468_industry_smt_direction_closure_latest.json')
    weekly_rej=read('v460_weekly_rejection_block_direction_closure_latest.json')
    inducement=read('v476_inducement_sweep_direction_closure_latest.json')
    double_ssl=read('v480_double_ssl_absorption_direction_closure_latest.json')
    two_sided=read('v484_two_sided_liquidity_purge_direction_closure_latest.json')
    weekly_bos=read('v492_weekly_bos_demand_independent_metric_audit_latest.json')
    weekly_breaker=read('v501_weekly_breaker_independent_metric_audit_latest.json')
    weekly_ifvg=read('v510_weekly_ifvg_support_metric_audit_latest.json')
    weekly_ctx=read('v514_weekly_bos_daily_ssl_reversal_metric_audit_latest.json')
    final=read('v515_weekly_two_sided_purge_daily_transfer_latest.json')

    frontier=[
      {'ontology':'SSL_CREATED_BEAR_IFVG','n':new_daily['directions']['SSL_CREATED_BEAR_IFVG']['metrics']['n'],'gross_wr_pct':new_daily['directions']['SSL_CREATED_BEAR_IFVG']['metrics']['wr_pct'],'avg_net_pnl_pct':new_daily['directions']['SSL_CREATED_BEAR_IFVG']['metrics']['avg_pnl_pct'],'payoff_rr':new_daily['directions']['SSL_CREATED_BEAR_IFVG']['metrics']['payoff_rr'],'profit_factor':new_daily['directions']['SSL_CREATED_BEAR_IFVG']['metrics']['profit_factor'],'failure':'2023 AvgPnL -0.1230%, PF 0.9497'},
      {'ontology':'WEEKLY_SSL_REJECTION_BLOCK_TRANSFER','n':weekly_rej['frozen_t1_replay']['closed_n'],'gross_wr_pct':weekly_rej['frozen_t1_replay']['gross_wr_pct'],'avg_net_pnl_pct':weekly_rej['frozen_t1_replay']['avg_net_pnl_pct'],'payoff_rr':weekly_rej['frozen_t1_replay']['payoff_rr'],'profit_factor':weekly_rej['frozen_t1_replay']['profit_factor'],'failure':'2023/2026 AvgPnL negative'},
      {'ontology':'INTERNAL_INDUCEMENT_SWEEP','n':inducement['frozen_t1_replay']['overall']['n'],'gross_wr_pct':inducement['frozen_t1_replay']['overall']['gross_wr_pct'],'avg_net_pnl_pct':inducement['frozen_t1_replay']['overall']['avg_net_pnl_pct'],'payoff_rr':inducement['frozen_t1_replay']['overall']['payoff_rr'],'profit_factor':inducement['frozen_t1_replay']['overall']['profit_factor'],'failure':'2023/2024 AvgPnL negative'},
      {'ontology':'DOUBLE_SSL_ABSORPTION','n':double_ssl['frozen_t1_replay']['overall']['n'],'gross_wr_pct':double_ssl['frozen_t1_replay']['overall']['gross_wr_pct'],'avg_net_pnl_pct':double_ssl['frozen_t1_replay']['overall']['avg_net_pnl_pct'],'payoff_rr':double_ssl['frozen_t1_replay']['overall']['payoff_rr'],'profit_factor':double_ssl['frozen_t1_replay']['overall']['profit_factor'],'failure':'2023 AvgPnL negative; payoff <0.5'},
      {'ontology':'DAILY_TWO_SIDED_PURGE','n':two_sided['frozen_t1_replay']['overall']['n'],'gross_wr_pct':two_sided['frozen_t1_replay']['overall']['gross_wr_pct'],'avg_net_pnl_pct':two_sided['frozen_t1_replay']['overall']['avg_net_pnl_pct'],'payoff_rr':two_sided['frozen_t1_replay']['overall']['payoff_rr'],'profit_factor':two_sided['frozen_t1_replay']['overall']['profit_factor'],'failure':'2023/2026 AvgPnL negative'},
      {'ontology':'WEEKLY_BOS_DEMAND_TRANSFER','n':weekly_bos['overall']['n'],'gross_wr_pct':weekly_bos['overall']['gross_wr_pct'],'avg_net_pnl_pct':weekly_bos['overall']['avg_net_pnl_pct'],'payoff_rr':weekly_bos['overall']['payoff_rr'],'profit_factor':weekly_bos['overall']['profit_factor'],'failure':'2023/2024 AvgPnL negative'},
      {'ontology':'WEEKLY_BREAKER_TRANSFER','n':weekly_breaker['overall']['n'],'gross_wr_pct':weekly_breaker['overall']['gross_wr_pct'],'avg_net_pnl_pct':weekly_breaker['overall']['avg_net_pnl_pct'],'payoff_rr':weekly_breaker['overall']['payoff_rr'],'profit_factor':weekly_breaker['overall']['profit_factor'],'failure':'2023/2026 AvgPnL negative'},
      {'ontology':'WEEKLY_IFVG_SUPPORT','n':weekly_ifvg['recomputed_overall']['n'],'gross_wr_pct':weekly_ifvg['recomputed_overall']['gross_wr_pct'],'avg_net_pnl_pct':weekly_ifvg['recomputed_overall']['avg_net_pnl_pct'],'payoff_rr':weekly_ifvg['recomputed_overall']['payoff_rr'],'profit_factor':weekly_ifvg['recomputed_overall']['profit_factor'],'failure':'2023/2026 AvgPnL negative'},
      {'ontology':'WEEKLY_BOS_CONTEXT_DAILY_SSL','n':weekly_ctx['recomputed_overall']['n'],'gross_wr_pct':weekly_ctx['recomputed_overall']['gross_wr_pct'],'avg_net_pnl_pct':weekly_ctx['recomputed_overall']['avg_net_pnl_pct'],'payoff_rr':weekly_ctx['recomputed_overall']['payoff_rr'],'profit_factor':weekly_ctx['recomputed_overall']['profit_factor'],'failure':'2023/2024/2026 AvgPnL negative'},
    ]
    best_wr=max(frontier,key=lambda x:x['gross_wr_pct']); best_avg=max(frontier,key=lambda x:x['avg_net_pnl_pct']); best_payoff=max(frontier,key=lambda x:x['payoff_rr'])
    checks={
      'daily_r1_r5_closed':daily['decision']=='LOCAL_DAILY_PURE_STRUCTURE_RESEARCH_COMPLETE__NO_DEFINED_LEGAL_NEXT_REPLAY' and daily['invariants']['unclosed_defined_local_daily_ontology_count']==0,
      'post_r5_daily_directions_closed':all(x.get('decision') for x in new_daily['directions'].values()),
      'cross_security_market_closed':market['promotion_gate_pass'] is False,
      'cross_security_industry_closed':industry['promotion_gate_pass'] is False,
      'weekly_transfer_families_closed':weekly_rej['promotion_gate_pass'] is False and weekly_ctx['promotion_gate_pass'] is False and weekly_ifvg['promotion_gate_pass'] is False,
      'v515_distinct_ontology_support_failed_before_outcomes':final['support_gate_pass'] is False and final['seed_count']==51 and final['invariants']['no_outcome_fields'],
      'all_production_writes_false':all(x.get('production_write',False) is False for x in (daily,market,industry,weekly_rej,inducement,double_ssl,two_sided,weekly_ifvg,weekly_ctx,final)),
    }
    result={'version':'V516_LOCAL_STRUCTURE_RESEARCH_FRONTIER_CLOSURE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'v515_new_direction':{'ontology':final['frozen_contract'],'symbols_scanned':final['symbols_scanned'],'weekly_events':final['weekly_purge_event_count'],'complete_seeds':final['seed_count'],'yearly':final['yearly_seed_count'],'support_gate_pass':False,'outcomes_opened':False,'decision':'CLOSE_SUPPORT_FAILURE__DO_NOT_RELAX'},
      'verified_economic_frontier':frontier,'frontier_extrema':{'highest_gross_wr':best_wr,'highest_avg_net_pnl':best_avg,'highest_payoff_rr':best_payoff},
      'registry_checks':checks,'audit_pass':all(checks.values()),
      'structural_diagnosis':'Across daily, cross-security and weekly ontologies, the recurring failure is not raw signal scarcity or replay causality. High headline WR is purchased with average losses materially larger than average wins, while 2023 and/or 2026 expectancy remains negative. The final distinct weekly two-sided path is too sparse for an honest replay.',
      'decision':'CURRENT_LOCAL_OHLCV_PURE_STRUCTURE_RESEARCH_COMPLETE__ZERO_ALL_YEAR_PROMOTION_PASS__STOP_STRATEGY_ITERATION' if all(checks.values()) else 'FRONTIER_AUDIT_INCOMPLETE',
      'remaining_legal_work':'Operational monitoring only. Restart strategy research only after a genuinely new causal ontology is identified that is not a timeframe/context/threshold/entry/exit variant and passes n>=300 plus every-year n>=40 before outcomes.',
      'artifacts':{'out_dir':str(OUT),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2); (OUT/'v516_report.json').write_text(text); LATEST.write_text(text); print(text)

if __name__=='__main__': main()
