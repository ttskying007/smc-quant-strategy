#!/usr/bin/env python3
"""V508 independent raw-bar semantic oracle for V507 weekly IFVG seeds."""
from __future__ import annotations
import csv,json,math
from collections import Counter
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes');KDIR=ROOT/'kline_cache';AUD=ROOT/'smc_audit';SRC=AUD/'v507_weekly_ifvg_support_transfer_latest.json'
OUT=AUD/f"v508_weekly_ifvg_support_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}";LATEST=AUD/'v508_weekly_ifvg_support_oracle_latest.json'

def f(x):
    try:v=float(x);return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError):return 0.0

def ds(x):return ''.join(c for c in str(x or '') if c.isdigit())[:8]

def daily(sym):
    try:raw=json.loads((KDIR/f"{sym.replace('.','_')}_daily_750.json").read_text())
    except (OSError,json.JSONDecodeError):return []
    out=[]
    for b in raw:
        r={k:f(b.get(k)) for k in ('o','h','l','c')};d=ds(b.get('t') or b.get('date'))
        if d and min(r.values())>0:r['t']=d;out.append(r)
    return sorted(out,key=lambda x:x['t'])

def weekly(rows):
    groups=[];key=None
    for b in rows:
        k=datetime.strptime(b['t'],'%Y%m%d').date().isocalendar()[:2]
        if k!=key:groups.append([]);key=k
        groups[-1].append(b)
    return [{'end':g[-1]['t'],'h':max(x['h'] for x in g),'l':min(x['l'] for x in g),'c':g[-1]['c']} for g in groups[:-1] if g]

def check(seed,ds_,ws):
    try:
        left=int(float(seed['weekly_fvg_left_idx']));create=int(float(seed['weekly_fvg_create_idx']));inv=int(float(seed['weekly_inversion_idx']))
        touch=int(float(seed['touch_idx']));reclaim=int(float(seed['reclaim_idx']));hold=int(float(seed['hold_idx']));eligible=int(float(seed['eligible_entry_idx']))
        zl=f(seed['zone_low']);zh=f(seed['zone_high'])
        if create!=left+2 or not (2<=create<inv<len(ws)):return 'WEEKLY_INDEX'
        if not (ws[create]['h']<ws[left]['l']*.9995):return 'BEAR_FVG_GEOMETRY'
        if abs(ws[create]['h']-zl)>1e-6 or abs(ws[left]['l']-zh)>1e-6:return 'ZONE_MISMATCH'
        first_inv=next((j for j in range(create+1,len(ws)) if ws[j]['c']>zh*1.003),None)
        if first_inv!=inv:return 'NOT_FIRST_INVERSION'
        start=next(i for i,b in enumerate(ds_) if b['t']>ws[inv]['end'])
        if not (ws[create]['end']<ws[inv]['end']<ds_[touch]['t']<ds_[reclaim]['t']<ds_[hold]['t']<ds_[eligible]['t'] and eligible==hold+1):return 'DAILY_ORDER'
        first_touch=next((i for i in range(start,hold+1) if ds_[i]['l']<=zh and ds_[i]['h']>=zl),None)
        if first_touch!=touch:return 'NOT_FIRST_TOUCH'
        if any(ds_[i]['c']<zl for i in range(start,hold+1)):return 'PRE_HOLD_INVALIDATION'
        if ds_[reclaim]['c']<=zh or ds_[hold]['c']<=zh or ds_[hold]['l']<zl:return 'RECLAIM_HOLD'
        return 'PASS'
    except Exception:return 'EXCEPTION'

def main():
    src=json.loads(SRC.read_text())
    if src.get('decision')!='WEEKLY_IFVG_SUPPORT_SEEDS_READY__INDEPENDENT_ORACLE_NEXT':raise RuntimeError('V507 gate failed')
    with open(src['artifacts']['seeds']) as h:seeds=list(csv.DictReader(h))
    forbidden=[c for c in seeds[0] if c!='no_outcome_fields' and any(x in c.lower() for x in ('pnl','exit','mfe','mae','outcome','entry_price'))] if seeds else []
    cache={};bad=[];counts=Counter()
    for i,s in enumerate(seeds,1):
        sym=s['symbol']
        if sym not in cache:
            bars=daily(sym);cache[sym]=(bars,weekly(bars))
        bars,ws=cache[sym];status=check(s,bars,ws);counts[status]+=1
        if status!='PASS':bad.append({'symbol':sym,'eligible_entry_date':s['eligible_entry_date'],'reason':status})
        if i%10000==0:print(json.dumps({'checked':i,'bad':len(bad)}),flush=True)
    OUT.mkdir(parents=True,exist_ok=True);mis=OUT/'v508_mismatches.csv'
    with mis.open('w',newline='') as h:w=csv.DictWriter(h,fieldnames=['symbol','eligible_entry_date','reason']);w.writeheader();w.writerows(bad)
    passed=not forbidden and not bad
    result={'version':'V508_WEEKLY_IFVG_SUPPORT_INDEPENDENT_ORACLE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source_seed_count':len(seeds),'oracle_pass_count':counts['PASS'],'failure_counts':dict(counts),'forbidden_outcome_headers':forbidden,'mismatch_total':len(bad),'oracle_gate_pass':passed,'decision':'WEEKLY_IFVG_SUPPORT_ORACLE_PASS__FROZEN_T1_REPLAY_ALLOWED' if passed else 'WEEKLY_IFVG_SUPPORT_ORACLE_FAIL__NO_REPLAY','artifacts':{'out_dir':str(OUT),'passed_seeds':src['artifacts']['seeds'],'mismatches':str(mis),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2);(OUT/'v508_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
