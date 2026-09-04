#!/usr/bin/env python3
"""V447 no-outcome generator: SSL raid -> opposing-FVG BPR -> retest/reclaim/hold.

Frozen causal ontology:
1. A bearish FVG forms on a downward leg.
2. That leg or the next three bars wick-sweeps a 3L/3R confirmed swing low and closes back above it.
3. Within five bars after the sweep, a bullish FVG overlaps the bearish FVG, creating a BPR.
4. After BPR creation: first retest -> reclaim above BPR -> one-bar hold -> next-open eligibility.

No entries, exits, PnL, MFE/MAE, targets, or outcomes are created here.
"""
from __future__ import annotations
import csv, json, math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
OUT=AUD/f"v447_ssl_bpr_reversal_generator_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST=AUD/'v447_ssl_bpr_reversal_generator_latest.json'

def f(x):
    try:
        v=float(x); return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError): return 0.0

def day(b): return ''.join(c for c in str(b.get('t') or b.get('date') or '') if c.isdigit())[:8]

def load(path):
    try: raw=json.loads(path.read_text())
    except (OSError,json.JSONDecodeError): return []
    rows=[]
    for b in raw:
        r={k:f(b.get(k)) for k in ('o','h','l','c')}
        if day(b) and all(r.values()): r['t']=day(b); rows.append(r)
    return sorted(rows,key=lambda x:x['t'])

def symbol(path):
    code,ex=path.name.removesuffix('_daily_750.json').split('_'); return f'{code}.{ex}'

def confirmed_lows(bars):
    out=[]
    for i in range(3,len(bars)-3):
        if all(bars[j]['l']>bars[i]['l'] for j in range(i-3,i+4) if j!=i):
            out.append((i,i+3,bars[i]['l']))
    return out

def generate(sym,bars):
    lows=confirmed_lows(bars); rows=[]; seen=set(); rejects=Counter()
    for bear in range(2,len(bars)-10):
        bear_low=bars[bear]['h']; bear_high=bars[bear-2]['l']
        if bear_high<=bear_low*1.0005: continue
        leg_start=bear-2
        prior=[x for x in lows if x[1]<leg_start and leg_start-x[0]<=60]
        if not prior: rejects['NO_CONFIRMED_SSL_REFERENCE']+=1; continue
        ref=prior[-1]
        sweep=next((i for i in range(leg_start,min(len(bars),bear+4))
                    if bars[i]['l']<ref[2]*.997 and bars[i]['c']>ref[2]),None)
        if sweep is None: rejects['NO_SSL_RAID_AND_RECLAIM']+=1; continue
        bull=None; bpr_low=bpr_high=0.0
        for u in range(max(bear+1,sweep+1),min(len(bars),sweep+6)):
            bull_low=bars[u-2]['h']; bull_high=bars[u]['l']
            if bull_high<=bull_low*1.0005: continue
            lo=max(bear_low,bull_low); hi=min(bear_high,bull_high)
            if hi>lo*1.0005 and bars[u]['c']>hi:
                bull,bpr_low,bpr_high=u,lo,hi; break
        if bull is None: rejects['NO_OVERLAPPING_BULL_FVG']+=1; continue
        touch=reclaim=hold=None; cancelled=False
        for j in range(bull+1,min(len(bars),bull+21)):
            b=bars[j]
            if b['c']<min(bpr_low,ref[2]): cancelled=True; break
            if touch is None:
                if b['l']<=bpr_high and b['h']>=bpr_low: touch=j
                continue
            if reclaim is None:
                if j>touch and b['c']>bpr_high: reclaim=j
                continue
            if j>reclaim and b['c']>bpr_high and b['l']>=bpr_low: hold=j; break
        if cancelled: rejects['BPR_OR_SSL_INVALIDATED']+=1; continue
        if hold is None or hold+1>=len(bars): rejects['NO_COMPLETE_LIFECYCLE']+=1; continue
        key=(sym,bars[hold+1]['t'])
        if key in seen: rejects['DUPLICATE_SYMBOL_ENTRY']+=1; continue
        seen.add(key)
        rows.append({'symbol':sym,'ontology':'SSL_OPPOSING_FVG_BPR_REVERSAL',
          'ssl_ref_idx':ref[0],'ssl_confirm_idx':ref[1],'ssl_price':round(ref[2],6),
          'bear_fvg_idx':bear,'bear_fvg_date':bars[bear]['t'],'bear_fvg_low':round(bear_low,6),'bear_fvg_high':round(bear_high,6),
          'sweep_idx':sweep,'sweep_date':bars[sweep]['t'],'sweep_low':round(bars[sweep]['l'],6),
          'bull_fvg_idx':bull,'bull_fvg_date':bars[bull]['t'],'bpr_low':round(bpr_low,6),'bpr_high':round(bpr_high,6),
          'touch_idx':touch,'touch_date':bars[touch]['t'],'reclaim_idx':reclaim,'reclaim_date':bars[reclaim]['t'],
          'takeover_idx':hold,'takeover_date':bars[hold]['t'],'eligible_entry_idx':hold+1,'eligible_entry_date':bars[hold+1]['t'],
          'structural_sl_ref':round(min(ref[2],bars[sweep]['l']),6),
          'semantic_order_valid':ref[1]<leg_start<=sweep<bull<touch<reclaim<hold<hold+1,
          'tradable':False,'buy_enabled':False,'no_outcome_fields':True})
    return rows,rejects

def main():
    OUT.mkdir(parents=True,exist_ok=True); rows=[]; rejects=Counter(); scanned=0
    for n,path in enumerate(sorted(KDIR.glob('*_daily_750.json')),1):
        bars=load(path)
        if len(bars)<80: continue
        scanned+=1; generated,bad=generate(symbol(path),bars); rows.extend(generated); rejects.update(bad)
        if n%500==0: print(json.dumps({'progress':n,'seeds':len(rows)}),flush=True)
    fields=sorted({k for r in rows for k in r})
    seed_file=OUT/'v447_semantic_seeds.csv'
    with seed_file.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(rows)
    yearly=Counter(r['eligible_entry_date'][:4] for r in rows)
    result={'version':'V447_SSL_BPR_REVERSAL_GENERATOR_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),
      'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'frozen_contract':'bear FVG -> confirmed SSL raid/reclaim -> overlapping bull FVG creates BPR -> later touch -> reclaim -> hold -> next-open eligibility',
      'symbols_scanned':scanned,'seed_count':len(rows),'yearly_seed_count':dict(sorted(yearly.items())),
      'rejection_counts':dict(rejects),'semantic_order_failures':sum(not r['semantic_order_valid'] for r in rows),
      'duplicate_symbol_entry':len(rows)-len(set((r['symbol'],r['eligible_entry_date']) for r in rows)),
      'invariants':{'no_entries_created':True,'no_outcome_fields':all(r['no_outcome_fields'] for r in rows),'all_nontradable':all(not r['tradable'] and not r['buy_enabled'] for r in rows)},
      'support_gate_pass':len(rows)>=300 and all(yearly[y]>=40 for y in ('2023','2024','2025','2026')),
      'decision':'SEMANTIC_SEEDS_READY_FOR_INDEPENDENT_ORACLE' if rows else 'NO_SEEDS',
      'artifacts':{'out_dir':str(OUT),'seeds':str(seed_file),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2); (OUT/'v447_report.json').write_text(text); LATEST.write_text(text); print(text)
if __name__=='__main__': main()
