#!/usr/bin/env python3
"""Aggregate immutable V677 audit shards into one no-write source-audit verdict."""
import json
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'
reports=[]
for p in AUD.glob('v677_weekly_daily_m60_pure_smc_source_audit_no_write_*/v677_report.json'):
    try:
        x=json.loads(p.read_text())
        if x.get('shard_count')==12: reports.append((p,x))
    except Exception: pass
reports=sorted(reports,key=lambda q:q[1]['shard_index'])
latest={}
for p,x in reports: latest[x['shard_index']]=(p,x)
chosen=[latest[i] for i in range(12) if i in latest]
missing=[i for i in range(12) if i not in latest]
counts={'symbols':0,'pass':0,'fail':0,'input_daily_files':0,'semantic_differential_rows':0,'exceptions':0}
rows=[]; samples=[]
for p,x in chosen:
    for k in counts: counts[k]+=x['counts'].get(k,0)
    samples+=x.get('failure_samples',[])
    rows.append({'shard_index':x['shard_index'],'report':str(p),'symbol_rows':x['artifacts']['symbol_rows'],'counts':x['counts'],'decision':x['decision']})
ok=not missing and counts['symbols']==4654 and counts['pass']==4654 and not counts['fail'] and not counts['semantic_differential_rows'] and not counts['exceptions']
out={'version':'V677_WEEKLY_DAILY_M60_PURE_SMC_SOURCE_AUDIT_AGGREGATE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'research_only':True,'production_write':False,'outcomes_included':False,'shard_contract':'12 deterministic source-audit shards; same source and semantics as V677','counts':counts,'missing_shards':missing,'shards':rows,'decision':'V677_SOURCE_AGGREGATION_SEMANTIC_PASS__V678_ALLOWED' if ok else 'V677_FAIL_CLOSED__STOP_BEFORE_V678','failure_samples':samples[:50]}
text=json.dumps(out,ensure_ascii=False,indent=2)
(AUD/'v677_weekly_daily_m60_pure_smc_source_audit_latest.json').write_text(text)
print(text)
