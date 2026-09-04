#!/usr/bin/env python3
"""V453 no-outcome bullish Turtle-Soup liquidity-reversal generator.

Frozen ontology: most recent visible 3L/3R swing low -> wick raid >=0.3% with
close back above the low -> within three bars a close above the raid candle high
-> next-session eligibility. No POI, entry, exit, or outcome fields are opened.
"""
from __future__ import annotations
import csv, json, math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
OUT=AUD/f"v453_turtle_soup_ssl_reversal_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST=AUD/'v453_turtle_soup_ssl_reversal_latest.json'


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
    return sorted(rows,key=lambda r:r['t'])


def symbol(path):
    code,ex=path.name.removesuffix('_daily_750.json').split('_'); return f'{code}.{ex}'


def confirmed_lows(bars):
    return [{'idx':i,'confirm_idx':i+3,'price':bars[i]['l']}
            for i in range(3,len(bars)-3)
            if all(bars[j]['l']>bars[i]['l'] for j in range(i-3,i+4) if j!=i)]


def generate(sym,bars):
    lows=confirmed_lows(bars); rows=[]; rejects=Counter()
    for raid in range(7,len(bars)-4):
        refs=[x for x in lows if x['confirm_idx']<raid and raid-x['idx']<=60
              and bars[raid]['l']<x['price']*.997 and bars[raid]['c']>x['price']]
        if not refs: continue
        ref=max(refs,key=lambda x:x['idx'])
        confirmation=None
        for idx in range(raid+1,min(len(bars),raid+4)):
            if bars[idx]['c']>bars[raid]['h']:
                confirmation=idx; break
        if confirmation is None:
            rejects['NO_CLOSE_ABOVE_RAID_HIGH_WITHIN_3B']+=1; continue
        eligible=confirmation+1
        if eligible>=len(bars): rejects['ENTRY_RIGHT_EDGE']+=1; continue
        rows.append({'symbol':sym,'ontology':'TURTLE_SOUP_SSL_REVERSAL',
          'ssl_idx':ref['idx'],'ssl_confirm_idx':ref['confirm_idx'],'ssl_price':round(ref['price'],6),
          'raid_idx':raid,'raid_date':bars[raid]['t'],'raid_low':round(bars[raid]['l'],6),'raid_high':round(bars[raid]['h'],6),
          'reversal_confirm_idx':confirmation,'reversal_confirm_date':bars[confirmation]['t'],
          'eligible_entry_idx':eligible,'eligible_entry_date':bars[eligible]['t'],
          'structural_sl_ref':round(bars[raid]['l'],6),
          'semantic_order_valid':ref['confirm_idx']<raid<confirmation<eligible,
          'tradable':False,'buy_enabled':False,'no_outcome_fields':True})
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
        key=(row['symbol'],row['eligible_entry_date'])
        old=dedup.get(key)
        if old is None or row['raid_idx']<old['raid_idx']: dedup[key]=row
    rows=list(dedup.values()); yearly=Counter(r['eligible_entry_date'][:4] for r in rows)
    fields=list(rows[0]) if rows else ['symbol','ontology']; seed_file=OUT/'v453_semantic_seeds.csv'
    with seed_file.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(rows)
    support=len(rows)>=300 and all(yearly.get(y,0)>=40 for y in ('2023','2024','2025','2026'))
    result={'version':'V453_TURTLE_SOUP_SSL_REVERSAL_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),
      'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'frozen_contract':'most-recent confirmed 3L/3R SSL -> >=0.3% wick raid and close-back -> close above raid candle high within 3 bars -> next-open eligibility',
      'distinct_information':'Liquidity-failure auction reversal; no CHOCH, OB, FVG, BPR, POI, threshold search, or exit variant.',
      'symbols_scanned':scanned,'raw_seed_count':len(raw),'seed_count':len(rows),'yearly_seed_count':dict(sorted(yearly.items())),
      'rejection_counts':dict(rejects),'semantic_order_failures':sum(not r['semantic_order_valid'] for r in rows),
      'duplicate_symbol_entry':len(rows)-len(set((r['symbol'],r['eligible_entry_date']) for r in rows)),
      'support_gate_pass':support,'invariants':{'no_entries_created':True,'no_outcome_fields':all(r['no_outcome_fields'] for r in rows),'all_nontradable':all(not r['tradable'] and not r['buy_enabled'] for r in rows)},
      'decision':'TURTLE_SOUP_SEEDS_READY__INDEPENDENT_ORACLE_NEXT' if support else 'TURTLE_SOUP_SUPPORT_FAIL__NO_REPLAY',
      'artifacts':{'out_dir':str(OUT),'seeds':str(seed_file),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2); (OUT/'v453_report.json').write_text(text); LATEST.write_text(text); print(text)

if __name__=='__main__': main()
