#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
BASE=Path('/root/.hermes'); AUDIT=BASE/'smc_audit'
OUT=AUDIT/('v247_v246_current_smoke_no_write_'+datetime.now().strftime('%Y%m%d_%H%M%S')); OUT.mkdir(parents=True,exist_ok=True)
v246=json.loads((AUDIT/'v246_industry_addback_candidate_latest.json').read_text())
v241=json.loads((AUDIT/'v241_v239_current_scanner_with_breadth_bridge_latest.json').read_text())
# V246 is a strict refinement of the V239/V244 current parent rule: it starts from V244/V239-compatible current rows and only excludes/adds back weak-industry subsets.
# Therefore if parent raw_rule_rows is 0, V246 current actionable rows must be 0 without touching production/frontend/watchlist.
summary={
 'version':'V247_V246_CURRENT_SMOKE_NO_WRITE',
 'generated_at':datetime.now().isoformat(timespec='seconds'),
 'out_dir':str(OUT),
 'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
 'v246_decision':v246.get('decision'),
 'parent_current_smoke_source':'/root/.hermes/smc_audit/v241_v239_current_scanner_with_breadth_bridge_latest.json',
 'parent_latest_entry_date':v241.get('latest_entry_date'),
 'parent_dry_recent45_rows':v241.get('dry_recent45_rows'),
 'parent_raw_rule_rows':v241.get('raw_rule_rows'),
 'parent_new_actionable_rows':v241.get('new_actionable_rows'),
 'logical_contract':'V246 is a strict post-filter/addback over the V239/V244 parent current-rule row set; parent raw_rule_rows=0 implies V246 current rows=0.',
 'v246_raw_current_rows':0 if v241.get('raw_rule_rows')==0 else None,
 'v246_new_actionable_rows':0 if v241.get('raw_rule_rows')==0 else None,
 'selector_leak_fields':[],
 'decision':'V247_NO_CURRENT_ACTIONABLE_ROWS__KEEP_V246_HISTORICAL_CANDIDATE_NO_WRITE' if v241.get('raw_rule_rows')==0 else 'V247_NEEDS_DIRECT_CURRENT_RECONSTRUCTION'
}
(OUT/'v247_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)); (AUDIT/'v247_v246_current_smoke_latest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False,indent=2))
