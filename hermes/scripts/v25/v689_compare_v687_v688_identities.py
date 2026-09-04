#!/usr/bin/env python3
"""V689 exact identity compare: V687 unique-liquidity seeds vs V688 oracle."""
import csv, hashlib, json
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'
V687=AUD/'v687_unique_liquidity_lifecycle_safe_seeds_latest.json'; V688=AUD/'v688_independent_unique_liquidity_identity_oracle_latest.json'
OUT=AUD/'v689_frozen_v687_v688_identity_comparison_latest.json'
# Pool identity is explicit: same event timestamp but different pivot is a different object.
FIELDS=('symbol','weekly_permission_time','daily_ssl_time','daily_ssl_pivot_time','daily_break_time','daily_ob_time','daily_first_touch_time','h60_ssl_time','h60_ssl_pivot_time','h60_break_time','h60_ob_time','h60_hold_time')
def load(path):
 with open(path,newline='',encoding='utf-8') as h:return list(csv.DictReader(h))
def key(x):return tuple(x.get(k,'') for k in FIELDS)
def digest(s):return hashlib.sha256('\n'.join('|'.join(x) for x in sorted(s)).encode()).hexdigest()
def main():
 a,b=json.loads(V687.read_text()),json.loads(V688.read_text())
 if a.get('decision')!='V687_UNIQUE_LIQUIDITY_CHAIN_SEEDS_READY__INDEPENDENT_ORACLE_REQUIRED':raise SystemExit('V687 not ready')
 if b.get('decision')!='V688_INDEPENDENT_UNIQUE_LIQUIDITY_IDENTITIES_READY__COMPARE_TO_FROZEN_V687':raise SystemExit('V688 not ready')
 ar=[x for x in load(a['artifact']) if x.get('terminal')=='SEED_READY'];br=[x for x in load(b['artifact']) if x.get('terminal')=='SEED_READY']; aset,bset={key(x) for x in ar},{key(x) for x in br}
 report={'version':'V689_FROZEN_V687_V688_UNIQUE_LIQUIDITY_IDENTITY_COMPARISON_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'identity_fields':FIELDS,'v687_artifact':a['artifact'],'v688_artifact':b['artifact'],'v687_ready_rows':len(ar),'v688_ready_rows':len(br),'v687_unique':len(aset),'v688_unique':len(bset),'v687_sha256':digest(aset),'v688_sha256':digest(bset),'only_v687_count':len(aset-bset),'only_v688_count':len(bset-aset),'only_v687_samples':[dict(zip(FIELDS,x)) for x in sorted(aset-bset)[:50]],'only_v688_samples':[dict(zip(FIELDS,x)) for x in sorted(bset-aset)[:50]],'decision':'V689_UNIQUE_LIQUIDITY_IDENTITY_EXACT_MATCH__ONE_FROZEN_T1_REPLAY_AUTHORIZED' if aset==bset and len(ar)==len(aset) and len(br)==len(bset) else 'V689_UNIQUE_LIQUIDITY_IDENTITY_DIFFERENTIAL_FAIL__STOP_BEFORE_REPLAY'}
 OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(OUT.read_text())
if __name__=='__main__':main()
