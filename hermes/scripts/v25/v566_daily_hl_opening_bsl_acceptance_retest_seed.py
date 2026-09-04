#!/usr/bin/env python3
"""V566 outcome-blind seed gate: daily HL -> M15 opening BSL acceptance/retest.

New continuation ontology:
completed daily higher-low parent -> M15 close acceptance above the first-hour
opening-range high -> later wick retest of that broken BSL with close above ->
one M15 hold -> D+1 open.  It has no sell-side sweep requirement.
"""
from __future__ import annotations
import csv, gzip, json, math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; RAW=ROOT/'intraday_cache/raw_multitf_v536/source_raw/sina'; DAILY=RAW/'daily'; M15=RAW/'m15'
OUT=AUD/f'v566_daily_hl_opening_bsl_acceptance_retest_seed_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'; LATEST=AUD/'v566_daily_hl_opening_bsl_acceptance_retest_seed_latest.json'; YEARS=('2025','2026')
# Capacity pre-gate; final replay remains n>=1000 and each year>=300.
SUPPORT={'seed_total_min':2000,'seed_each_year_min':800,'unique_symbols_min':500}

def f(x:Any)->float|None:
    try:
        v=float(x); return v if math.isfinite(v) and v>0 else None
    except (ValueError,TypeError): return None

def load(p:Path)->list[dict[str,Any]]:
    try:
        with gzip.open(p,'rt',encoding='utf-8') as h: x=json.load(h)
        return x if isinstance(x,list) else []
    except (OSError,ValueError): return []

def daily(sym:str)->list[dict[str,Any]]:
    out=[]
    for x in load(DAILY/f'{sym.replace(".","_")}_daily.json.gz'):
        d=str(x.get('d') or x.get('t') or '')[:8]; v=[f(x.get(k)) for k in ('o','h','l','c')]
        if len(d)==8 and all(z is not None for z in v): out.append({'d':d,'o':v[0],'h':v[1],'l':v[2],'c':v[3]})
    return sorted(out,key=lambda x:x['d'])

def sessions(sym:str)->dict[str,list[dict[str,Any]]]:
    out=defaultdict(list)
    for x in load(M15/f'{sym.replace(".","_")}_m15.json.gz'):
        t=str(x.get('t') or ''); v=[f(x.get(k)) for k in ('o','h','l','c')]
        if len(t)==14 and all(z is not None for z in v): out[t[:8]].append({'t':t,'o':v[0],'h':v[1],'l':v[2],'c':v[3]})
    for xs in out.values(): xs.sort(key=lambda x:x['t'])
    return out

def parent(xs:list[dict[str,Any]])->dict[str,dict[str,str]]:
    lows=[]
    for i in range(3,len(xs)-3):
        if xs[i]['l']<min(x['l'] for x in xs[i-3:i]) and xs[i]['l']<=min(x['l'] for x in xs[i+1:i+4]): lows.append((i,i+3,xs[i]['l']))
    out={}
    for i,x in enumerate(xs):
        known=[p for p in lows if p[1]<i]
        if len(known)>=2 and known[-1][2]>known[-2][2] and xs[i-1]['c']>known[-1][2]:
            out[x['d']]={'daily_prior_hl_date':xs[known[-2][0]]['d'],'daily_latest_hl_date':xs[known[-1][0]]['d'],'daily_hl_confirm_date':xs[known[-1][1]]['d']}
    return out

def event(xs:list[dict[str,Any]])->tuple[dict[str,Any]|None,str]:
    if len(xs)!=16: return None,'M15_INCOMPLETE_SESSION'
    opening=xs[:4]; high=max(x['h'] for x in opening)
    for br_i in range(4,13):
        br=xs[br_i]
        if br['c']<=high*1.001: continue
        # Retest starts strictly after acceptance; wick may touch but close must accept above BSL.
        for rt_i in range(br_i+1,15):
            rt,hold=xs[rt_i],xs[rt_i+1]
            if rt['l']<=high*1.001 and rt['c']>high and hold['c']>high:
                return {'opening_bsl_start_time':opening[0]['t'],'opening_bsl_end_time':opening[-1]['t'],'opening_bsl_high':round(high,8),'bsl_acceptance_break_time':br['t'],'bsl_acceptance_break_close':round(br['c'],8),'bsl_retest_time':rt['t'],'bsl_retest_low':round(rt['l'],8),'bsl_retest_close':round(rt['c'],8),'bsl_hold_time':hold['t']},'PASS'
    return None,'NO_OPENING_BSL_ACCEPTANCE_RETEST'

