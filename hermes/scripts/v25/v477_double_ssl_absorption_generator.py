#!/usr/bin/env python3
"""V477 outcome-blind double-SSL-raid absorption reversal generator.

Frozen ontology: most-recent visible 3L/3R SSL -> first >=0.3% wick raid and
close-back without confirming above its high -> 2..10 bars later a second raid
of the same SSL, with a higher raid low and close-back -> close above both raid
highs within three bars -> next-session eligibility.
"""
from __future__ import annotations
import csv, json, math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
OUT=AUD/f"v477_double_ssl_absorption_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST=AUD/'v477_double_ssl_absorption_latest.json'; YEARS=('2023','2024','2025','2026')


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


def confirmed_lows(bars):
    return [{'idx':i,'confirm_idx':i+3,'price':bars[i]['l']}
            for i in range(3,len(bars)-3)
            if all(bars[j]['l']>bars[i]['l'] for j in range(i-3,i+4) if j!=i)]


def generate(sym,bars):
    lows=confirmed_lows(bars); rows=[]; rejects=Counter()
    for first in range(7,len(bars)-6):
        refs=[x for x in lows if x['confirm_idx']<first and first-x['idx']<=60
              and bars[first]['l']<x['price']*.997 and bars[first]['c']>x['price']]
        if not refs: continue
        ref=max(refs,key=lambda x:x['idx'])
        for second in range(first+2,min(len(bars)-4,first+11)):
            if any(bars[j]['c']>bars[first]['h'] for j in range(first+1,second)):
                rejects['FIRST_RAID_ALREADY_CONFIRMED']+=1; break
            if any(bars[j]['c']<bars[first]['l'] for j in range(first+1,second)):
                rejects['ABSORPTION_FLOOR_BROKEN']+=1; break
            if not (bars[second]['l']<ref['price']*.997 and bars[second]['c']>ref['price']
                    and bars[second]['l']>bars[first]['l']):
                continue
            trigger=max(bars[first]['h'],bars[second]['h'])
            confirm=next((j for j in range(second+1,min(len(bars),second+4)) if bars[j]['c']>trigger),None)
            if confirm is None:
                rejects['NO_CLOSE_ABOVE_BOTH_RAID_HIGHS_WITHIN_3B']+=1; break
            eligible=confirm+1
            if eligible>=len(bars): rejects['ENTRY_RIGHT_EDGE']+=1; break
            order=ref['confirm_idx']<first<second<confirm<eligible
            rows.append({'symbol':sym,'ontology':'DOUBLE_SSL_RAID_ABSORPTION_REVERSAL',
              'ssl_idx':ref['idx'],'ssl_confirm_idx':ref['confirm_idx'],'ssl_price':round(ref['price'],6),
              'first_raid_idx':first,'first_raid_date':bars[first]['t'],'first_raid_low':round(bars[first]['l'],6),'first_raid_high':round(bars[first]['h'],6),
              'second_raid_idx':second,'second_raid_date':bars[second]['t'],'second_raid_low':round(bars[second]['l'],6),'second_raid_high':round(bars[second]['h'],6),
              'reversal_trigger':round(trigger,6),'reversal_confirm_idx':confirm,'reversal_confirm_date':bars[confirm]['t'],
              'eligible_entry_idx':eligible,'eligible_entry_date':bars[eligible]['t'],'structural_sl_ref':round(min(bars[first]['l'],bars[second]['l']),6),
              'semantic_order_valid':order,'tradable':False,'buy_enabled':False,'no_outcome_fields':True})
            break
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
        if old is None or row['second_raid_idx']<old['second_raid_idx']: dedup[key]=row
    rows=list(dedup.values()); yearly=Counter(r['eligible_entry_date'][:4] for r in rows)
    support=len(rows)>=300 and all(yearly.get(y,0)>=40 for y in YEARS)
    seed_file=OUT/'v477_semantic_seeds.csv'; fields=list(rows[0]) if rows else ['symbol','ontology']
    with seed_file.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(rows)
    result={'version':'V477_DOUBLE_SSL_ABSORPTION_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),
      'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'frozen_contract':'most-recent confirmed 3L/3R SSL -> first >=0.3% raid/close-back with no close above raid high -> 2..10 bars later higher-low second raid of same SSL/close-back while first floor holds -> close above both raid highs within 3 bars -> next-open eligibility',
      'distinct_information':'Repeated same-pool absorption and seller exhaustion; unlike single-raid Turtle Soup it requires an unresolved first raid and a higher-low second raid before expansion, and unlike inducement continuation it starts from external SSL without prior bull BOS.',
      'symbols_scanned':scanned,'raw_seed_count':len(raw),'seed_count':len(rows),'yearly_seed_count':dict(sorted(yearly.items())),
      'rejection_counts':dict(rejects),'support_gate_pass':support,
      'invariants':{'semantic_order_failures':sum(not r['semantic_order_valid'] for r in rows),'duplicate_symbol_entry':len(rows)-len(set((r['symbol'],r['eligible_entry_date']) for r in rows)),'no_outcome_fields':all(r['no_outcome_fields'] for r in rows),'all_nontradable':all(not r['tradable'] and not r['buy_enabled'] for r in rows)},
      'decision':'DOUBLE_SSL_ABSORPTION_SEEDS_READY__INDEPENDENT_ORACLE_NEXT' if support and all(r['semantic_order_valid'] for r in rows) else 'DOUBLE_SSL_ABSORPTION_PRE_OUTCOME_GATE_FAIL__NO_REPLAY',
      'artifacts':{'out_dir':str(OUT),'seeds':str(seed_file),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2); (OUT/'v477_report.json').write_text(text); LATEST.write_text(text); print(text)

if __name__=='__main__': main()
