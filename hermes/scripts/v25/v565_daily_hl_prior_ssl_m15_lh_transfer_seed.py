#!/usr/bin/env python3
"""V565 outcome-blind seed gate: daily HL -> prior-day SSL raid -> M15 confirmed LH transfer.

New ontology:
  completed daily higher-low parent -> M15 raid/reclaim of the *prior daily low*
  -> break a M15 lower high confirmed before that raid -> one M15 hold -> D+1 open.
It is distinct from V543's FVG-displacement chain and V564's opening-range pool.
"""
from __future__ import annotations
import csv, gzip, json, math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; RAW=ROOT/'intraday_cache/raw_multitf_v536/source_raw/sina'
DAILY=RAW/'daily'; M15=RAW/'m15'; OUT=AUD/f'v565_daily_hl_prior_ssl_m15_lh_transfer_seed_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST=AUD/'v565_daily_hl_prior_ssl_m15_lh_transfer_seed_latest.json'; YEARS=('2025','2026')
SUPPORT={'seed_total_min':3000,'seed_each_year_min':1200,'unique_symbols_min':500}


def f(x: Any)->float|None:
    try:
        v=float(x); return v if math.isfinite(v) and v>0 else None
    except (TypeError,ValueError): return None


def load(path:Path)->list[dict[str,Any]]:
    try:
        with gzip.open(path,'rt',encoding='utf-8') as h: x=json.load(h)
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


def daily_hl_parent(xs:list[dict[str,Any]])->dict[str,dict[str,Any]]:
    lows=[]
    for i in range(3,len(xs)-3):
        if xs[i]['l']<min(x['l'] for x in xs[i-3:i]) and xs[i]['l']<=min(x['l'] for x in xs[i+1:i+4]): lows.append((i,i+3,xs[i]['l']))
    out={}
    for i,row in enumerate(xs):
        known=[x for x in lows if x[1]<i]
        if len(known)<2: continue
        prior,last=known[-2:]
        if last[2]>prior[2] and xs[i-1]['c']>last[2]:
            out[row['d']]={'daily_prior_hl_date':xs[prior[0]]['d'],'daily_latest_hl_date':xs[last[0]]['d'],'daily_hl_confirm_date':xs[last[1]]['d']}
    return out


def m15_event(xs:list[dict[str,Any]],prior_low:float)->tuple[dict[str,Any]|None,str]:
    if len(xs)!=16: return None,'M15_INCOMPLETE_SESSION'
    # Each LH pivot has 2 completed right bars before the external SSL raid.
    highs=[]
    for i in range(2,len(xs)-2):
        if xs[i]['h']>max(x['h'] for x in xs[i-2:i]) and xs[i]['h']>=max(x['h'] for x in xs[i+1:i+3]): highs.append((i,i+2,xs[i]['h']))
    for raid_i,raid in enumerate(xs):
        if raid['l']>=prior_low*.997 or raid['c']<=prior_low: continue
        known=[x for x in highs if x[1]<raid_i]
        if len(known)<2: continue
        # Last descending high is the local bearish structure to transfer.
        lh=next((x for x in reversed(known[1:]) if x[2]<known[known.index(x)-1][2]),None)
        if lh is None: continue
        for break_i in range(raid_i+1,15):
            b,hold=xs[break_i],xs[break_i+1]
            if b['c']>lh[2]*1.001 and hold['c']>lh[2]:
                return {'prior_daily_ssl_low':round(prior_low,8),'external_ssl_raid_time':raid['t'],'external_ssl_raid_low':round(raid['l'],8),'external_ssl_reclaim_close':round(raid['c'],8),'m15_lh_time':xs[lh[0]]['t'],'m15_lh_confirm_time':xs[lh[1]]['t'],'m15_lh_high':round(lh[2],8),'m15_choch_break_time':b['t'],'m15_choch_hold_time':hold['t']},'PASS'
    return None,'NO_PRIOR_DAILY_SSL_TO_CONFIRMED_LH_TRANSFER'


