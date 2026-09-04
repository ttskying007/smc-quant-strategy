#!/usr/bin/env python3
"""V473 outcome-blind bullish inducement-sweep continuation generator.

Frozen ontology: external protected low -> confirmed swing high -> bullish close-BOS
-> higher internal low -> internal-low wick raid/close-back while external low is
untouched -> close above raid high within three bars -> next-open eligibility.
"""
from __future__ import annotations
import csv, json, math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
OUT=AUD/f"v473_inducement_sweep_continuation_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST=AUD/'v473_inducement_sweep_continuation_latest.json'
YEARS=('2023','2024','2025','2026')

def f(x):
    try:
        v=float(x); return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError): return 0.0

def ds(x): return ''.join(c for c in str(x or '') if c.isdigit())[:8]

def load(path):
    try: raw=json.loads(path.read_text())
    except (OSError,json.JSONDecodeError): return []
    rows=[]
    for b in raw:
        r={k:f(b.get(k)) for k in ('o','h','l','c')}; d=ds(b.get('t') or b.get('date'))
        if d and all(r.values()): r['t']=d; rows.append(r)
    return sorted(rows,key=lambda x:x['t'])

def symbol(path):
    code,ex=path.name.removesuffix('_daily_750.json').split('_'); return f'{code}.{ex}'

def pivots(bars,key):
    cmp=(lambda a,b:a<b) if key=='l' else (lambda a,b:a>b)
    return [{'idx':i,'confirm_idx':i+3,'price':bars[i][key]}
            for i in range(3,len(bars)-3)
            if all(cmp(bars[i][key],bars[j][key]) for j in range(i-3,i+4) if j!=i)]

def contexts(bars):
    lows=pivots(bars,'l'); highs=pivots(bars,'h'); out=[]
    for internal in lows:
        old=[x for x in lows if x['idx']<internal['idx'] and x['price']<internal['price']]
        if not old: continue
        external=max(old,key=lambda x:x['idx'])
        hs=[x for x in highs if external['confirm_idx']<x['idx']<internal['idx'] and x['confirm_idx']<internal['idx']]
        if not hs: continue
        h=max(hs,key=lambda x:x['idx'])
        bos=next((j for j in range(h['confirm_idx']+1,internal['idx']) if bars[j]['c']>h['price']),None)
        if bos is None: continue
        if any(bars[j]['l']<=external['price'] for j in range(bos+1,internal['confirm_idx']+1)): continue
        out.append({'external':external,'high':h,'bos_idx':bos,'internal':internal})
    return out

def generate(sym,bars):
    ctx=contexts(bars); rows=[]; rejects=Counter()
    for raid in range(10,len(bars)-4):
        eligible=[x for x in ctx if x['internal']['confirm_idx']<raid and raid-x['internal']['idx']<=60
                  and bars[raid]['l']<x['internal']['price']*.997 and bars[raid]['c']>x['internal']['price']
                  and bars[raid]['l']>x['external']['price']]
        if not eligible: continue
        x=max(eligible,key=lambda z:z['internal']['idx'])
        confirm=next((j for j in range(raid+1,min(len(bars),raid+4)) if bars[j]['c']>bars[raid]['h']),None)
        if confirm is None: rejects['NO_CLOSE_ABOVE_RAID_HIGH_WITHIN_3B']+=1; continue
        entry=confirm+1
        if entry>=len(bars): rejects['ENTRY_RIGHT_EDGE']+=1; continue
        ext,high,internal=x['external'],x['high'],x['internal']
        order=ext['confirm_idx']<high['idx']<high['confirm_idx']<x['bos_idx']<internal['idx']<internal['confirm_idx']<raid<confirm<entry
        rows.append({'symbol':sym,'ontology':'BULLISH_INTERNAL_INDUCEMENT_SWEEP_CONTINUATION',
          'external_low_idx':ext['idx'],'external_low_confirm_idx':ext['confirm_idx'],'external_low_price':round(ext['price'],6),
          'structure_high_idx':high['idx'],'structure_high_confirm_idx':high['confirm_idx'],'structure_high_price':round(high['price'],6),
          'bos_idx':x['bos_idx'],'bos_date':bars[x['bos_idx']]['t'],
          'internal_low_idx':internal['idx'],'internal_low_confirm_idx':internal['confirm_idx'],'internal_low_price':round(internal['price'],6),
          'raid_idx':raid,'raid_date':bars[raid]['t'],'raid_low':round(bars[raid]['l'],6),'raid_high':round(bars[raid]['h'],6),
          'reversal_confirm_idx':confirm,'reversal_confirm_date':bars[confirm]['t'],
          'eligible_entry_idx':entry,'eligible_entry_date':bars[entry]['t'],'structural_sl_ref':round(bars[raid]['l'],6),
          'semantic_order_valid':order,'tradable':False,'buy_enabled':False,'no_outcome_fields':True})
    return rows,rejects

def main():
    OUT.mkdir(parents=True,exist_ok=True); raw=[]; rejects=Counter(); scanned=0
    for n,path in enumerate(sorted(KDIR.glob('*_daily_750.json')),1):
        bars=load(path)
        if len(bars)<80: continue
        scanned+=1; rows,bad=generate(symbol(path),bars); raw.extend(rows); rejects.update(bad)
        if n%500==0: print(json.dumps({'progress':n,'raw_seeds':len(raw)}),flush=True)
    dedup={}
    for row in raw:
        key=(row['symbol'],row['eligible_entry_date']); old=dedup.get(key)
        if old is None or row['raid_idx']<old['raid_idx']: dedup[key]=row
    rows=list(dedup.values()); yearly=Counter(r['eligible_entry_date'][:4] for r in rows)
    support=len(rows)>=300 and all(yearly.get(y,0)>=40 for y in YEARS)
    seed_file=OUT/'v473_semantic_seeds.csv'; fields=list(rows[0]) if rows else ['symbol','ontology']
    with seed_file.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(rows)
    report={'version':'V473_INDUCEMENT_SWEEP_CONTINUATION_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),
      'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'frozen_contract':'external protected low -> confirmed high -> bull close-BOS -> higher internal low -> internal-low raid/close-back while external low untouched -> close above raid high within 3 bars -> next-open eligibility',
      'distinct_information':'Internal inducement liquidity is raided inside an already established bullish protected structure; unlike Turtle Soup it does not trade an external SSL failure, and unlike protected-swing transfer it does not require a second BOS plus POI retest.',
      'symbols_scanned':scanned,'raw_seed_count':len(raw),'seed_count':len(rows),'yearly_seed_count':dict(sorted(yearly.items())),
      'rejection_counts':dict(rejects),'support_gate_pass':support,'invariants':{'semantic_order_failures':sum(not r['semantic_order_valid'] for r in rows),'duplicate_symbol_entry':len(rows)-len(set((r['symbol'],r['eligible_entry_date']) for r in rows)),'no_outcome_fields':all(r['no_outcome_fields'] for r in rows),'all_nontradable':all(not r['tradable'] and not r['buy_enabled'] for r in rows)},
      'decision':'INDUCEMENT_SWEEP_SEEDS_READY__INDEPENDENT_ORACLE_NEXT' if support and not any(not r['semantic_order_valid'] for r in rows) else 'INDUCEMENT_SWEEP_PRE_OUTCOME_GATE_FAIL__NO_REPLAY',
      'artifacts':{'out_dir':str(OUT),'seeds':str(seed_file),'latest':str(LATEST)}}
    text=json.dumps(report,ensure_ascii=False,indent=2); (OUT/'v473_report.json').write_text(text); LATEST.write_text(text); print(text)
if __name__=='__main__': main()