def main()->None:
    OUT.mkdir(parents=True,exist_ok=False); rows=[]; rejects=Counter(); scanned=0
    for p in sorted(DAILY.glob('*_daily.json.gz')):
        z=p.name.removesuffix('_daily.json.gz').split('_',1)
        if len(z)!=2: continue
        sym=f'{z[0]}.{z[1]}'; ds=daily(sym)
        if len(ds)<30: rejects['DAILY_TOO_SHORT']+=1; continue
        ps=parent(ds); ss=sessions(sym); nxt={a['d']:b['d'] for a,b in zip(ds,ds[1:])}
        for d,state in ps.items():
            if d[:4] not in YEARS: continue
            e,status=event(ss.get(d,[])); rejects[status]+=1; entry=nxt.get(d)
            if e is None or not entry:
                if e is not None: rejects['NO_NEXT_DAILY_SESSION']+=1
                continue
            assert state['daily_hl_confirm_date']<d<entry
            assert e['bsl_acceptance_break_time']<e['bsl_retest_time']<e['bsl_hold_time']<entry+'000000'
            rows.append({'symbol':sym,'ontology':'DAILY_PROTECTED_HL_TO_M15_OPENING_BSL_ACCEPTANCE_RETEST','signal_date':d,'eligible_entry_date':entry,'tradable':'false','buy_enabled':'false','no_outcome_fields':'true',**state,**e})
        scanned+=1
        if scanned%1000==0: print(json.dumps({'symbols_scanned':scanned,'seeds':len(rows)},ensure_ascii=False),flush=True)
    rows.sort(key=lambda x:(x['signal_date'],x['symbol'],x['bsl_hold_time'])); rows=list({(x['symbol'],x['signal_date']):x for x in rows}.values()); rows.sort(key=lambda x:(x['signal_date'],x['symbol']))
    years=Counter(x['signal_date'][:4] for x in rows)
    inv={'source_isolated_sina_only':True,'no_outcome_fields':all(not any(t in k.lower() for k in r for t in ('pnl','return','exit','mae','mfe','target','stop')) for r in rows),'all_parent_confirmed_before_signal':all(r['daily_hl_confirm_date']<r['signal_date'] for r in rows),'all_m15_chain_before_entry':all(r['bsl_acceptance_break_time']<r['bsl_retest_time']<r['bsl_hold_time']<r['eligible_entry_date']+'000000' for r in rows),'all_execution_next_trade_day':all(r['eligible_entry_date']>r['signal_date'] for r in rows),'seed_total_capacity':len(rows)>=SUPPORT['seed_total_min'],'seed_each_year_capacity':all(years[y]>=SUPPORT['seed_each_year_min'] for y in YEARS),'unique_symbols_capacity':len({r['symbol'] for r in rows})>=SUPPORT['unique_symbols_min']}
    seeds=OUT/'v566_outcome_blind_seeds.csv'; fields=sorted({k for r in rows for k in r}) if rows else ['symbol','signal_date']
    with seeds.open('w',newline='',encoding='utf-8') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(rows)
    rep={'version':'V566_DAILY_HL_OPENING_BSL_ACCEPTANCE_RETEST_SEED_NO_OUTCOME','generated_at':datetime.now().isoformat(timespec='seconds'),'research_only':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'scope':'SINA_SOURCE_ISOLATED_COMPLETE_2025_2026_PARTIAL_HISTORY__RESEARCH_ONLY','hypothesis':'A completed daily higher-low parent plus accepted/retested first-hour buy-side liquidity predicts a T+1-survivable intraday continuation.','distinctness':'No V543 sweep/FVG/displacement/volume chain, V564 opening-range SSL raid, V565 prior-day SSL raid, or V562 industry event/selection is used. The event is BSL acceptance then retest.','frozen_pre_outcome_contract':'before D completed daily 3L/3R prior HL then higher HL; first four M15 bars form BSL at high; later close >=0.1% above BSL; later bar wick reaches BSL and closes above it; next M15 close remains above BSL; execution only D+1 daily open. No outcomes read.','support_gate_before_outcomes':SUPPORT,'final_replay_gate':'n>=1000; each year>=300; WR>=55%; AvgNet>=+0.50%; PF>=1.15; payoff>=0.70; every year AvgNet>0; T+1 violations=0','seed_count':len(rows),'year_counts':dict(sorted(years.items())),'unique_symbols':len({r['symbol'] for r in rows}),'symbols_scanned':scanned,'rejection_counts':dict(rejects),'invariants':inv,'decision':'V566_SUPPORT_PASS__INDEPENDENT_ORACLE_REQUIRED_NEXT' if all(inv.values()) else 'V566_SUPPORT_INSUFFICIENT__NO_OUTCOMES_OPENED__CLOSE_OBJECT','artifacts':{'out_dir':str(OUT),'seeds':str(seeds),'latest':str(LATEST)}}
    text=json.dumps(rep,ensure_ascii=False,indent=2); (OUT/'v566_report.json').write_text(text); LATEST.write_text(text); print(text)
if __name__=='__main__': main()
