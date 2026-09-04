#!/usr/bin/env python3
"""V654 source-only official-margin coverage/PIT audit; reads no outcomes."""
from __future__ import annotations
import gzip,json
from collections import Counter
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; BASE=ROOT/'pit_cache/v562_exchange_margin_raw'
OUT=AUD/'v654_two_sided_leverage_source_pit_audit_latest.json'; YEARS=('2023','2024','2025')
def valid(ex,p):
 try:
  with gzip.open(p,'rt',encoding='utf8') as h:d=json.load(h)
  rows=d.get('rows') or []
  required=('financing_buy','financing_balance','lending_balance')
  return d.get('source')==f'{ex}_official_exchange' and d.get('exchange')==ex and d.get('date')==p.name[:8] and len(rows)>=500 and all(all(k in r for k in required) for r in rows)
 except (OSError,ValueError,TypeError):return False
def audit(ex):
 good=[];bad=[]
 for p in sorted((BASE/ex).glob('20*.json.gz')):
  (good if valid(ex,p) else bad).append(p.name[:8])
 c=Counter(d[:4] for d in good)
 return {'valid_dates':len(good),'invalid_dates':bad,'year_counts':{y:c[y] for y in sorted(c)},'range':[min(good),max(good)] if good else []}
def main():
 sh,sz=audit('SH'),audit('SZ'); expected={'2023':242,'2024':242,'2025':243}
 coverage=all(sh['year_counts'].get(y)==expected[y] and sz['year_counts'].get(y)==expected[y] for y in YEARS)
 pre=json.loads((AUD/'v654_two_sided_leverage_convergence_fvg_preregistration.json').read_text())
 rep={'version':'V654_TWO_SIDED_LEVERAGE_SOURCE_COVERAGE_PIT_AUDIT_NO_OUTCOME','generated_at':datetime.now().isoformat(timespec='seconds'),'research_only':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source':'Official SSE/SZSE stored raw per-stock margin reports only; no cross-source fill.','fields_verified':['financing_buy','financing_balance','lending_balance'],'coverage':{'SH':sh,'SZ':sz,'expected_complete_year_sessions':expected,'complete_decision_years_2023_2025':coverage},'pit_timing':{'same_session_feature_use_forbidden':True,'generator_contract':'event M < first response session; reclaim < planned next-open entry','official_record_availability_contract':'daily record is only eligible after M completes; no same-date decision is permitted'},'decision':'V654_SOURCE_PIT_PASS__OUTCOME_BLIND_SEED_AUTHORIZED' if coverage and pre['decision'].startswith('PREREGISTRATION_COMPLETE') else 'V654_SOURCE_PIT_FAIL__CLOSE_ONTOLOGY_NO_SEED'}
 OUT.write_text(json.dumps(rep,ensure_ascii=False,indent=2));print(json.dumps(rep,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
