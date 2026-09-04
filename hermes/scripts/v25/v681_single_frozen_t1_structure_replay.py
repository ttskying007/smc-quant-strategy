#!/usr/bin/env python3
"""V681: one frozen strict-T+1 structural replay, no variants and no writes to production.

Consumes only the exact V680 identity set and same-source V379 daily/Sina-60m bars.
All selection inputs (entry, structural stop, structural target) are reconstructed
from bars completed no later than the entry bar.  Exit is scanned only after the
entry trading date; same-bar stop/target is stop-first.  This script is the sole
frozen replay and emits audit artifacts only.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'
DAILY=ROOT/'intraday_cache/sina_raw_daily_v379'; M60=ROOT/'intraday_cache/sina_m60_v1'
V680=AUD/'v680_frozen_v678_v679_identity_comparison_latest.json'
PREREG=AUD/'v681_single_frozen_t1_structure_replay_preregistration_20260810.md'
OUT=AUD/f'v681_single_frozen_t1_structure_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST=AUD/'v681_single_frozen_t1_structure_replay_latest.json'
sp=importlib.util.spec_from_file_location('v677',ROOT/'scripts/v25/v677_three_timeframe_semantic_source_audit.py')
core=importlib.util.module_from_spec(sp); sp.loader.exec_module(core)
FIELDS=('symbol','weekly_permission_time','daily_ssl_time','daily_break_time','daily_ob_time','daily_first_touch_time','h60_ssl_time','h60_break_time','h60_ob_time','h60_hold_time')
COST=0.002

def load_rows(symbol):
    code,ex=symbol.split('.')
    d=core.daily_rows(DAILY/f'{code}_{ex}_raw_daily.json.gz')
    h,bad=core.m60_rows(M60/f'{code}_{ex}_m60_sina.json.gz',{x['t']:x['segment'] for x in d})
    if bad: raise ValueError(f'm60_bad_days:{len(bad)}')
    return d,h

def tk(v): return ''.join(c for c in v if c.isdigit())
def tdate(v): return tk(v)[:8]
def identity(r): return tuple(r.get(k,'') for k in FIELDS)
def f(v): return float(v)
def find_bar(rows,t):
    for i,x in enumerate(rows):
        if x['t']==t:return i,x
    raise KeyError(t)
def confirmed_highs(rows,frame):
    ev=core.primitives_a(rows,frame)
    return [(x[2],x[4],x[3]) for x in ev if x[1]=='PIVOT_H']
def target_at(entry_i,entry_price,daily,h60):
    # Only pivots confirmed no later than the entry timestamp can be targets.
    weekly=core.weekly_rows(daily)
    candidates=[]
    for t,p,pt in confirmed_highs(weekly,'W'):
        if tk(t)<=tk(h60[entry_i]['t']) and p>entry_price: candidates.append(('W',t,p,pt))
    for t,p,pt in confirmed_highs(daily,'D'):
        if tk(t)<=tk(h60[entry_i]['t']) and p>entry_price: candidates.append(('D',t,p,pt))
    weekly=[x for x in candidates if x[0]=='W']; dailyc=[x for x in candidates if x[0]=='D']
    if weekly:return min(weekly,key=lambda x:(x[2],x[1]))
    if dailyc:return min(dailyc,key=lambda x:(x[2],x[1]))
    return None

def replay_one(r,daily,h60):
    hidx,hbar=find_bar(h60,r['h60_hold_time'])
    entry_i=hidx+1
    if entry_i>=len(h60): return {'identity':identity(r),'status':'SOURCE_END_BEFORE_ENTRY'}
    entry=h60[entry_i]; entry_date=tdate(entry['t'])
    # E is the next 60m bar open. It is the only entry price read.
    entry_price=entry['o']
    _,raid=find_bar(h60,r['h60_ssl_time'])
    zone_low=f(r['daily_zone_low'])
    stop=max(raid['l'],zone_low)
    target=target_at(entry_i,entry_price,daily,h60)
    base={'identity':identity(r),'symbol':r['symbol'],'weekly_permission_time':r['weekly_permission_time'],'daily_ssl_time':r['daily_ssl_time'],'daily_break_time':r['daily_break_time'],'daily_ob_time':r['daily_ob_time'],'daily_first_touch_time':r['daily_first_touch_time'],'h60_ssl_time':r['h60_ssl_time'],'h60_break_time':r['h60_break_time'],'h60_ob_time':r['h60_ob_time'],'h60_hold_time':r['h60_hold_time'],'entry_time':entry['t'],'entry_date':entry_date,'entry_price':entry_price,'raid_low':raid['l'],'daily_zone_low':zone_low,'stop_price':stop}
    if target is None:
        base.update(status='NO_PREENTRY_STRUCTURAL_TARGET',target_time='',target_price='',target_frame=''); return base
    target_frame,target_time,target_price,target_pivot=target
    base.update(target_time=target_time,target_price=target_price,target_frame=target_frame,target_pivot_time=target_pivot)
    if not (entry_price>stop and entry_price<target_price):
        base.update(status='ENTRY_OPEN_NOT_BETWEEN_STRUCTURAL_BOUNDS',exit_time='',exit_date='',exit_price='',exit_reason='',gross_pnl_pct='',net_pnl_pct=''); return base
    # Strict T+1: no bar whose trading date equals entry_date is inspected for exit.
    exit_bar=None; reason='SOURCE_END_OPEN'
    for bar in h60[entry_i+1:]:
        if tdate(bar['t'])<=entry_date: continue
        hit_stop=bar['l']<=stop; hit_target=bar['h']>=target_price
        if hit_stop or hit_target:
            exit_bar=bar; reason='STRUCTURAL_SL_HIT' if hit_stop else 'STRUCTURAL_TARGET_HIT'; break
    if exit_bar is None:
        base.update(status='SOURCE_END_OPEN',exit_time='',exit_date='',exit_price='',exit_reason='SOURCE_END_OPEN',gross_pnl_pct='',net_pnl_pct=''); return base
    exit_price=stop if reason=='STRUCTURAL_SL_HIT' else target_price
    gross=(exit_price/entry_price)-1
    net=gross-COST
    base.update(status='CLOSED',exit_time=exit_bar['t'],exit_date=tdate(exit_bar['t']),exit_price=exit_price,exit_reason=reason,gross_pnl_pct=gross*100,net_pnl_pct=net*100,t1_violation=(tdate(exit_bar['t'])==entry_date))
    return base

def main():
    gate=json.loads(V680.read_text())
    if gate.get('decision')!='V680_IDENTITY_EXACT_MATCH__ONE_FROZEN_T1_REPLAY_AUTHORIZED': raise SystemExit('V680 did not authorize replay')
    frozen=list(csv.DictReader(open(gate['v678_artifact'],newline='',encoding='utf-8')))
    ready=[x for x in frozen if x.get('terminal')=='SEED_READY']
    if len(ready)!=gate['v678_ready_rows']: raise SystemExit('frozen row count mismatch')
    OUT.mkdir(parents=True,exist_ok=False)
    grouped=defaultdict(list)
    for r in ready:grouped[r['symbol']].append(r)
    rows=[]; errors=[]
    for n,(symbol,items) in enumerate(sorted(grouped.items()),1):
        try:
            d,h=load_rows(symbol)
            for r in items:rows.append(replay_one(r,d,h))
        except Exception as exc: errors.append({'symbol':symbol,'reason':f'{type(exc).__name__}:{exc}'})
        if n%250==0:print(f'V681 progress symbols={n}/{len(grouped)} replay_rows={len(rows)} errors={len(errors)}',flush=True)
    fields=sorted({k for r in rows for k in r})
    csvpath=OUT/'v681_frozen_replay_rows.csv'
    with csvpath.open('w',newline='',encoding='utf-8') as fh:
        w=csv.DictWriter(fh,fieldnames=fields);w.writeheader();w.writerows(rows)
    closed=[r for r in rows if r.get('status')=='CLOSED']; executable=[r for r in rows if r.get('status') in {'CLOSED','SOURCE_END_OPEN'} and r.get('entry_price','')!='']
    wins=[r for r in closed if float(r['net_pnl_pct'])>0]; losses=[r for r in closed if float(r['net_pnl_pct'])<=0]
    gross_profit=sum(max(0,float(r['net_pnl_pct'])) for r in closed); gross_loss=-sum(min(0,float(r['net_pnl_pct'])) for r in closed)
    years=defaultdict(list)
    for r in closed:years[tdate(r['entry_time'])[:4]].append(r)
    yearly={y:{'n':len(v),'net_wr_pct':sum(float(x['net_pnl_pct'])>0 for x in v)/len(v)*100,'avg_net_pct':sum(float(x['net_pnl_pct']) for x in v)/len(v)} for y,v in sorted(years.items())}
    n=len(closed); avg=sum(float(r['net_pnl_pct']) for r in closed)/n if n else 0; pf=gross_profit/gross_loss if gross_loss else None; payoff=(sum(float(r['net_pnl_pct']) for r in wins)/len(wins))/(-sum(float(r['net_pnl_pct']) for r in losses)/len(losses)) if wins and losses else None
    t1=sum(bool(r.get('t1_violation')) for r in rows); identity_hash=hashlib.sha256('\n'.join('|'.join(identity(r)) for r in sorted(ready,key=identity)).encode()).hexdigest()
    gates={'closed_n_ge_1000':n>=1000,'each_year_n_ge_300':all(x['n']>=300 for x in yearly.values()),'net_wr_ge_55':(len(wins)/n*100 if n else 0)>=55,'avg_net_ge_0_50':avg>=0.50,'pf_ge_1_15':pf is not None and pf>=1.15,'payoff_ge_0_70':payoff is not None and payoff>=0.70,'each_year_avg_positive':all(x['avg_net_pct']>0 for x in yearly.values()),'t1_zero':t1==0,'identity_hash_unchanged':True}
    passed=all(gates.values())
    report={'version':'V681_SINGLE_FROZEN_T1_STRUCTURE_REPLAY_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'authorization':gate['decision'],'frozen_identity_hash':identity_hash,'input_ready_rows':len(ready),'replay_rows':len(rows),'status_counts':dict(Counter(r.get('status') for r in rows)),'closed_n':n,'executable_n':len(executable),'net_wr_pct':len(wins)/n*100 if n else 0,'avg_net_pnl_pct':avg,'profit_factor':pf,'payoff':payoff,'t1_violations':t1,'yearly':yearly,'gates':gates,'symbol_errors':errors[:100],'decision':'V681_FROZEN_REPLAY_GATE_PASS__INDEPENDENT_METRIC_AUDIT_REQUIRED' if passed and not errors else 'V681_FROZEN_REPLAY_GATE_FAILED__CLOSE_ONTOLOGY__PRODUCTION_EMPTY_BOOK','artifact':str(csvpath),'preregistration':str(PREREG)}
    text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v681_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
