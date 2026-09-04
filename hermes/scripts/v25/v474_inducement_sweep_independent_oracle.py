#!/usr/bin/env python3
"""V474 independent raw-bar oracle for V473; outcome fields are forbidden."""
from __future__ import annotations
import csv,json,math
from collections import Counter
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
SRC=AUD/'v473_inducement_sweep_continuation_latest.json'
OUT=AUD/f"v474_inducement_sweep_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST=AUD/'v474_inducement_sweep_oracle_latest.json'
FORBIDDEN=('entry_price','exit','pnl','mfe','mae','target','tp','rr','hold_bars','won','outcome')
def f(x):
    try:
        v=float(x); return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError): return 0.0
def ii(x): return int(float(x))
def ds(x): return ''.join(c for c in str(x or '') if c.isdigit())[:8]
def load(sym):
    try: raw=json.loads((KDIR/f"{sym.replace('.','_')}_daily_750.json").read_text())
    except (OSError,json.JSONDecodeError): return []
    rows=[]
    for b in raw:
        r={k:f(b.get(k)) for k in ('o','h','l','c')}; d=ds(b.get('t') or b.get('date'))
        if d and all(r.values()): r['t']=d; rows.append(r)
    return sorted(rows,key=lambda x:x['t'])
def pivot(bars,idx,key):
    return 3<=idx<len(bars)-3 and all((bars[idx][key]<bars[j][key] if key=='l' else bars[idx][key]>bars[j][key]) for j in range(idx-3,idx+4) if j!=idx)
def close(a,b): return abs(a-b)<=max(1e-6,abs(b)*1e-6)
def eligible_contexts(bars,raid):
    lows=[p for p in range(3,len(bars)-3) if pivot(bars,p,'l')]
    highs=[p for p in range(3,len(bars)-3) if pivot(bars,p,'h')]
    out=[]
    for internal in lows:
        if internal+3>=raid or raid-internal>60: continue
        old=[p for p in lows if p<internal and bars[p]['l']<bars[internal]['l']]
        if not old: continue
        external=max(old)
        hs=[p for p in highs if external+3<p<internal and p+3<internal]
        if not hs: continue
        high=max(hs)
        bos=next((j for j in range(high+4,internal) if bars[j]['c']>bars[high]['h']),None)
        if bos is None: continue
        if any(bars[j]['l']<=bars[external]['l'] for j in range(bos+1,internal+4)): continue
        if bars[raid]['l']<bars[internal]['l']*.997 and bars[raid]['c']>bars[internal]['l'] and bars[raid]['l']>bars[external]['l']:
            out.append((internal,external,high,bos))
    return out
def verify(r,bars):
    try: ext,extc,hi,hic,bos,internal,intc,raid,confirm,entry=(ii(r[k]) for k in ('external_low_idx','external_low_confirm_idx','structure_high_idx','structure_high_confirm_idx','bos_idx','internal_low_idx','internal_low_confirm_idx','raid_idx','reversal_confirm_idx','eligible_entry_idx'))
    except (KeyError,ValueError): return 'BAD_INDEX'
    if not (extc==ext+3<hi<hic==hi+3<bos<internal<intc==internal+3<raid<confirm<entry==confirm+1<len(bars)): return 'INDEX_OR_CHRONOLOGY'
    if not pivot(bars,ext,'l') or not pivot(bars,hi,'h') or not pivot(bars,internal,'l'): return 'PIVOT_FAILURE'
    if not bars[internal]['l']>bars[ext]['l'] or not bars[bos]['c']>bars[hi]['h']: return 'BULL_STRUCTURE_FAILURE'
    if any(bars[j]['l']<=bars[ext]['l'] for j in range(bos+1,intc+1)): return 'EXTERNAL_LOW_NOT_PROTECTED'
    contexts=eligible_contexts(bars,raid)
    if not contexts or max(x[0] for x in contexts)!=internal: return 'NOT_LATEST_ELIGIBLE_INTERNAL_LOW'
    first=next((j for j in range(raid+1,min(len(bars),raid+4)) if bars[j]['c']>bars[raid]['h']),None)
    if first!=confirm: return 'REVERSAL_CONFIRM_FAILURE'
    if not (close(f(r['external_low_price']),bars[ext]['l']) and close(f(r['structure_high_price']),bars[hi]['h']) and close(f(r['internal_low_price']),bars[internal]['l']) and close(f(r['raid_low']),bars[raid]['l']) and close(f(r['raid_high']),bars[raid]['h'])): return 'PRICE_MISMATCH'
    for name,idx in {'bos_date':bos,'raid_date':raid,'reversal_confirm_date':confirm,'eligible_entry_date':entry}.items():
        if ds(r.get(name))!=bars[idx]['t']: return 'DATE_MISMATCH'
    return 'PASS'
def main():
    OUT.mkdir(parents=True,exist_ok=True); report=json.loads(SRC.read_text())
    if report.get('decision')!='INDUCEMENT_SWEEP_SEEDS_READY__INDEPENDENT_ORACLE_NEXT': raise RuntimeError('V473 support gate failed')
    with open(report['artifacts']['seeds']) as h: reader=csv.DictReader(h); headers=reader.fieldnames or []; rows=list(reader)
    forbidden=[h for h in headers if h!='no_outcome_fields' and any(x in h.lower() for x in FORBIDDEN)]
    cache={}; counts=Counter(); passed=[]; bad=[]
    for n,r in enumerate(rows,1):
        if r['symbol'] not in cache: cache[r['symbol']]=load(r['symbol'])
        reason=verify(r,cache[r['symbol']]) if cache[r['symbol']] else 'MISSING_KLINE'; counts[reason]+=1
        if reason=='PASS': passed.append(r)
        elif len(bad)<1000: bad.append({'symbol':r['symbol'],'eligible_entry_date':r.get('eligible_entry_date',''),'reason':reason})
        if n%50000==0: print(json.dumps({'progress':n,'passed':len(passed)}),flush=True)
    pass_file=OUT/'v474_oracle_passed_seeds.csv'; mismatch_file=OUT/'v474_mismatches.csv'
    with pass_file.open('w',newline='') as h: w=csv.DictWriter(h,fieldnames=headers); w.writeheader(); w.writerows(passed)
    with mismatch_file.open('w',newline='') as h: w=csv.DictWriter(h,fieldnames=['symbol','eligible_entry_date','reason']); w.writeheader(); w.writerows(bad)
    mismatch=len(rows)-len(passed); gate=mismatch==0 and not forbidden
    result={'version':'V474_INDUCEMENT_SWEEP_INDEPENDENT_ORACLE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source_seed_count':len(rows),'oracle_pass_count':len(passed),'failure_counts':dict(counts),'mismatch_total':mismatch,'forbidden_outcome_headers':forbidden,'oracle_gate_pass':gate,'decision':'INDEPENDENT_ORACLE_PASS__FROZEN_T1_REPLAY_ALLOWED' if gate else 'ORACLE_FAIL__NO_REPLAY','artifacts':{'out_dir':str(OUT),'passed_seeds':str(pass_file),'mismatches':str(mismatch_file),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2); (OUT/'v474_report.json').write_text(text); LATEST.write_text(text); print(text)
if __name__=='__main__': main()
