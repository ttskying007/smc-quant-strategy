#!/usr/bin/env python3
"""V448 independent raw-bar oracle for V447 SSL/BPR seeds; no outcomes opened."""
from __future__ import annotations
import csv, json, math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
SRC=AUD/'v447_ssl_bpr_reversal_generator_latest.json'
OUT=AUD/f"v448_ssl_bpr_independent_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST=AUD/'v448_ssl_bpr_independent_oracle_latest.json'
FORBIDDEN=('entry_price','exit','pnl','mfe','mae','target','tp','rr','hold_bars','won','outcome')

def f(x):
    try:
        v=float(x); return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError): return 0.0

def i(x): return int(float(x))
def day(x): return ''.join(c for c in str(x or '') if c.isdigit())[:8]

def load(sym):
    try: raw=json.loads((KDIR/f"{sym.replace('.','_')}_daily_750.json").read_text())
    except (OSError,json.JSONDecodeError): return []
    rows=[]
    for b in raw:
        d=day(b.get('t') or b.get('date')); r={k:f(b.get(k)) for k in ('o','h','l','c')}
        if d and all(r.values()): r['t']=d; rows.append(r)
    return sorted(rows,key=lambda x:x['t'])

def close(a,b): return abs(a-b)<=max(1e-6,abs(b)*1e-6)

def verify(row,bars):
    try:
        ref,conf,bear,sweep,bull,touch,reclaim,hold,entry=(i(row[k]) for k in ('ssl_ref_idx','ssl_confirm_idx','bear_fvg_idx','sweep_idx','bull_fvg_idx','touch_idx','reclaim_idx','takeover_idx','eligible_entry_idx'))
    except (KeyError,ValueError): return 'BAD_INDEX'
    if not (3<=ref<len(bars)-3 and conf==ref+3 and entry==hold+1<len(bars)): return 'INDEX_RANGE_OR_CONFIRM'
    if not all(bars[j]['l']>bars[ref]['l'] for j in range(ref-3,ref+4) if j!=ref): return 'SSL_NOT_UNIQUE_3_3_PIVOT'
    if not conf<bear-2<=sweep<bull<touch<reclaim<hold<entry: return 'CHRONOLOGY'
    if not (bear-2<=sweep<=bear+3 and bull<=sweep+5): return 'FROZEN_WINDOW'
    bear_low,bear_high=bars[bear]['h'],bars[bear-2]['l']
    if not bear_high>bear_low*1.0005: return 'BEAR_FVG_GEOMETRY'
    if not (bars[sweep]['l']<bars[ref]['l']*.997 and bars[sweep]['c']>bars[ref]['l']): return 'SSL_SWEEP_GEOMETRY'
    bull_low,bull_high=bars[bull-2]['h'],bars[bull]['l']
    if not bull_high>bull_low*1.0005: return 'BULL_FVG_GEOMETRY'
    bpr_low,bpr_high=max(bear_low,bull_low),min(bear_high,bull_high)
    if not (bpr_high>bpr_low*1.0005 and bars[bull]['c']>bpr_high): return 'BPR_OVERLAP_OR_DISPLACEMENT'
    if not (close(f(row['bpr_low']),bpr_low) and close(f(row['bpr_high']),bpr_high)): return 'BPR_PRICE_MISMATCH'
    first_touch=first_reclaim=first_hold=None
    for j in range(bull+1,min(len(bars),bull+21)):
        b=bars[j]
        if b['c']<min(bpr_low,bars[ref]['l']): return 'INVALIDATED_BEFORE_HOLD'
        if first_touch is None:
            if b['l']<=bpr_high and b['h']>=bpr_low: first_touch=j
            continue
        if first_reclaim is None:
            if j>first_touch and b['c']>bpr_high: first_reclaim=j
            continue
        if j>first_reclaim and b['c']>bpr_high and b['l']>=bpr_low:
            first_hold=j; break
    if (first_touch,first_reclaim,first_hold)!=(touch,reclaim,hold): return 'LIFECYCLE_FIRST_EVENT_MISMATCH'
    dates={'bear_fvg_date':bear,'sweep_date':sweep,'bull_fvg_date':bull,'touch_date':touch,'reclaim_date':reclaim,'takeover_date':hold,'eligible_entry_date':entry}
    if any(day(row.get(k))!=bars[idx]['t'] for k,idx in dates.items()): return 'DATE_INDEX_MISMATCH'
    return 'PASS'

def main():
    OUT.mkdir(parents=True,exist_ok=True); report=json.loads(SRC.read_text())
    with open(report['artifacts']['seeds']) as h:
        reader=csv.DictReader(h); headers=reader.fieldnames or []; rows=list(reader)
    forbidden=[h for h in headers if h!='no_outcome_fields' and any(x in h.lower() for x in FORBIDDEN)]
    cache={}; failures=Counter(); mismatches=[]; passed=[]
    for row in rows:
        sym=row['symbol']
        if sym not in cache: cache[sym]=load(sym)
        reason=verify(row,cache[sym]) if cache[sym] else 'MISSING_KLINE'
        failures[reason]+=1
        if reason=='PASS': passed.append(row)
        elif len(mismatches)<1000: mismatches.append({'symbol':sym,'eligible_entry_date':row.get('eligible_entry_date',''),'reason':reason})
    mismatch_file=OUT/'v448_mismatches.csv'
    with mismatch_file.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=['symbol','eligible_entry_date','reason']); w.writeheader(); w.writerows(mismatches)
    pass_file=OUT/'v448_oracle_passed_seeds.csv'
    with pass_file.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=headers); w.writeheader(); w.writerows(passed)
    result={'version':'V448_SSL_BPR_INDEPENDENT_ORACLE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),
      'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'source_seed_count':len(rows),'oracle_pass_count':len(passed),'failure_counts':dict(failures),
      'forbidden_outcome_headers':forbidden,'duplicate_symbol_entry':len(passed)-len(set((r['symbol'],r['eligible_entry_date']) for r in passed)),
      'mismatch_total':len(rows)-len(passed),'oracle_gate_pass':len(rows)==len(passed) and not forbidden,
      'decision':'INDEPENDENT_SEMANTIC_ORACLE_PASS__FROZEN_REPLAY_ALLOWED' if len(rows)==len(passed) and not forbidden else 'ORACLE_FAIL__NO_REPLAY',
      'artifacts':{'out_dir':str(OUT),'passed_seeds':str(pass_file),'mismatches':str(mismatch_file),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2); (OUT/'v448_report.json').write_text(text); LATEST.write_text(text); print(text)
if __name__=='__main__': main()
