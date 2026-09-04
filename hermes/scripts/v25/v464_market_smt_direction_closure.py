#!/usr/bin/env python3
"""V464 close the market-SMT pure-structure direction after frozen replay."""
import json
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes');AUD=ROOT/'smc_audit';LATEST=AUD/'v464_market_smt_direction_closure_latest.json'
v461=json.loads((AUD/'v461_market_smt_turtle_soup_latest.json').read_text())
v462=json.loads((AUD/'v462_market_smt_independent_oracle_latest.json').read_text())
v463=json.loads((AUD/'v463_market_smt_frozen_t1_replay_latest.json').read_text())
if v461['decision']!='MARKET_SMT_SEEDS_READY__INDEPENDENT_ORACLE_NEXT':raise RuntimeError('V461 not ready')
if not v462['oracle_gate_pass'] or v462['mismatch_total']!=0:raise RuntimeError('V462 oracle failed')
if v463['invariants']['t1_violations']!=0 or v463['invariants']['search_count']!=1:raise RuntimeError('V463 integrity failed')
report={'version':'V464_MARKET_SMT_DIRECTION_CLOSURE','generated_at':datetime.now().isoformat(timespec='seconds'),
 'scope':'One distinct local-data cross-security SMT liquidity-divergence ontology; no production/frontend/watchlist writes.',
 'ontology':'MARKET_SMT_TURTLE_SOUP_SSL_REVERSAL','semantic_generation':{'source_seed_count':v461['source_seed_count'],'seed_count':v461['seed_count'],'yearly_seed_count':v461['yearly_seed_count'],'semantic_order_failures':v461['invariants']['semantic_order_failures'],'support_gate_pass':v461['support_gate']['pass']},
 'independent_oracle':{'expected_seed_count':v462['expected_seed_count'],'observed_seed_count':v462['observed_seed_count'],'mismatch_total':v462['mismatch_total'],'oracle_gate_pass':v462['oracle_gate_pass']},
 'frozen_t1_replay':{'overall':v463['overall'],'yearly':v463['yearly'],'epochs':v463['epochs'],'baseline_delta':v463['comparison_to_unconditioned_turtle_soup']['delta'],'t1_violations':v463['invariants']['t1_violations'],'search_count':v463['invariants']['search_count']},
 'promotion_gate_pass':v463['promotion_gate_pass'],
 'hard_findings':['SMT market-protected-higher-low context is semantically causal and independently reproduced with zero mismatches.','It raises aggregate gross WR only 0.4473 percentage points but lowers net>=0.8% win rate by 3.0510 points, AvgNet by 0.3719 points, payoff by 0.0853, and PF by 0.1908 versus unconditioned Turtle Soup.','Average net expectancy is negative overall and in 2023, 2024, and 2026; PF is below 1 overall and in those same years.','The direction is closed without market-index, pivot, divergence, stop, target, or hold variants.'],
 'production_state':'UNCHANGED_EMPTY_BOOK_FAIL_CLOSED','production_write':False,'frontend_write':False,'watchlist_write':False,
 'decision':'MARKET_SMT_CAUSAL_BUT_ECONOMICALLY_WORSE__CLOSE_ONTOLOGY_NO_VARIANTS',
 'artifacts':{'v461':str(AUD/'v461_market_smt_turtle_soup_latest.json'),'v462':str(AUD/'v462_market_smt_independent_oracle_latest.json'),'v463':str(AUD/'v463_market_smt_frozen_t1_replay_latest.json'),'latest':str(LATEST)}}
text=json.dumps(report,ensure_ascii=False,indent=2);LATEST.write_text(text);print(text)
