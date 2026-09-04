#!/usr/bin/env python3
"""V481 outcome-blind two-sided liquidity-purge bullish reversal generator.

Frozen ontology: a fully visible 3L/3R range high and low -> BSL wick raid and
close-back -> 2..10 bars later SSL wick raid of the same range and close-back,
without an intervening close beyond either raid floor/ceiling -> close above the
SSL-raid candle high within 3 bars -> next-session eligibility.
"""
from __future__ import annotations
import csv, json, math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
OUT=AUD/f"v481_two_sided_liquidity_purge_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST=AUD/'v481_two_sided_liquidity_purge_latest.json'; YEARS=('2023','2024','2025','2026')


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


def pivots(bars, field, high):
    cmp=(lambda a,b:a>b) if high else (lambda a,b:a<b)
    return [{'idx':i,'confirm_idx':i+3,'price':bars[i][field]}
            for i in range(3,len(bars)-3)
            if all(cmp(bars[i][field],bars[j][field]) for j in range(i-3,i+4) if j!=i)]


def generate(sym,bars):
    highs=pivots(bars,'h',True); lows=pivots(bars,'l',False); rows=[]; rejects=Counter()
    for up in range(7,len(bars)-6):
        hrefs=[x for x in highs if x['confirm_idx']<up and up-x['idx']<=60
               and bars[up]['h']>x['price']*1.003 and bars[up]['c']<x['price']]
        if not hrefs: continue
        hi=max(hrefs,key=lambda x:x['idx'])
        lrefs=[x for x in lows if x['confirm_idx']<up and up-x['idx']<=60 and x['price']<hi['price']]
        if not lrefs: rejects['NO_VISIBLE_RANGE_LOW']+=1; continue
        lo=max(lrefs,key=lambda x:x['idx'])
        for down in range(up+2,min(len(bars)-4,up+11)):
            if any(bars[j]['c']>bars[up]['h'] for j in range(up+1,down)):
                rejects['BSL_RAID_CEILING_BROKEN']+=1; break
            if any(bars[j]['c']<lo['price'] for j in range(up+1,down)):
                rejects['SSL_CLOSED_THROUGH_BEFORE_RAID']+=1; break
            if not (bars[down]['l']<lo['price']*.997 and bars[down]['c']>lo['price']):
                continue
            confirm=next((j for j in range(down+1,min(len(bars),down+4))
                          if bars[j]['c']>bars[down]['h']),None)
            if confirm is None:
                rejects['NO_BULL_REVERSAL_ABOVE_SSL_RAID_HIGH_3B']+=1; break
            eligible=confirm+1
            if eligible>=len(bars): rejects['ENTRY_RIGHT_EDGE']+=1; break
            order=max(hi['confirm_idx'],lo['confirm_idx'])<up<down<confirm<eligible
            rows.append({'symbol':sym,'ontology':'BSL_THEN_SSL_TWO_SIDED_LIQUIDITY_PURGE_REVERSAL',
              'range_high_idx':hi['idx'],'range_high_confirm_idx':hi['confirm_idx'],'range_high':round(hi['price'],6),
              'range_low_idx':lo['idx'],'range_low_confirm_idx':lo['confirm_idx'],'range_low':round(lo['price'],6),
              'bsl_raid_idx':up,'bsl_raid_date':bars[up]['t'],'bsl_raid_high':round(bars[up]['h'],6),
              'ssl_raid_idx':down,'ssl_raid_date':bars[down]['t'],'ssl_raid_low':round(bars[down]['l'],6),'ssl_raid_high':round(bars[down]['h'],6),
              'reversal_confirm_idx':confirm,'reversal_confirm_date':bars[confirm]['t'],
              'eligible_entry_idx':eligible,'eligible_entry_date':bars[eligible]['t'],
              'structural_sl_ref':round(bars[down]['l'],6),'structural_target_ref':round(bars[up]['h'],6),
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
        if old is None or row['ssl_raid_idx']<old['ssl_raid_idx']: dedup[key]=row
    rows=list(dedup.values()); yearly=Counter(r['eligible_entry_date'][:4] for r in rows)
    support=len(rows)>=300 and all(yearly.get(y,0)>=40 for y in YEARS)
    seed_file=OUT/'v481_semantic_seeds.csv'; fields=list(rows[0]) if rows else ['symbol','ontology']
    with seed_file.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(rows)
    result={'version':'V481_TWO_SIDED_LIQUIDITY_PURGE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),
      'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'frozen_contract':'visible 3L/3R range high+low -> >=0.3% BSL wick raid/close-back -> 2..10 bars later >=0.3% SSL wick raid/close-back with no intervening close beyond raid ceiling/range low -> close above SSL-raid high within 3 bars -> next-open eligibility',
      'distinct_information':'Two-sided stop clearing in a fixed visible range. Unlike SSL-only Turtle Soup/double-SSL it first consumes BSL; unlike R4 balance-breaker it requires both opposite-side raids and no breaker/OB retest.',
      'symbols_scanned':scanned,'raw_seed_count':len(raw),'seed_count':len(rows),'yearly_seed_count':dict(sorted(yearly.items())),
      'rejection_counts':dict(rejects),'support_gate_pass':support,
      'invariants':{'semantic_order_failures':sum(not r['semantic_order_valid'] for r in rows),'duplicate_symbol_entry':len(rows)-len(set((r['symbol'],r['eligible_entry_date']) for r in rows)),'no_outcome_fields':all(r['no_outcome_fields'] for r in rows),'all_nontradable':all(not r['tradable'] and not r['buy_enabled'] for r in rows)},
      'decision':'TWO_SIDED_PURGE_SEEDS_READY__INDEPENDENT_ORACLE_NEXT' if support and all(r['semantic_order_valid'] for r in rows) else 'TWO_SIDED_PURGE_PRE_OUTCOME_GATE_FAIL__NO_REPLAY',
      'artifacts':{'out_dir':str(OUT),'seeds':str(seed_file),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2); (OUT/'v481_report.json').write_text(text); LATEST.write_text(text); print(text)

if __name__=='__main__': main()
