#!/usr/bin/env python3
"""V692 no-write reconciliation of the completed W/D/60m research frontier.

This is a ledger, not another signal generator.  It reads only authoritative
reports and the production registry, verifies their required decisions, and
states whether any currently authorized price-only ontology remains eligible.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; REG=ROOT/'smc_monitor/production_registry.json'
SPECS=[
 ('V677 source+semantic', 'v677_three_timeframe_semantic_source_audit_latest.json', 'V677_SOURCE_AND_SEMANTIC_AUDIT_PASS__OUTCOME_BLIND_STATE_MACHINE_SEEDS_ALLOWED'),
 ('V678/V679 exact original chain', 'v680_frozen_v678_v679_identity_comparison_latest.json', 'V680_IDENTITY_EXACT_MATCH__ONE_FROZEN_T1_REPLAY_AUTHORIZED'),
 ('V683 original-chain lifecycle audit', 'v683_wdh_lifecycle_cancellation_audit_latest.json', 'V683_LIFECYCLE_INVARIANT_FAIL__V678_V679_IDENTITIES_INVALID_FOR_REPLAY'),
 ('V684 lifecycle-safe differential', 'v686_frozen_v684_v685_identity_comparison_latest.json', 'V686_LIFECYCLE_SAFE_IDENTITY_DIFFERENTIAL_FAIL__STOP_BEFORE_REPLAY'),
 ('V687/V688 unique-liquidity exact identity', 'v689_frozen_v687_v688_identity_comparison_latest.json', 'V689_UNIQUE_LIQUIDITY_IDENTITY_EXACT_MATCH__ONE_FROZEN_T1_REPLAY_AUTHORIZED'),
 ('V690 pre-outcome support gate', 'v690_v687_outcome_blind_support_gate_latest.json', 'V690_SUPPORT_FAIL__CLOSE_V687_WITHOUT_REPLAY__EMPTY_BOOK'),
]

def main():
    chain=[]; ok=True
    for label,name,expected in SPECS:
        path=AUD/name
        try:
            report=json.loads(path.read_text())
            actual=report.get('decision')
            matched=actual==expected
        except Exception as exc:
            actual=f'ERROR:{type(exc).__name__}:{exc}'; matched=False
        ok &= matched
        chain.append({'stage':label,'artifact':str(path),'expected_decision':expected,'actual_decision':actual,'verified':matched})
    reg=json.loads(REG.read_text())
    registry_ok=(reg.get('state')=='FAIL_CLOSED_REPLAY_GATE_FAILED' and reg.get('buy_enabled') is False and reg.get('active_buy_valid_count')==0)
    report={
      'version':'V692_WDH_RESEARCH_FRONTIER_RECONCILIATION_NO_WRITE',
      'generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'chain':chain,
      'production_registry':{'artifact':str(REG),'state':reg.get('state'),'buy_enabled':reg.get('buy_enabled'),'active_buy_valid_count':reg.get('active_buy_valid_count'),'verified_empty_book':registry_ok},
      'unambiguous_findings':[
        'The raw three-timeframe source and primitive semantics are qualified (V677).',
        'The original V678 chain cannot be interpreted as an economic test: V683 found 762 of 1,579 ready identities violated one or more pre-entry hard lifecycle cancellations.',
        'The lifecycle-safe V684 formulation is closed before replay because independent implementations disagreed on an undefined multi-pool sweep reference.',
        'The V687 repaired formulation resolved that identity ambiguity (813/813 exact identities) but fails the predeclared full-universe support floor n>=1000 before outcomes are opened.',
        'No completed, authorized W/D/60m price-only ontology remains eligible for a new replay under the current information set.'
      ],
      'not_permitted_next':[
        'Do not replay V678/V679, V684/V685, or V687/V688.',
        'Do not lower the n>=1000 support floor, select dates/stocks, or borrow V681 outcomes to create a selector.',
        'Do not modify pivots, time windows, POI, stop/target, hold, or liquidity ordering within closed ontologies.'
      ],
      'only_qualitative_research_frontier':[
        'A genuinely independent, point-in-time information dimension or a full-history independent market microstructure/source qualification may start a new ontology.',
        'Before a new ontology: source/PIT coverage audit -> outcome-blind seeds -> independent oracle exact identity -> pre-outcome support gate -> one frozen strict T+1 replay.',
        'With only the already-qualified W/D/60m OHLCV information, maintain source-health/coverage monitoring rather than opening another price-derived variant.'
      ],
      'decision':'V692_WDH_PRICE_ONLY_FRONTIER_CLOSED__EMPTY_BOOK__SOURCE_QUALIFICATION_ONLY' if ok and registry_ok else 'V692_RECONCILIATION_CONTRACT_FAILURE__EMPTY_BOOK'
    }
    text=json.dumps(report,ensure_ascii=False,indent=2)
    (AUD/'v692_wdh_research_frontier_reconciliation_latest.json').write_text(text,encoding='utf-8')
    print(text)
if __name__=='__main__': main()
