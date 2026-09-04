#!/usr/bin/env python3
"""V353 no-write persistent-takeover validator for V352 lifecycle rows.

A one-bar hold is not sufficient evidence of smart-money takeover.  This audit
requires two additional closes above the OB and no zone-low close break.  It
remains lifecycle-only: no entry, PnL, exit, or production writes.
"""
from __future__ import annotations
import csv, json, math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes'); AUD = ROOT / 'smc_audit'; KDIR = ROOT / 'kline_cache'
SRC = AUD / 'v352_continuation_lifecycle_latest.json'
OUT = AUD / f"v353_persistent_takeover_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST = AUD / 'v353_persistent_takeover_latest.json'

def f(x):
    try:
        x=float(x); return x if math.isfinite(x) else 0.
    except (TypeError, ValueError): return 0.
def d(b): return ''.join(c for c in str(b.get('t') or b.get('date') or '') if c.isdigit())[:8]
def bars(sym):
    try: x=json.loads((KDIR/f"{sym.replace('.', '_')}_daily_750.json").read_text())
    except Exception: return []
    return sorted(x,key=d)
def persistent(ks,row):
    dates={d(b):i for i,b in enumerate(ks)}; i=dates.get(row['takeover_date']); low,high=f(row['zone_low']),f(row['zone_high'])
    if i is None or i+2>=len(ks): return 'PERSISTENCE_UNOBSERVED'
    for j in range(i+1,i+3):
        if f(ks[j].get('c'))<low: return 'PERSISTENCE_ZONE_INVALIDATED'
        if f(ks[j].get('c'))<=high: return 'PERSISTENCE_REENTERED_ZONE'
    return 'PERSISTENT_TAKEOVER'
def main():
    OUT.mkdir(parents=True,exist_ok=True); rep=json.loads(SRC.read_text())
    with Path(rep['artifacts']['rows']).open() as inp: rows=list(csv.DictReader(inp))
    cache={}; counts=Counter(); years={}; output=[]
    for row in rows:
        prior=row['lifecycle_state']; status=prior
        if prior=='TAKEOVER_CONFIRMED':
            sym=row['symbol']; cache.setdefault(sym,bars(sym)); status=persistent(cache[sym],row)
        # Cohort by event date, not later takeover date; otherwise Dec events leak into
        # the following year's denominator and annual stability becomes distorted.
        counts[status] += 1
        year = row.get('event_date','')[:4]
        years.setdefault(year,Counter())[status]+=1; years[year]['all']+=1
        row['lifecycle_state']=status; row['tradable']='false'; row['buy_enabled']='false'; output.append(row)
    fields=list(output[0]) if output else ['symbol','lifecycle_state']
    with (OUT/'v353_persistent_lifecycle_rows.csv').open('w',newline='') as out:
        w=csv.DictWriter(out,fieldnames=fields);w.writeheader();w.writerows(output)
    annual=[]
    for year,x in sorted(years.items()):
        base=x['TAKEOVER_CONFIRMED']+x['PERSISTENT_TAKEOVER']+x['PERSISTENCE_UNOBSERVED']+x['PERSISTENCE_ZONE_INVALIDATED']+x['PERSISTENCE_REENTERED_ZONE']
        persistent_n=x['PERSISTENT_TAKEOVER'];annual.append({'year':year,'all_semantic_seeds':x['all'],'one_bar_takeovers':base,'persistent_takeovers':persistent_n,'persistent_of_takeovers_pct':round(persistent_n/base*100,2) if base else 0})
    result={'version':'V353_PERSISTENT_TAKEOVER_LIFECYCLE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'contract':'V352 takeover + next two daily closes > zone_high; any close < zone_low cancels','stage_counts':dict(counts),'yearly':annual,'invariants':{'no_entries_created':True,'no_outcome_fields':True,'all_non_tradable':all(x['tradable']=='false' for x in output)},'decision':'PERSISTENT_TAKEOVER_EVIDENCE_READY__60MIN_STILL_BLOCKED','artifacts':{'out_dir':str(OUT),'rows':str(OUT/'v353_persistent_lifecycle_rows.csv'),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2);(OUT/'v353_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
