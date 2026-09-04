#!/usr/bin/env python3
"""V485 outcome-blind external BSL acceptance/retest continuation generator.

Distinct ontology: confirmed external BSL -> close acceptance above it -> first
retest holds the broken BSL -> re-expansion above retest high -> next open.
The target is the nearest higher BSL already visible before acceptance.
"""
from __future__ import annotations
import csv, json, math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
OUT=AUD/f"v485_bsl_acceptance_retest_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST=AUD/'v485_bsl_acceptance_retest_latest.json'; YEARS=('2023','2024','2025','2026')


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


def highs(bars):
    return [{'idx':i,'confirm_idx':i+3,'price':bars[i]['h']}
            for i in range(3,len(bars)-3)
            if bars[i]['h']>max(bars[j]['h'] for j in range(i-3,i+4) if j!=i)]


def generate(sym,bars):
    piv=highs(bars); rows=[]; rejects=Counter()
    for accept in range(7,len(bars)-6):
        visible=[x for x in piv if x['confirm_idx']<accept and accept-x['idx']<=60]
        broken=[x for x in visible if bars[accept]['c']>x['price']*1.003]
        if not broken: continue
        level=max(broken,key=lambda x:x['idx'])
        higher=sorted((x for x in visible if x['price']>level['price']*1.003),key=lambda x:x['price'])
        if not higher: rejects['NO_VISIBLE_HIGHER_BSL_TARGET']+=1; continue
        target=higher[0]
        if bars[accept]['c']>=target['price']:
            rejects['TARGET_ALREADY_CONSUMED_AT_ACCEPTANCE']+=1; continue
        retest=None
        for i in range(accept+2,min(len(bars)-4,accept+11)):
            if bars[i]['c']<level['price']:
                rejects['BROKEN_BSL_FAILED_BEFORE_RETEST']+=1; break
            if bars[i]['l']<=level['price']*1.003 and bars[i]['c']>level['price']:
                retest=i; break
        if retest is None: continue
        confirm=next((i for i in range(retest+1,min(len(bars),retest+4))
                      if bars[i]['c']>bars[retest]['h']),None)
        if confirm is None:
            rejects['NO_REEXPANSION_ABOVE_RETEST_HIGH_3B']+=1; continue
        eligible=confirm+1
        if eligible>=len(bars): rejects['ENTRY_RIGHT_EDGE']+=1; continue
        order=max(level['confirm_idx'],target['confirm_idx'])<accept<retest<confirm<eligible
        rows.append({'symbol':sym,'ontology':'EXTERNAL_BSL_ACCEPTANCE_RETEST_CONTINUATION',
          'broken_bsl_idx':level['idx'],'broken_bsl_confirm_idx':level['confirm_idx'],'broken_bsl':round(level['price'],6),
          'target_bsl_idx':target['idx'],'target_bsl_confirm_idx':target['confirm_idx'],'target_bsl':round(target['price'],6),
          'accept_idx':accept,'accept_date':bars[accept]['t'],'accept_close':round(bars[accept]['c'],6),
          'retest_idx':retest,'retest_date':bars[retest]['t'],'retest_low':round(bars[retest]['l'],6),'retest_high':round(bars[retest]['h'],6),
          'reexpand_idx':confirm,'reexpand_date':bars[confirm]['t'],'eligible_entry_idx':eligible,'eligible_entry_date':bars[eligible]['t'],
          'structural_sl_ref':round(bars[retest]['l'],6),'structural_target_ref':round(target['price'],6),
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
        if old is None or row['retest_idx']<old['retest_idx']: dedup[key]=row
    rows=list(dedup.values()); yearly=Counter(r['eligible_entry_date'][:4] for r in rows)
    support=len(rows)>=300 and all(yearly.get(y,0)>=40 for y in YEARS)
    seed_file=OUT/'v485_semantic_seeds.csv'; fields=list(rows[0]) if rows else ['symbol','ontology']
    with seed_file.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(rows)
    result={'version':'V485_BSL_ACCEPTANCE_RETEST_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),
      'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'frozen_contract':'visible external 3L/3R BSL -> close acceptance >=0.3% above -> 2..10 bars first retest wick<=level*1.003 and close holds above -> close above retest high within 3 bars -> next-open eligibility; target=nearest higher BSL visible before acceptance',
      'distinct_information':'Liquidity-run acceptance at a broken BSL flip level. Unlike C1 it retests the broken liquidity level rather than an OB; unlike Turtle Soup it requires close acceptance, not close-back rejection; unlike Target-First DOL it requires acceptance-retest-reexpansion before entry.',
      'symbols_scanned':scanned,'raw_seed_count':len(raw),'seed_count':len(rows),'yearly_seed_count':dict(sorted(yearly.items())),
      'rejection_counts':dict(rejects),'support_gate_pass':support,
      'invariants':{'semantic_order_failures':sum(not r['semantic_order_valid'] for r in rows),'duplicate_symbol_entry':len(rows)-len(set((r['symbol'],r['eligible_entry_date']) for r in rows)),'no_outcome_fields':all(r['no_outcome_fields'] for r in rows),'all_nontradable':all(not r['tradable'] and not r['buy_enabled'] for r in rows)},
      'decision':'BSL_ACCEPTANCE_SEEDS_READY__INDEPENDENT_ORACLE_NEXT' if support and all(r['semantic_order_valid'] for r in rows) else 'BSL_ACCEPTANCE_PRE_OUTCOME_GATE_FAIL__NO_REPLAY',
      'artifacts':{'out_dir':str(OUT),'seeds':str(seed_file),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2); (OUT/'v485_report.json').write_text(text); LATEST.write_text(text); print(text)

if __name__=='__main__': main()
