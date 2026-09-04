#!/usr/bin/env python3
"""V468 consolidate and close the ex-stock industry-SMT direction."""
import json
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes');AUD=ROOT/'smc_audit'
a=json.loads((AUD/'v465_industry_smt_turtle_soup_latest.json').read_text())
b=json.loads((AUD/'v466_industry_smt_independent_oracle_latest.json').read_text())
c=json.loads((AUD/'v467_industry_smt_frozen_t1_replay_latest.json').read_text())
r={'version':'V468_INDUSTRY_SMT_DIRECTION_CLOSURE','generated_at':datetime.now().isoformat(timespec='seconds'),
'scope':'One distinct local-data ex-stock industry SMT liquidity-divergence ontology; no production/frontend/watchlist writes.',
'ontology':'INDUSTRY_SMT_TURTLE_SOUP_SSL_REVERSAL',
'semantic_generation':{'source_seed_count':a['source_seed_count'],'seed_count':a['seed_count'],'yearly_seed_count':a['yearly_seed_count'],'semantic_order_failures':a['invariants']['semantic_order_failures'],'support_gate_pass':a['support_gate']['pass']},
'independent_oracle':{'expected_seed_count':b['expected_seed_count'],'observed_seed_count':b['observed_seed_count'],'mismatch_total':b['mismatch_total'],'oracle_gate_pass':b['oracle_gate_pass']},
'frozen_t1_replay':{'overall':c['overall'],'yearly':c['yearly'],'epochs':c['epochs'],'baseline_delta':c['comparison_to_unconditioned_turtle_soup']['delta'],'market_smt_delta':c['comparison_to_market_smt']['delta'],'t1_violations':c['invariants']['t1_violations'],'search_count':c['invariants']['search_count']},
'promotion_gate_pass':c['promotion_gate_pass'],
'hard_findings':['Ex-stock industry SMT semantics are causal, abundant, and independently reproduced with zero mismatches.','Gross WR rises 1.0445pp versus unconditioned Turtle Soup, but net>=0.8% WR falls 2.8041pp, AvgNet falls 0.3184pp, payoff falls 0.0858, and PF falls 0.1656.','Overall AvgNet is -0.1207% and PF 0.9351; 2023, 2024, and 2026 have negative expectancy and PF<1.','The direction is closed without industry-map, minimum-peer, pivot, divergence, stop, target, or hold variants.'],
'production_state':'UNCHANGED_EMPTY_BOOK_FAIL_CLOSED','production_write':False,'frontend_write':False,'watchlist_write':False,
'decision':'INDUSTRY_SMT_CAUSAL_BUT_ECONOMICALLY_NEGATIVE__CLOSE_ONTOLOGY_NO_VARIANTS',
'artifacts':{'v465':str(AUD/'v465_industry_smt_turtle_soup_latest.json'),'v466':str(AUD/'v466_industry_smt_independent_oracle_latest.json'),'v467':str(AUD/'v467_industry_smt_frozen_t1_replay_latest.json'),'latest':str(AUD/'v468_industry_smt_direction_closure_latest.json')}}
(AUD/'v468_industry_smt_direction_closure_latest.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False,indent=2))
