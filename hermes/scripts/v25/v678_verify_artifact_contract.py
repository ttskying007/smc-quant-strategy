#!/usr/bin/env python3
"""Verify a completed V678 artifact after canonical W/D/H timestamp normalization."""
import csv, hashlib, json
from collections import Counter
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes'); AUDIT=ROOT/'smc_audit'
report=json.loads((AUDIT/'v678_outcome_blind_wdh_state_machine_seeds_latest.json').read_text())
path=Path(report['artifact'])
def key(v): return ''.join(c for c in v if c.isdigit())
rows=list(csv.DictReader(path.open()))
ready=[r for r in rows if r['terminal']=='SEED_READY']
cols=['weekly_permission_time','daily_ssl_time','daily_break_time','daily_first_touch_time','h60_first_touch_time','h60_ssl_time','h60_break_time','h60_reclaim_time','h60_hold_time','next_h60_open_time']
chronology=all(all(key(r[cols[i]])<key(r[cols[i+1]]) for i in range(len(cols)-1)) for r in ready)
identities={(r['symbol'],r['weekly_permission_time'],r['daily_ssl_time'],r['daily_break_time'],r['daily_ob_time'],r['daily_first_touch_time'],r['h60_ssl_time'],r['h60_break_time'],r['h60_ob_time'],r['h60_hold_time']) for r in ready}
forbidden={'pnl','return','exit','sl','tp','mfe','mae','win','loss','risk','rr','hold_bars','volume_filter'}
actual={x.lower() for x in rows[0]} if rows else set()
leak=sorted(actual&forbidden)
out={'version':'V678_ARTIFACT_CONTRACT_VERIFICATION_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'source_report':str(AUDIT/'v678_outcome_blind_wdh_state_machine_seeds_latest.json'),'seed_artifact':str(path),'artifact_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'rows':len(rows),'terminal_counts':dict(Counter(r['terminal'] for r in rows)),'ready':len(ready),'unique_identity_count':len(identities),'canonical_timestamp_chronology_pass':chronology,'forbidden_field_leaks':leak,'decision':'V678_OUTCOME_BLIND_CHAIN_SEEDS_READY__INDEPENDENT_IDENTITY_ORACLE_REQUIRED' if chronology and not leak and len(ready)==len(identities) else 'V678_ARTIFACT_CONTRACT_FAIL__STOP_BEFORE_ORACLE'}
outpath=AUDIT/'v678_artifact_contract_verification_latest.json';outpath.write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False,indent=2))
