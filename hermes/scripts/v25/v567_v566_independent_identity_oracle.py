#!/usr/bin/env python3
"""V567 independent raw-bar identity oracle for frozen V566 seeds.

Does not import V566. Reads only V566 identities and raw same-source daily/M15 bars.
No trade outcomes, replay outputs, stops, targets, PnL, MFE, or MAE are read.
"""
from __future__ import annotations
import csv, gzip, json, math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; RAW=ROOT/'intraday_cache/raw_multitf_v536/source_raw/sina'; DAILY=RAW/'daily'; M15=RAW/'m15'
V566=AUD/'v566_daily_hl_opening_bsl_acceptance_retest_seed_latest.json'; OUT=AUD/f'v567_v566_independent_identity_oracle_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'; LATEST=AUD/'v567_v566_independent_identity_oracle_latest.json'; YEARS={'2025','2026'}

def val(x:Any)->float|None:
    try:
        y=float(x); return y if math.isfinite(y) and y>0 else None
    except (TypeError,ValueError): return None

def raw(path:Path)->list[dict[str,Any]]:
    try:
        with gzip.open(path,'rt',encoding='utf-8') as h: x=json.load(h)
        return x if isinstance(x,list) else []
    except (OSError,ValueError): return []

def dload(sym:str)->list[tuple[str,float,float,float,float]]:
    out=[]
    for x in raw(DAILY/f'{sym.replace(".","_")}_daily.json.gz'):
        d=str(x.get('d') or x.get('t') or '')[:8]; z=[val(x.get(k)) for k in ('o','h','l','c')]
        if len(d)==8 and all(q is not None for q in z): out.append((d,z[0],z[1],z[2],z[3]))
    return sorted(out)

def iload(sym:str)->dict[str,list[tuple[str,float,float,float,float]]]:
    out=defaultdict(list)
    for x in raw(M15/f'{sym.replace(".","_")}_m15.json.gz'):
        t=str(x.get('t') or ''); z=[val(x.get(k)) for k in ('o','h','l','c')]
        if len(t)==14 and all(q is not None for q in z): out[t[:8]].append((t,z[0],z[1],z[2],z[3]))
    for x in out.values(): x.sort()
    return out

def parent_dates(ds:list[tuple[str,float,float,float,float]])->set[str]:
    piv=[]
    for i in range(3,len(ds)-3):
        low=ds[i][3]
        if low<min(x[3] for x in ds[i-3:i]) and low<=min(x[3] for x in ds[i+1:i+4]): piv.append((i,i+3,low))
    good=set()
    for i in range(1,len(ds)):
        known=[x for x in piv if x[1]<i]
        if len(known)>=2 and known[-1][2]>known[-2][2] and ds[i-1][4]>known[-1][2]: good.add(ds[i][0])
    return good

def m15_signal(b:list[tuple[str,float,float,float,float]])->bool:
    if len(b)!=16:return False
    bsl=max(x[2] for x in b[:4])
    accepted=[]
    for i in range(4,13):
        if b[i][4]>bsl*1.001: accepted.append(i)
    for i in accepted:
        for j in range(i+1,15):
            if b[j][3]<=bsl*1.001 and b[j][4]>bsl and b[j+1][4]>bsl:return True
    return False

def main()->None:
    OUT.mkdir(parents=True,exist_ok=False); source=json.loads(V566.read_text()); seed=Path(source['artifacts']['seeds'])
    with seed.open(newline='',encoding='utf-8') as h: expected={(r['symbol'],r['signal_date'],r['eligible_entry_date']) for r in csv.DictReader(h)}
    symbols=sorted({x[0] for x in expected}); actual=set(); malformed=0
    for n,sym in enumerate(symbols,1):
        ds=dload(sym); sessions=iload(sym)
        if len(ds)<30: malformed+=1; continue
        parent=parent_dates(ds); nxt={a[0]:b[0] for a,b in zip(ds,ds[1:])}
        for day in parent:
            if day[:4] in YEARS and m15_signal(sessions.get(day,[])) and nxt.get(day): actual.add((sym,day,nxt[day]))
        if n%1000==0:print(json.dumps({'symbols':n,'oracle_identities':len(actual)}),flush=True)
    missing=expected-actual; extra=actual-expected
    inv={'source_isolated_sina_only':True,'outcome_files_not_read':True,'expected_nonempty':bool(expected),'identity_match':not missing and not extra,'all_oracle_execution_t1':all(e>d for _,d,e in actual),'all_oracle_dates_in_scope':all(d[:4] in YEARS for _,d,_ in actual)}
    rep={'version':'V567_V566_INDEPENDENT_IDENTITY_ORACLE_NO_OUTCOME','generated_at':datetime.now().isoformat(timespec='seconds'),'research_only':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'oracle_contract':'Independent raw daily 3L/3R protected-HL parent; raw M15 first-four-bar BSL acceptance, later retest/close-above, then one hold; next daily session eligibility. Identity=symbol,signal_date,eligible_entry_date.','forbidden_inputs':'No V566 code import and no outcomes/replay/trade file reads.','expected_identities':len(expected),'oracle_identities':len(actual),'missing_count':len(missing),'extra_count':len(extra),'malformed_symbols':malformed,'missing_sample':[list(x) for x in sorted(missing)[:20]],'extra_sample':[list(x) for x in sorted(extra)[:20]],'invariants':inv,'decision':'V567_IDENTITY_PASS__ONE_FROZEN_STRICT_T1_REPLAY_AUTHORIZED' if all(inv.values()) else 'V567_IDENTITY_MISMATCH__STOP_V566_NO_REPLAY','artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'source_seed':str(seed)}}
    text=json.dumps(rep,ensure_ascii=False,indent=2); (OUT/'v567_report.json').write_text(text); LATEST.write_text(text); print(text)
if __name__=='__main__':main()
