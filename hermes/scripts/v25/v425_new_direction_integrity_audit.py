#!/usr/bin/env python3
"""V425 independent chronology/T+1 integrity audit for V420-V424."""
import csv,json,math
from collections import Counter
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; K=ROOT/'kline_cache'
OUT=AUD/f'v425_new_direction_integrity_no_write_{datetime.now():%Y%m%d_%H%M%S}'; LATEST=AUD/'v425_new_direction_integrity_latest.json'
def report(name): return json.loads((AUD/name).read_text())
def rows(r):
    with Path(r['artifacts']['rows']).open(newline='') as h:return list(csv.DictReader(h))
def iv(x):
    try:return int(float(x))
    except:return None
def day(b):return ''.join(c for c in str(b.get('t') or b.get('date') or '') if c.isdigit())[:8]
def audit_seed(data,order,forbidden):
    bad=Counter()
    for r in data:
        vals=[iv(r.get(k)) for k in order]
        vals=[x for x in vals if x is not None]
        if any(b<=a for a,b in zip(vals,vals[1:])):bad['CHRONOLOGY']+=1
        if any(k in r for k in forbidden):bad['FORBIDDEN_FIELD']+=1
        if r.get('tradable')!='false' or r.get('buy_enabled')!='false':bad['TRADABLE_SEED']+=1
    return dict(bad)
def audit_trade(data):
    bad=Counter();cache={}
    for r in data:
        sym=r['symbol']
        if sym not in cache:
            raw=json.loads((K/f"{sym.replace('.','_')}_daily_750.json").read_text());cache[sym]={day(b):b for b in raw}
        b=cache[sym].get(r['entry_date'])
        if not b or abs(float(b['o'])-float(r['entry_price']))>1e-5:bad['ENTRY_NOT_SESSION_OPEN']+=1
        if r['exit_date']<=r['entry_date'] or str(r.get('t1_violation')).lower()=='true':bad['T1']+=1
    return dict(bad)
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    r420,r421,r422,r423,r424=[report(x) for x in ('v420_eql_spring_sos_lps_latest.json','v421_eql_spring_frozen_structural_replay_latest.json','v422_failed_breakdown_breaker_latest.json','v423_failed_breakdown_frozen_replay_latest.json','v424_failed_breakdown_hierarchical_replay_latest.json')]
    s420,s422=rows(r420),rows(r422);t421,t423,t424=rows(r421),rows(r423),rows(r424)
    forbidden=('entry_date','entry_price','exit_date','exit_price','pnl_pct','net_pnl_pct','won','mfe','mae')
    checks={
      'v420_seed':audit_seed(s420,['pool_low1_idx','pool_low2_idx','pool_confirm_idx','spring_idx','sos_idx','touch_idx','reclaim_idx','takeover_idx'],forbidden),
      'v422_seed':audit_seed(s422,['pivot_idx','pivot_confirm_idx','break_idx','recovery_idx','sos_idx','touch_idx','reclaim_idx','takeover_idx'],forbidden),
      'v421_trade':audit_trade(t421),'v423_trade':audit_trade(t423),'v424_trade':audit_trade(t424)}
    result={'version':'V425_NEW_DIRECTION_INTEGRITY_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,
      'counts':{'v420_seeds':len(s420),'v421_trades':len(t421),'v422_seeds':len(s422),'v423_trades':len(t423),'v424_trades':len(t424)},
      'checks':checks,'pass':all(not x for x in checks.values()),
      'decision':'INTEGRITY_PASS__ECONOMIC_RESULTS_VALID' if all(not x for x in checks.values()) else 'INTEGRITY_FAIL__DO_NOT_USE_RESULTS',
      'artifacts':{'out_dir':str(OUT),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2);(OUT/'v425_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