def main()->None:
    OUT.mkdir(parents=True,exist_ok=False); rows=[]; reject=Counter(); scanned=0
    for path in sorted(DAILY.glob('*_daily.json.gz')):
        parts=path.name.removesuffix('_daily.json.gz').split('_',1)
        if len(parts)!=2: continue
        sym=f'{parts[0]}.{parts[1]}'; ds=daily(sym)
        if len(ds)<30: reject['DAILY_TOO_SHORT']+=1; continue
        parent=daily_hl_parent(ds); ss=sessions(sym); nxt={a['d']:b['d'] for a,b in zip(ds,ds[1:])}; bydate={x['d']:(i,x) for i,x in enumerate(ds)}
        for d,state in parent.items():
            if d[:4] not in YEARS: continue
            idx,now=bydate[d]
            if idx<1: continue
            event,status=m15_event(ss.get(d,[]),ds[idx-1]['l']); reject[status]+=1
            entry=nxt.get(d)
            if event is None or not entry:
                if event is not None: reject['NO_NEXT_DAILY_SESSION']+=1
                continue
            assert state['daily_hl_confirm_date']<d<entry
            assert event['m15_lh_confirm_time']<event['external_ssl_raid_time']<event['m15_choch_break_time']<event['m15_choch_hold_time']<entry+'000000'
            rows.append({'symbol':sym,'ontology':'DAILY_PROTECTED_HL_TO_PRIOR_DAILY_SSL_M15_LH_TRANSFER','signal_date':d,'eligible_entry_date':entry,'tradable':'false','buy_enabled':'false','no_outcome_fields':'true',**state,**event})
        scanned+=1
        if scanned%1000==0: print(json.dumps({'symbols_scanned':scanned,'seeds':len(rows)},ensure_ascii=False),flush=True)
    rows.sort(key=lambda x:(x['signal_date'],x['symbol'],x['m15_choch_hold_time'])); rows=list({(x['symbol'],x['signal_date']):x for x in rows}.values()); rows.sort(key=lambda x:(x['signal_date'],x['symbol']))
    years=Counter(x['signal_date'][:4] for x in rows)
    inv={'source_isolated_sina_only':True,'no_outcome_fields':all(not any(t in k.lower() for k in r for t in ('pnl','return','exit','mae','mfe','target','stop')) for r in rows),'all_parent_confirmed_before_signal':all(r['daily_hl_confirm_date']<r['signal_date'] for r in rows),'all_m15_chain_before_entry':all(r['m15_lh_confirm_time']<r['external_ssl_raid_time']<r['m15_choch_break_time']<r['m15_choch_hold_time']<r['eligible_entry_date']+'000000' for r in rows),'all_execution_next_trade_day':all(r['eligible_entry_date']>r['signal_date'] for r in rows),'seed_total_capacity':len(rows)>=SUPPORT['seed_total_min'],'seed_each_year_capacity':all(years[y]>=SUPPORT['seed_each_year_min'] for y in YEARS),'unique_symbols_capacity':len({r['symbol'] for r in rows})>=SUPPORT['unique_symbols_min']}
    seeds=OUT/'v565_outcome_blind_seeds.csv'; fields=sorted({k for r in rows for k in r}) if rows else ['symbol','signal_date']
    with seeds.open('w',newline='',encoding='utf-8') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(rows)
    rep={'version':'V565_DAILY_HL_PRIOR_DAILY_SSL_M15_LH_TRANSFER_SEED_NO_OUTCOME','generated_at':datetime.now().isoformat(timespec='seconds'),'research_only':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'scope':'SINA_SOURCE_ISOLATED_COMPLETE_2025_2026_PARTIAL_HISTORY__RESEARCH_ONLY','hypothesis':'A completed daily higher-low parent plus a same-session raid/reclaim of the prior daily external SSL and confirmed M15 lower-high transfer identifies next-day-executable demand acceptance.','distinctness':'The external liquidity source is the prior completed daily low; no V543 FVG/displacement/volume condition, no V564 opening-range pool, no V562 industry BOS/ranking/participation is used.','frozen_pre_outcome_contract':'before D confirmed 3L/3R daily prior HL then higher HL; on D wick raid prior daily low >=0.3% then close above it; break a pre-raid 2L/2R confirmed descending M15 LH by >=0.1% then next M15 close holds; only D+1 daily open eligible. No outcomes read.','support_gate_before_outcomes':SUPPORT,'seed_count':len(rows),'year_counts':dict(sorted(years.items())),'unique_symbols':len({r['symbol'] for r in rows}),'symbols_scanned':scanned,'rejection_counts':dict(reject),'invariants':inv,'decision':'V565_SUPPORT_PASS__INDEPENDENT_ORACLE_REQUIRED_NEXT' if all(inv.values()) else 'V565_SUPPORT_INSUFFICIENT__NO_OUTCOMES_OPENED__CLOSE_OBJECT','artifacts':{'out_dir':str(OUT),'seeds':str(seeds),'latest':str(LATEST)}}
    text=json.dumps(rep,ensure_ascii=False,indent=2); (OUT/'v565_report.json').write_text(text); LATEST.write_text(text); print(text)

if __name__=='__main__': main()
