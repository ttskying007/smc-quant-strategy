#!/usr/bin/env python3
"""V478 independent raw-bar oracle for V477 double-SSL absorption seeds.

This implementation reconstructs the complete seed set directly from raw bars;
it does not import V477 and reads no outcomes.
"""
from __future__ import annotations
import csv, json, math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
SRC=AUD/'v477_double_ssl_absorption_latest.json'
OUT=AUD/f"v478_double_ssl_absorption_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST=AUD/'v478_double_ssl_absorption_oracle_latest.json'
FORBIDDEN=('entry_price','exit','pnl','mfe','mae','target','tp','rr','hold_bars','won','outcome')
COMPARE=('ssl_idx','ssl_confirm_idx','first_raid_idx','second_raid_idx','reversal_confirm_idx','eligible_entry_idx','ssl_price','first_raid_low','first_raid_high','second_raid_low','second_raid_high','reversal_trigger','structural_sl_ref')


def f(x):
    try:
        v=float(x); return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError): return 0.0


def ds(x): return ''.join(c for c in str(x or '') if c.isdigit())[:8]


def bars_for(sym):
    try: raw=json.loads((KDIR/f"{sym.replace('.','_')}_daily_750.json").read_text())
    except (OSError,json.JSONDecodeError): return []
    out=[]
    for x in raw:
        d=ds(x.get('t') or x.get('date')); row={k:f(x.get(k)) for k in ('o','h','l','c')}
        if d and all(row.values()): row['t']=d; out.append(row)
    return sorted(out,key=lambda x:x['t'])


def pivots_low(b):
    ans=[]
    for p in range(3,len(b)-3):
        value=b[p]['l']
        if min(b[j]['l'] for j in range(p-3,p+4) if j!=p)>value:
            ans.append((p,p+3,value))
    return ans


def rebuild(sym,b):
    lows=pivots_low(b); found=[]
    for r1 in range(7,len(b)-6):
        swept=[p for p in lows if p[1]<r1 and r1-p[0]<=60 and b[r1]['l']<p[2]*.997 and b[r1]['c']>p[2]]
        if not swept: continue
        ssl=max(swept,key=lambda p:p[0])
        for r2 in range(r1+2,min(len(b)-4,r1+11)):
            between=range(r1+1,r2)
            if any(b[k]['c']>b[r1]['h'] for k in between): break
            if any(b[k]['c']<b[r1]['l'] for k in between): break
            if b[r2]['l']>=ssl[2]*.997 or b[r2]['c']<=ssl[2] or b[r2]['l']<=b[r1]['l']: continue
            trigger=max(b[r1]['h'],b[r2]['h'])
            confirmation=None
            for k in range(r2+1,min(len(b),r2+4)):
                if b[k]['c']>trigger:
                    confirmation=k; break
            if confirmation is None: break
            entry=confirmation+1
            if entry>=len(b): break
            found.append({'symbol':sym,'eligible_entry_date':b[entry]['t'],'ssl_idx':ssl[0],'ssl_confirm_idx':ssl[1],
              'first_raid_idx':r1,'second_raid_idx':r2,'reversal_confirm_idx':confirmation,'eligible_entry_idx':entry,
              'ssl_price':ssl[2],'first_raid_low':b[r1]['l'],'first_raid_high':b[r1]['h'],
              'second_raid_low':b[r2]['l'],'second_raid_high':b[r2]['h'],'reversal_trigger':trigger,
              'structural_sl_ref':min(b[r1]['l'],b[r2]['l'])})
            break
    dedup={}
    for row in found:
        key=(sym,row['eligible_entry_date']); old=dedup.get(key)
        if old is None or row['second_raid_idx']<old['second_raid_idx']: dedup[key]=row
    return dedup


def equal(a,b,key):
    if key.endswith(('_price','_low','_high','_trigger','_ref')):
        return abs(f(a)-f(b))<=max(1e-6,abs(f(b))*1e-6)
    return int(float(a))==int(float(b))


def main():
    report=json.loads(SRC.read_text())
    with open(report['artifacts']['seeds']) as h:
        reader=csv.DictReader(h); headers=reader.fieldnames or []; source=list(reader)
    forbidden=[h for h in headers if h!='no_outcome_fields' and any(x in h.lower() for x in FORBIDDEN)]
    source_map={(r['symbol'],r['eligible_entry_date']):r for r in source}
    by_symbol=defaultdict(list)
    for row in source: by_symbol[row['symbol']].append(row)
    expected={}; missing_bars=[]
    for n,sym in enumerate(sorted(by_symbol),1):
        bars=bars_for(sym)
        if not bars: missing_bars.append(sym); continue
        expected.update(rebuild(sym,bars))
        if n%500==0: print(json.dumps({'symbols':n,'expected':len(expected)}),flush=True)
    mismatches=[]; counts=Counter()
    all_keys=set(source_map)|set(expected)
    for key in sorted(all_keys):
        if key not in source_map:
            counts['ORACLE_EXTRA_MISSING_FROM_V477']+=1; mismatches.append({'symbol':key[0],'eligible_entry_date':key[1],'reason':'ORACLE_EXTRA_MISSING_FROM_V477'}); continue
        if key not in expected:
            counts['V477_EXTRA_NOT_IN_ORACLE']+=1; mismatches.append({'symbol':key[0],'eligible_entry_date':key[1],'reason':'V477_EXTRA_NOT_IN_ORACLE'}); continue
        bad=[field for field in COMPARE if not equal(source_map[key].get(field),expected[key].get(field),field)]
        if bad:
            counts['FIELD_MISMATCH']+=1; mismatches.append({'symbol':key[0],'eligible_entry_date':key[1],'reason':'FIELD_MISMATCH:'+','.join(bad)})
        else: counts['PASS']+=1
    OUT.mkdir(parents=True,exist_ok=True); mismatch_file=OUT/'v478_mismatches.csv'
    with mismatch_file.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=['symbol','eligible_entry_date','reason']); w.writeheader(); w.writerows(mismatches)
    pass_file=OUT/'v478_oracle_passed_seeds.csv'
    with pass_file.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=headers); w.writeheader(); w.writerows(source if not mismatches else [])
    gate=not mismatches and not forbidden and not missing_bars and len(expected)==len(source)
    result={'version':'V478_DOUBLE_SSL_ABSORPTION_INDEPENDENT_ORACLE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),
      'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'source_seed_count':len(source),'independent_expected_count':len(expected),'oracle_pass_count':counts['PASS'],
      'failure_counts':dict(counts),'mismatch_total':len(mismatches),'missing_kline_symbols':missing_bars,
      'forbidden_outcome_headers':forbidden,'oracle_gate_pass':gate,
      'decision':'DOUBLE_SSL_ABSORPTION_ORACLE_PASS__FROZEN_T1_REPLAY_ALLOWED' if gate else 'DOUBLE_SSL_ABSORPTION_ORACLE_FAIL__NO_REPLAY',
      'artifacts':{'out_dir':str(OUT),'passed_seeds':str(pass_file),'mismatches':str(mismatch_file),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2); (OUT/'v478_report.json').write_text(text); LATEST.write_text(text); print(text)

if __name__=='__main__': main()
