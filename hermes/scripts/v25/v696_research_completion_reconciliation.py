#!/usr/bin/env python3
"""V696 no-write reconciliation of the complete authorized research frontier."""
from __future__ import annotations
import hashlib, json
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; REG=ROOT/'smc_monitor/production_registry.json'

def load(p): return json.loads(Path(p).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    v692=load(AUD/'v692_wdh_research_frontier_reconciliation_latest.json')
    v695=load(AUD/'v695_v694_short_covering_frontier_closure_latest.json')
    v536=load(AUD/'v536_multitf_source_monitor_latest.json')
    v693=load(AUD/'v693_v536_source_monitor_maintenance_reconciliation_latest.json')
    v660=load(AUD/'v660_post_v654_authorized_source_inventory_no_write_20260730.json')
    v601=load(AUD/'v601_current_qualified_strategy_frontier_latest.json')
    reg=load(REG)
    assertions={
      'v692_price_only_closed': v692.get('decision')=='V692_WDH_PRICE_ONLY_FRONTIER_CLOSED__EMPTY_BOOK__SOURCE_QUALIFICATION_ONLY',
      'v695_new_pit_closed_before_replay': v695.get('decision')=='V695_V694_SUPPORT_FAIL__CLOSE_SHORT_COVERING_ONTOLOGY_WITHOUT_ORACLE_OR_REPLAY__EMPTY_BOOK',
      'v695_no_outcomes_opened': v695.get('gate_reason',{}).get('outcomes_opened') is False,
      'v660_inventory_terminal': v660.get('decision')=='NO_NEW_AUTHORIZED_SOURCE_FOUND__DO_NOT_REOPEN_CLOSED_ONTOLOGIES__EMPTY_BOOK_REMAINS__WAIT_FOR_GENUINELY_NEW_PIT_RAW_SOURCE',
      'v601_no_qualified_strategy': 'NO_QUALIFIED_STRATEGY' in v601.get('decision',''),
      'source_primary_healthy': v536.get('state')=='PRIMARY_SOURCE_HEALTHY' and v536.get('cache_build_allowed') is True,
      'source_audit_pass': v693.get('full_cache_audit',{}).get('decision')=='SOURCE_ISOLATED_CACHE_PASS',
      'source_monitor_timer_enabled': v693.get('cadence',{}).get('timer_enabled') is True,
      'registry_fail_closed': reg.get('buy_enabled') is False and reg.get('active_buy_valid_count')==0 and reg.get('production_strategy') is None,
      'no_production_writes': all(x.get('production_write') is False for x in (v692,v695)) and v693.get('cadence',{}).get('production_write') is False and v693.get('cadence',{}).get('watchlist_write') is False and v693.get('cadence',{}).get('position_write') is False and v693.get('cadence',{}).get('registry_write') is False,
    }
    report={
      'version':'V696_COMPLETE_RESEARCH_FRONTIER_RECONCILIATION_NO_WRITE',
      'generated_at':datetime.now().isoformat(timespec='seconds'),
      'scope':'V382-V695 authorized research inventory, latest source qualification, and production boundary',
      'completed_work':[
        'Current qualified OHLCV pure-SMC W/D/60m frontier: V692 terminal closed.',
        'New independent PIT margin short-covering contraction ontology: V694 support measured, V695 closed before Oracle/replay.',
        'No other qualified independent PIT source remains in the local inventory: V660 terminal inventory.',
        'V536 same-source health monitor and 2,861-symbol Baostock isolated cache audit maintained; Sina/Tencent remain witnesses only.'
      ],
      'assertions':assertions,
      'all_assertions_pass':all(assertions.values()),
      'source_monitor_artifact':str(AUD/'v693_v536_source_monitor_maintenance_reconciliation_latest.json'),
      'production_registry':{'path':str(REG),'sha256':sha(REG),'state':reg.get('state'),'buy_enabled':reg.get('buy_enabled'),'active_buy_valid_count':reg.get('active_buy_valid_count'),'production_strategy':reg.get('production_strategy'),'forbidden_fallback':reg.get('forbidden_fallback')},
      'available_next_step':'No strategy iteration is authorized. Continue only scheduled source-health/coverage monitoring. Reopen research only after a genuinely new independent PIT dimension or a complete canonical historical microstructure source passes source-only qualification.',
      'decision':'V696_RESEARCH_GOAL_COMPLETE_UNDER_AVAILABLE_INFORMATION__NO_QUALITATIVE_CHANGE__EMPTY_BOOK__SOURCE_MONITORING_ONLY' if all(assertions.values()) else 'V696_RECONCILIATION_FAIL__DO_NOT_REOPEN_ANY_ONTOLOGY'
    }
    out=AUD/'v696_complete_research_frontier_reconciliation_latest.json'; tmp=out.with_suffix('.tmp'); tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2)); tmp.replace(out); print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
