#!/usr/bin/env python3
"""V499 independent raw-bar semantic oracle for V498 weekly-breaker transfer."""
from __future__ import annotations
import csv,json,math
from collections import Counter
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes');KDIR=ROOT/'kline_cache';AUD=ROOT/'smc_audit';SRC=AUD/'v498_weekly_breaker_daily_transfer_latest.json'
OUT=AUD/f"v499_weekly_breaker_daily_transfer_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}";LATEST=AUD/'v499_weekly_breaker_daily_transfer_oracle_latest.json'


def num(x):
    try:v=float(x);return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError):return 0.0

def date(x):return ''.join(c for c in str(x or '') if c.isdigit())[:8]

def bars(sym):
    try:raw=json.loads((KDIR/f"{sym.replace('.','_')}_daily_750.json").read_text())
    except (OSError,json.JSONDecodeError):return []
    out=[]
    for b in raw:
        q={k:num(b.get(k)) for k in ('o','h','l','c')};d=date(b.get('t') or b.get('date'))
        if d and min(q.values())>0:q['t']=d;out.append(q)
    return sorted(out,key=lambda x:x['t'])

def aggregate(ds):
    buckets=[];last=None
    for b in ds:
        d=datetime.strptime(b['t'],'%Y%m%d').date();key=(d.isocalendar().year,d.isocalendar().week)
        if key!=last:buckets.append([]);last=key
        buckets[-1].append(b)
    return [{'end':g[-1]['t'],'o':g[0]['o'],'h':max(x['h'] for x in g),'l':min(x['l'] for x in g),'c':g[-1]['c']} for g in buckets[:-1] if g]

def check(s,ds,ws):
    try:
        p=int(float(s['weekly_swing_low_idx']));cf=int(float(s['weekly_swing_confirm_idx']));ev=int(float(s['weekly_bear_bos_idx']));ob=int(float(s['weekly_bearish_ob_idx']));act=int(float(s['weekly_breaker_activation_idx']))
        touch=int(float(s['touch_idx']));rec=int(float(s['reclaim_idx']));hold=int(float(s['hold_idx']));entry=int(float(s['eligible_entry_idx']))
        zl=num(s['zone_low']);zh=num(s['zone_high'])
        if not (2<=p<len(ws)-2 and cf==p+2 and cf<=ev and ob<ev<act):return 'WEEKLY_ORDER'
        if not (ws[p]['l']<min(ws[j]['l'] for j in range(p-2,p+3) if j!=p)):return 'SWING_LOW'
        if ws[ev]['c']>=ws[p]['l']*.997:return 'BEAR_BOS'
        visible=[(i,i+2,ws[i]['l']) for i in range(2,len(ws)-2) if i+2<=ev and i<ev and ws[i]['l']<min(ws[j]['l'] for j in range(i-2,i+3) if j!=i) and ws[ev]['c']<ws[i]['l']*.997]
        if not visible or max(visible,key=lambda x:x[0])[0]!=p:return 'NOT_LATEST_BROKEN_SWING'
        nearest=next((j for j in range(ev-1,max(-1,ev-7),-1) if ws[j]['c']>ws[j]['o']),None)
        if nearest!=ob:return 'NOT_NEAREST_BULLISH_OB'
        if abs(min(ws[ob]['o'],ws[ob]['c'])-zl)>1e-6 or abs(ws[ob]['h']-zh)>1e-6:return 'ZONE_MISMATCH'
        first_activation=next((j for j in range(ev+1,min(len(ws),ev+21)) if ws[j]['c']>zh),None)
        if first_activation!=act:return 'NOT_FIRST_ACTIVATION'
        start=next(i for i,b in enumerate(ds) if b['t']>ws[act]['end'])
        if not (ws[act]['end']<ds[touch]['t']<ds[rec]['t']<ds[hold]['t']<ds[entry]['t'] and entry==hold+1):return 'DAILY_ORDER'
        first_touch=next((i for i in range(start,hold+1) if ds[i]['l']<=zh and ds[i]['h']>=zl),None)
        if first_touch!=touch:return 'NOT_FIRST_TOUCH'
        if any(ds[i]['c']<zl for i in range(start,hold+1)):return 'PRE_HOLD_INVALIDATION'
        if ds[rec]['c']<=zh or ds[hold]['c']<=zh or ds[hold]['l']<zl:return 'RECLAIM_HOLD'
        return 'PASS'
    except Exception:return 'EXCEPTION'

def main():
    src=json.loads(SRC.read_text())
    if src.get('decision')!='WEEKLY_BREAKER_TRANSFER_SEEDS_READY__INDEPENDENT_ORACLE_NEXT':raise RuntimeError('V498 gate failed')
    with open(src['artifacts']['seeds']) as h:seeds=list(csv.DictReader(h))
    forbidden=[c for c in seeds[0] if c!='no_outcome_fields' and any(x in c.lower() for x in ('pnl','exit','mfe','mae','outcome','entry_price'))] if seeds else []
    cache={};counts=Counter();bad=[]
    for i,s in enumerate(seeds,1):
        sym=s['symbol']
        if sym not in cache:
            ds=bars(sym);cache[sym]=(ds,aggregate(ds))
        ds,ws=cache[sym];status=check(s,ds,ws);counts[status]+=1
        if status!='PASS':bad.append({'symbol':sym,'eligible_entry_date':s['eligible_entry_date'],'reason':status})
        if i%10000==0:print(json.dumps({'checked':i,'bad':len(bad)}),flush=True)
    OUT.mkdir(parents=True,exist_ok=True);mis=OUT/'v499_mismatches.csv'
    with mis.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=['symbol','eligible_entry_date','reason']);w.writeheader();w.writerows(bad)
    passed=not forbidden and not bad
    result={'version':'V499_WEEKLY_BREAKER_DAILY_TRANSFER_INDEPENDENT_ORACLE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'source_seed_count':len(seeds),'oracle_pass_count':counts['PASS'],'failure_counts':dict(counts),'forbidden_outcome_headers':forbidden,'mismatch_total':len(bad),'oracle_gate_pass':passed,'decision':'WEEKLY_BREAKER_TRANSFER_ORACLE_PASS__FROZEN_T1_REPLAY_ALLOWED' if passed else 'WEEKLY_BREAKER_TRANSFER_ORACLE_FAIL__NO_REPLAY','artifacts':{'out_dir':str(OUT),'passed_seeds':src['artifacts']['seeds'],'mismatches':str(mis),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2);(OUT/'v499_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
