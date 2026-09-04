#!/usr/bin/env python3
"""V482 independent raw-bar differential oracle for V481."""
from __future__ import annotations
import csv, json, math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
SRC=AUD/'v481_two_sided_liquidity_purge_latest.json'
OUT=AUD/f"v482_two_sided_liquidity_purge_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST=AUD/'v482_two_sided_liquidity_purge_oracle_latest.json'


def num(x):
    try:
        v=float(x); return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError): return 0.0


def date(x): return ''.join(ch for ch in str(x or '') if ch.isdigit())[:8]


def read_bars(sym):
    try: data=json.loads((KDIR/f"{sym.replace('.','_')}_daily_750.json").read_text())
    except (OSError,json.JSONDecodeError): return []
    out=[]
    for raw in data:
        d=date(raw.get('t') or raw.get('date')); row={k:num(raw.get(k)) for k in ('o','h','l','c')}
        if d and min(row.values())>0: row['t']=d; out.append(row)
    return sorted(out,key=lambda x:x['t'])


def independent_pivots(bars,is_high):
    field='h' if is_high else 'l'; out=[]
    for idx in range(3,len(bars)-3):
        center=bars[idx][field]; neighbours=[bars[j][field] for j in range(idx-3,idx+4) if j!=idx]
        if (center>max(neighbours) if is_high else center<min(neighbours)):
            out.append((idx,idx+3,center))
    return out


def derive(sym,bars):
    ph=independent_pivots(bars,True); pl=independent_pivots(bars,False); found=[]
    for raid1 in range(7,len(bars)-6):
        visible_h=[p for p in ph if p[1]<raid1 and raid1-p[0]<=60 and bars[raid1]['h']>p[2]*1.003 and bars[raid1]['c']<p[2]]
        if not visible_h: continue
        h=max(visible_h,key=lambda p:p[0])
        visible_l=[p for p in pl if p[1]<raid1 and raid1-p[0]<=60 and p[2]<h[2]]
        if not visible_l: continue
        l=max(visible_l,key=lambda p:p[0])
        for raid2 in range(raid1+2,min(len(bars)-4,raid1+11)):
            if max((bars[j]['c'] for j in range(raid1+1,raid2)),default=-1)>bars[raid1]['h']: break
            if min((bars[j]['c'] for j in range(raid1+1,raid2)),default=10**99)<l[2]: break
            if bars[raid2]['l']>=l[2]*.997 or bars[raid2]['c']<=l[2]: continue
            confirm=None
            for idx in range(raid2+1,min(len(bars),raid2+4)):
                if bars[idx]['c']>bars[raid2]['h']: confirm=idx; break
            if confirm is None: break
            entry=confirm+1
            if entry<len(bars):
                found.append({'symbol':sym,'eligible_entry_date':bars[entry]['t'],'range_high_idx':h[0],
                  'range_low_idx':l[0],'bsl_raid_idx':raid1,'ssl_raid_idx':raid2,
                  'reversal_confirm_idx':confirm,'eligible_entry_idx':entry,
                  'range_high':h[2],'range_low':l[2],'bsl_raid_high':bars[raid1]['h'],
                  'ssl_raid_low':bars[raid2]['l'],'ssl_raid_high':bars[raid2]['h']})
            break
    unique={}
    for row in found:
        key=(row['symbol'],row['eligible_entry_date']); old=unique.get(key)
        if old is None or row['ssl_raid_idx']<old['ssl_raid_idx']: unique[key]=row
    return unique


def main():
    source=json.loads(SRC.read_text())
    if source.get('decision')!='TWO_SIDED_PURGE_SEEDS_READY__INDEPENDENT_ORACLE_NEXT': raise RuntimeError('V481 gate not passed')
    with open(source['artifacts']['seeds']) as h: expected=list(csv.DictReader(h))
    by_symbol={}
    for row in expected: by_symbol.setdefault(row['symbol'],[]).append(row)
    observed={}
    for n,sym in enumerate(sorted(by_symbol),1):
        observed.update(derive(sym,read_bars(sym)))
        if n%500==0: print(json.dumps({'symbols':n,'observed':len(observed)}),flush=True)
    exp={(r['symbol'],r['eligible_entry_date']):r for r in expected}; mismatches=[]
    fields=('range_high_idx','range_low_idx','bsl_raid_idx','ssl_raid_idx','reversal_confirm_idx','eligible_entry_idx','range_high','range_low','bsl_raid_high','ssl_raid_low','ssl_raid_high')
    for key in sorted(set(exp)|set(observed)):
        if key not in exp: mismatches.append({'key':'|'.join(key),'reason':'ORACLE_EXTRA'}); continue
        if key not in observed: mismatches.append({'key':'|'.join(key),'reason':'ORACLE_MISSING'}); continue
        for field in fields:
            a=exp[key].get(field); b=observed[key].get(field)
            equal=(int(float(a))==int(b)) if field.endswith('idx') else abs(float(a)-float(b))<=1e-6
            if not equal: mismatches.append({'key':'|'.join(key),'reason':field,'expected':a,'observed':b})
    OUT.mkdir(parents=True,exist_ok=True); mismatch_file=OUT/'v482_mismatches.csv'
    with mismatch_file.open('w',newline='') as h:
        fields_out=sorted({k for r in mismatches for k in r}) or ['key','reason']; w=csv.DictWriter(h,fieldnames=fields_out); w.writeheader(); w.writerows(mismatches)
    passed=len(mismatches)==0 and len(observed)==len(expected)
    result={'version':'V482_TWO_SIDED_LIQUIDITY_PURGE_INDEPENDENT_ORACLE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),
      'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'expected_seed_count':len(expected),'observed_seed_count':len(observed),'mismatch_total':len(mismatches),
      'mismatch_reasons':dict(Counter(r['reason'] for r in mismatches)),
      'invariants':{'oracle_implementation_independent':True,'no_outcome_fields_read':True,'seed_set_equal':set(exp)==set(observed)},
      'oracle_gate_pass':passed,'decision':'TWO_SIDED_PURGE_ORACLE_PASS__FROZEN_T1_REPLAY_ALLOWED' if passed else 'TWO_SIDED_PURGE_ORACLE_FAIL__NO_REPLAY',
      'artifacts':{'out_dir':str(OUT),'passed_seeds':source['artifacts']['seeds'],'mismatches':str(mismatch_file),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2); (OUT/'v482_report.json').write_text(text); LATEST.write_text(text); print(text)

if __name__=='__main__': main()
