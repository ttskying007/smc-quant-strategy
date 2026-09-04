#!/usr/bin/env python3
"""V490 independent raw-bar integrity oracle for V489 seeds."""
from __future__ import annotations
import csv,json,math
from collections import Counter
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes');KDIR=ROOT/'kline_cache';AUD=ROOT/'smc_audit';SRC=AUD/'v489_weekly_bos_demand_transfer_latest.json'
OUT=AUD/f"v490_weekly_bos_demand_transfer_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}";LATEST=AUD/'v490_weekly_bos_demand_transfer_oracle_latest.json'

def num(x):
    try:v=float(x);return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError):return 0.0

def date(x):return ''.join(c for c in str(x or '') if c.isdigit())[:8]

def daily(sym):
    try:raw=json.loads((KDIR/f"{sym.replace('.','_')}_daily_750.json").read_text())
    except (OSError,json.JSONDecodeError):return []
    out=[]
    for b in raw:
        r={k:num(b.get(k)) for k in ('o','h','l','c')};d=date(b.get('t') or b.get('date'))
        if d and min(r.values())>0:r['t']=d;out.append(r)
    return sorted(out,key=lambda x:x['t'])

def weekly(ds):
    groups=[];key=None
    for b in ds:
        d=datetime.strptime(b['t'],'%Y%m%d').date();k=d.isocalendar()[:2]
        if k!=key:groups.append([]);key=k
        groups[-1].append(b)
    return [{'start':g[0]['t'],'end':g[-1]['t'],'o':g[0]['o'],'h':max(x['h'] for x in g),'l':min(x['l'] for x in g),'c':g[-1]['c']} for g in groups[:-1]]

def check(seed,ds,ws):
    try:
        p=int(float(seed['weekly_broken_high_idx']));pc=int(float(seed['weekly_broken_high_confirm_idx']));o=int(float(seed['weekly_ob_idx']));b=int(float(seed['weekly_bos_idx']))
        t=int(float(seed['touch_idx']));r=int(float(seed['reclaim_idx']));h=int(float(seed['hold_idx']));e=int(float(seed['eligible_entry_idx']))
        level=num(seed['weekly_broken_high']);zl=num(seed['zone_low']);zh=num(seed['zone_high'])
        if not (2<=p<len(ws)-2 and pc==p+2 and pc<b and o<b):return 'INDEX_OR_ORDER'
        if not (ws[p]['h']>max(ws[j]['h'] for j in range(p-2,p+3) if j!=p) and abs(ws[p]['h']-level)<=1e-6):return 'WEEKLY_PIVOT'
        if not ws[b]['c']>level*1.003:return 'WEEKLY_BOS'
        expected=next((i for i in range(b-1,max(-1,b-7),-1) if ws[i]['c']<ws[i]['o']),None)
        if expected!=o:return 'OB_ANCHOR'
        if abs(ws[o]['l']-zl)>1e-6 or abs(max(ws[o]['o'],ws[o]['c'])-zh)>1e-6:return 'OB_ZONE'
        if any(ws[j]['l']<=zh for j in range(o+1,b)):return 'PRE_BOS_MITIGATION'
        if not (ws[b]['end']<ds[t]['t']<ds[r]['t']<ds[h]['t']<ds[e]['t'] and e==h+1):return 'DAILY_ORDER'
        if ds[t]['l']>zh or ds[r]['c']<=zh or ds[h]['c']<=zh or ds[h]['l']<zl:return 'DAILY_LIFECYCLE'
        if any(ds[j]['c']<zl for j in range(next(i for i,x in enumerate(ds) if x['t']>ws[b]['end']),h+1)):return 'PRE_HOLD_INVALIDATION'
        return 'PASS'
    except Exception:return 'EXCEPTION'

def main():
    src=json.loads(SRC.read_text())
    if src.get('decision')!='WEEKLY_BOS_DEMAND_SEEDS_READY__INDEPENDENT_ORACLE_NEXT':raise RuntimeError('V489 gate failed')
    with open(src['artifacts']['seeds']) as h:seeds=list(csv.DictReader(h))
    forbidden=[c for c in seeds[0] if c!='no_outcome_fields' and any(x in c.lower() for x in ('pnl','exit','mfe','mae','outcome','entry_price'))] if seeds else []
    cache={};bad=[];counts=Counter()
    for i,s in enumerate(seeds,1):
        sym=s['symbol']
        if sym not in cache:
            bars=daily(sym);cache[sym]=(bars,weekly(bars))
        bars,ws=cache[sym]
        status=check(s,bars,ws);counts[status]+=1
        if status!='PASS':bad.append({'symbol':sym,'eligible_entry_date':s['eligible_entry_date'],'reason':status})
        if i%10000==0:print(json.dumps({'checked':i,'bad':len(bad)}),flush=True)
    OUT.mkdir(parents=True,exist_ok=True);mis=OUT/'v490_mismatches.csv'
    with mis.open('w',newline='') as h:w=csv.DictWriter(h,fieldnames=['symbol','eligible_entry_date','reason']);w.writeheader();w.writerows(bad)
    passed=not forbidden and not bad
    result={'version':'V490_WEEKLY_BOS_DEMAND_TRANSFER_INDEPENDENT_ORACLE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'source_seed_count':len(seeds),'oracle_pass_count':counts['PASS'],'failure_counts':dict(counts),'forbidden_outcome_headers':forbidden,'mismatch_total':len(bad),'oracle_gate_pass':passed,'decision':'WEEKLY_BOS_DEMAND_ORACLE_PASS__FROZEN_T1_REPLAY_ALLOWED' if passed else 'WEEKLY_BOS_DEMAND_ORACLE_FAIL__NO_REPLAY','artifacts':{'out_dir':str(OUT),'passed_seeds':src['artifacts']['seeds'],'mismatches':str(mis),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2);(OUT/'v490_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
