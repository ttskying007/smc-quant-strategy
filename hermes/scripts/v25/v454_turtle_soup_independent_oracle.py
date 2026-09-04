#!/usr/bin/env python3
"""V454 independent raw-bar semantic oracle for V453; reads no outcomes."""
from __future__ import annotations
import csv,json,math
from collections import Counter
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
SRC=AUD/'v453_turtle_soup_ssl_reversal_latest.json'
OUT=AUD/f"v454_turtle_soup_independent_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST=AUD/'v454_turtle_soup_independent_oracle_latest.json'
FORBIDDEN=('entry_price','exit','pnl','mfe','mae','target','tp','rr','hold_bars','won','outcome')

def f(x):
    try:
        v=float(x); return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError): return 0.0

def i(x): return int(float(x))
def ds(x): return ''.join(c for c in str(x or '') if c.isdigit())[:8]

def load(sym):
    try: raw=json.loads((KDIR/f"{sym.replace('.','_')}_daily_750.json").read_text())
    except (OSError,json.JSONDecodeError): return []
    rows=[]
    for b in raw:
        r={k:f(b.get(k)) for k in ('o','h','l','c')}; d=ds(b.get('t') or b.get('date'))
        if d and all(r.values()): r['t']=d; rows.append(r)
    return sorted(rows,key=lambda r:r['t'])

def close(a,b): return abs(a-b)<=max(1e-6,abs(b)*1e-6)

def verify(row,bars):
    try: pivot,visible,raid,confirm,eligible=(i(row[k]) for k in ('ssl_idx','ssl_confirm_idx','raid_idx','reversal_confirm_idx','eligible_entry_idx'))
    except (KeyError,ValueError): return 'BAD_INDEX'
    if not (3<=pivot<len(bars)-3 and visible==pivot+3<raid<confirm<eligible==confirm+1<len(bars)): return 'INDEX_OR_CHRONOLOGY'
    if raid-pivot>60 or confirm-raid>3: return 'FROZEN_WINDOW'
    if not all(bars[j]['l']>bars[pivot]['l'] for j in range(pivot-3,pivot+4) if j!=pivot): return 'NOT_UNIQUE_3_3_LOW'
    if not (bars[raid]['l']<bars[pivot]['l']*.997 and bars[raid]['c']>bars[pivot]['l']): return 'RAID_GEOMETRY'
    refs=[]
    for p in range(max(3,raid-60),raid-3):
        if p+3<raid and all(bars[j]['l']>bars[p]['l'] for j in range(p-3,p+4) if j!=p) and bars[raid]['l']<bars[p]['l']*.997 and bars[raid]['c']>bars[p]['l']:
            refs.append(p)
    if not refs or max(refs)!=pivot: return 'NOT_MOST_RECENT_SWEPT_SSL'
    first=next((j for j in range(raid+1,min(len(bars),raid+4)) if bars[j]['c']>bars[raid]['h']),None)
    if first!=confirm: return 'NOT_FIRST_CLOSE_ABOVE_RAID_HIGH'
    if not (close(f(row['ssl_price']),bars[pivot]['l']) and close(f(row['raid_low']),bars[raid]['l']) and close(f(row['raid_high']),bars[raid]['h'])): return 'PRICE_MISMATCH'
    dates={'raid_date':raid,'reversal_confirm_date':confirm,'eligible_entry_date':eligible}
    if any(ds(row.get(k))!=bars[idx]['t'] for k,idx in dates.items()): return 'DATE_MISMATCH'
    return 'PASS'

def main():
    OUT.mkdir(parents=True,exist_ok=True); report=json.loads(SRC.read_text())
    with open(report['artifacts']['seeds']) as h:
        reader=csv.DictReader(h); headers=reader.fieldnames or []; rows=list(reader)
    forbidden=[h for h in headers if h!='no_outcome_fields' and any(x in h.lower() for x in FORBIDDEN)]
    cache={}; counts=Counter(); passed=[]; mismatches=[]
    for n,row in enumerate(rows,1):
        sym=row['symbol']
        if sym not in cache: cache[sym]=load(sym)
        reason=verify(row,cache[sym]) if cache[sym] else 'MISSING_KLINE'; counts[reason]+=1
        if reason=='PASS': passed.append(row)
        elif len(mismatches)<1000: mismatches.append({'symbol':sym,'eligible_entry_date':row.get('eligible_entry_date',''),'reason':reason})
        if n%50000==0: print(json.dumps({'progress':n,'passed':len(passed)}),flush=True)
    pass_file=OUT/'v454_oracle_passed_seeds.csv'; mismatch_file=OUT/'v454_mismatches.csv'
    with pass_file.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=headers); w.writeheader(); w.writerows(passed)
    with mismatch_file.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=['symbol','eligible_entry_date','reason']); w.writeheader(); w.writerows(mismatches)
    mismatch=len(rows)-len(passed); gate=mismatch==0 and not forbidden
    result={'version':'V454_TURTLE_SOUP_INDEPENDENT_ORACLE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),
      'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'source_seed_count':len(rows),'oracle_pass_count':len(passed),'failure_counts':dict(counts),'mismatch_total':mismatch,
      'forbidden_outcome_headers':forbidden,'duplicate_symbol_entry':len(passed)-len(set((r['symbol'],r['eligible_entry_date']) for r in passed)),
      'oracle_gate_pass':gate,'decision':'INDEPENDENT_ORACLE_PASS__FROZEN_T1_REPLAY_ALLOWED' if gate else 'ORACLE_FAIL__NO_REPLAY',
      'artifacts':{'out_dir':str(OUT),'passed_seeds':str(pass_file),'mismatches':str(mismatch_file),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2); (OUT/'v454_report.json').write_text(text); LATEST.write_text(text); print(text)
if __name__=='__main__': main()
