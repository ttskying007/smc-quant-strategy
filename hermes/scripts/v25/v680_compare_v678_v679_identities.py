#!/usr/bin/env python3
"""V680 no-write exact identity comparison: frozen V678 generator vs V679 oracle."""
import csv, hashlib, json
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'
V678=AUD/'v678_outcome_blind_wdh_state_machine_seeds_latest.json'
V679=AUD/'v679_independent_wdh_identity_oracle_latest.json'
FIELDS=('symbol','weekly_permission_time','daily_ssl_time','daily_break_time','daily_ob_time','daily_first_touch_time','h60_ssl_time','h60_break_time','h60_ob_time','h60_hold_time')
def load_report(p): return json.loads(p.read_text())
def rows(path):
    with open(path,newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def key(x): return tuple(x.get(k,'') for k in FIELDS)
def digest(s):return hashlib.sha256('\n'.join('|'.join(x) for x in sorted(s)).encode()).hexdigest()
def main():
    a,b=load_report(V678),load_report(V679)
    if a.get('decision')!='V678_OUTCOME_BLIND_CHAIN_SEEDS_READY__INDEPENDENT_IDENTITY_ORACLE_REQUIRED':raise SystemExit('V678 not ready')
    if b.get('decision')!='V679_INDEPENDENT_ORACLE_IDENTITIES_READY__COMPARE_TO_FROZEN_V678':raise SystemExit('V679 not ready')
    ar=[x for x in rows(a['artifact']) if x.get('terminal')=='SEED_READY'];br=[x for x in rows(b['artifact']) if x.get('terminal')=='SEED_READY']
    aset,bset={key(x) for x in ar},{key(x) for x in br}
    out={'version':'V680_FROZEN_V678_V679_IDENTITY_COMPARISON_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'identity_fields':FIELDS,'v678_artifact':a['artifact'],'v679_artifact':b['artifact'],'v678_ready_rows':len(ar),'v679_ready_rows':len(br),'v678_unique':len(aset),'v679_unique':len(bset),'v678_sha256':digest(aset),'v679_sha256':digest(bset),'only_v678_count':len(aset-bset),'only_v679_count':len(bset-aset),'only_v678_samples':[dict(zip(FIELDS,x)) for x in sorted(aset-bset)[:50]],'only_v679_samples':[dict(zip(FIELDS,x)) for x in sorted(bset-aset)[:50]],'decision':'V680_IDENTITY_EXACT_MATCH__ONE_FROZEN_T1_REPLAY_AUTHORIZED' if aset==bset and len(ar)==len(aset) and len(br)==len(bset) else 'V680_IDENTITY_DIFFERENTIAL_FAIL__STOP_BEFORE_REPLAY'}
    text=json.dumps(out,ensure_ascii=False,indent=2);(AUD/'v680_frozen_v678_v679_identity_comparison_latest.json').write_text(text);print(text)
if __name__=='__main__':main()
