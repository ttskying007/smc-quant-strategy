#!/usr/bin/env python3
"""V486 independent raw-bar differential oracle for V485."""
from __future__ import annotations
import csv, json, math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
SRC=AUD/'v485_bsl_acceptance_retest_latest.json'
OUT=AUD/f"v486_bsl_acceptance_retest_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST=AUD/'v486_bsl_acceptance_retest_oracle_latest.json'


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


def pivot_highs(bars):
    out=[]
    for i in range(3,len(bars)-3):
        adjacent=[bars[j]['h'] for j in range(i-3,i+4) if j!=i]
        if bars[i]['h']>max(adjacent): out.append((i,i+3,bars[i]['h']))
    return out


def derive(sym,bars):
    piv=pivot_highs(bars); found=[]
    for a in range(7,len(bars)-6):
        visible=[p for p in piv if p[1]<a and a-p[0]<=60]
        broken=[p for p in visible if bars[a]['c']>p[2]*1.003]
        if not broken: continue
        level=max(broken,key=lambda p:p[0])
        higher=sorted((p for p in visible if p[2]>level[2]*1.003),key=lambda p:p[2])
        if not higher: continue
        target=higher[0]
        if bars[a]['c']>=target[2]: continue
        retest=None
        for i in range(a+2,min(len(bars)-4,a+11)):
            if bars[i]['c']<level[2]: break
            if bars[i]['l']<=level[2]*1.003 and bars[i]['c']>level[2]: retest=i; break
        if retest is None: continue
        confirm=None
        for i in range(retest+1,min(len(bars),retest+4)):
            if bars[i]['c']>bars[retest]['h']: confirm=i; break
        if confirm is None or confirm+1>=len(bars): continue
        entry=confirm+1
        found.append({'symbol':sym,'eligible_entry_date':bars[entry]['t'],'broken_bsl_idx':level[0],
          'target_bsl_idx':target[0],'accept_idx':a,'retest_idx':retest,'reexpand_idx':confirm,
          'eligible_entry_idx':entry,'broken_bsl':level[2],'target_bsl':target[2],
          'retest_low':bars[retest]['l'],'retest_high':bars[retest]['h']})
    unique={}
    for row in found:
        key=(row['symbol'],row['eligible_entry_date']); old=unique.get(key)
        if old is None or row['retest_idx']<old['retest_idx']: unique[key]=row
    return unique


def main():
    source=json.loads(SRC.read_text())
    if source.get('decision')!='BSL_ACCEPTANCE_SEEDS_READY__INDEPENDENT_ORACLE_NEXT': raise RuntimeError('V485 gate not passed')
    with open(source['artifacts']['seeds']) as h: expected=list(csv.DictReader(h))
    symbols=sorted({r['symbol'] for r in expected}); observed={}
    for n,sym in enumerate(symbols,1):
        observed.update(derive(sym,read_bars(sym)))
        if n%500==0: print(json.dumps({'symbols':n,'observed':len(observed)}),flush=True)
    exp={(r['symbol'],r['eligible_entry_date']):r for r in expected}; mismatches=[]
    fields=('broken_bsl_idx','target_bsl_idx','accept_idx','retest_idx','reexpand_idx','eligible_entry_idx','broken_bsl','target_bsl','retest_low','retest_high')
    for key in sorted(set(exp)|set(observed)):
        if key not in exp: mismatches.append({'key':'|'.join(key),'reason':'ORACLE_EXTRA'}); continue
        if key not in observed: mismatches.append({'key':'|'.join(key),'reason':'ORACLE_MISSING'}); continue
        for field in fields:
            a=exp[key].get(field); b=observed[key].get(field)
            equal=(int(float(a))==int(b)) if field.endswith('idx') else abs(float(a)-float(b))<=1e-6
            if not equal: mismatches.append({'key':'|'.join(key),'reason':field,'expected':a,'observed':b})
    OUT.mkdir(parents=True,exist_ok=True); mismatch_file=OUT/'v486_mismatches.csv'
    with mismatch_file.open('w',newline='') as h:
        out_fields=sorted({k for r in mismatches for k in r}) or ['key','reason']; w=csv.DictWriter(h,fieldnames=out_fields); w.writeheader(); w.writerows(mismatches)
    passed=len(mismatches)==0 and len(observed)==len(expected)
    result={'version':'V486_BSL_ACCEPTANCE_RETEST_INDEPENDENT_ORACLE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),
      'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'expected_seed_count':len(expected),'observed_seed_count':len(observed),'mismatch_total':len(mismatches),
      'mismatch_reasons':dict(Counter(r['reason'] for r in mismatches)),
      'invariants':{'oracle_implementation_independent':True,'no_outcome_fields_read':True,'seed_set_equal':set(exp)==set(observed)},
      'oracle_gate_pass':passed,'decision':'BSL_ACCEPTANCE_ORACLE_PASS__FROZEN_T1_REPLAY_ALLOWED' if passed else 'BSL_ACCEPTANCE_ORACLE_FAIL__NO_REPLAY',
      'artifacts':{'out_dir':str(OUT),'passed_seeds':source['artifacts']['seeds'],'mismatches':str(mismatch_file),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2); (OUT/'v486_report.json').write_text(text); LATEST.write_text(text); print(text)

if __name__=='__main__': main()
