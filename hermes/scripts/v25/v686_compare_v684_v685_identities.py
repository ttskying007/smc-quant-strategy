#!/usr/bin/env python3
"""V686 exact identity comparison: lifecycle-safe V684 vs independent V685."""
import csv, hashlib, json
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'
V684=AUD/'v684_lifecycle_safe_wdh_state_machine_seeds_latest.json'
V685=AUD/'v685_independent_lifecycle_safe_wdh_identity_oracle_latest.json'
OUT=AUD/'v686_frozen_v684_v685_identity_comparison_latest.json'
FIELDS=('symbol','weekly_permission_time','daily_ssl_time','daily_break_time','daily_ob_time','daily_first_touch_time','h60_ssl_time','h60_break_time','h60_ob_time','h60_hold_time')
def rows(path):
    with open(path,newline='',encoding='utf-8') as h:return list(csv.DictReader(h))
def key(x):return tuple(x.get(k,'') for k in FIELDS)
def digest(s):return hashlib.sha256('\n'.join('|'.join(x) for x in sorted(s)).encode()).hexdigest()
def main():
    a,b=json.loads(V684.read_text()),json.loads(V685.read_text())
    if a.get('decision')!='V684_LIFECYCLE_SAFE_CHAIN_SEEDS_READY__INDEPENDENT_IDENTITY_ORACLE_REQUIRED':raise SystemExit('V684 not ready')
    if b.get('decision')!='V685_INDEPENDENT_LIFECYCLE_ORACLE_IDENTITIES_READY__COMPARE_TO_FROZEN_V684':raise SystemExit('V685 not ready')
    ar=[x for x in rows(a['artifact']) if x.get('terminal')=='SEED_READY']; br=[x for x in rows(b['artifact']) if x.get('terminal')=='SEED_READY']
    aset,bset={key(x) for x in ar},{key(x) for x in br}
    report={'version':'V686_FROZEN_V684_V685_LIFECYCLE_SAFE_IDENTITY_COMPARISON_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'identity_fields':FIELDS,'v684_artifact':a['artifact'],'v685_artifact':b['artifact'],'v684_ready_rows':len(ar),'v685_ready_rows':len(br),'v684_unique':len(aset),'v685_unique':len(bset),'v684_sha256':digest(aset),'v685_sha256':digest(bset),'only_v684_count':len(aset-bset),'only_v685_count':len(bset-aset),'only_v684_samples':[dict(zip(FIELDS,x)) for x in sorted(aset-bset)[:50]],'only_v685_samples':[dict(zip(FIELDS,x)) for x in sorted(bset-aset)[:50]],'decision':'V686_LIFECYCLE_SAFE_IDENTITY_EXACT_MATCH__ONE_FROZEN_T1_REPLAY_AUTHORIZED' if aset==bset and len(ar)==len(aset) and len(br)==len(bset) else 'V686_LIFECYCLE_SAFE_IDENTITY_DIFFERENTIAL_FAIL__STOP_BEFORE_REPLAY'}
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(OUT.read_text())
if __name__=='__main__':main()
