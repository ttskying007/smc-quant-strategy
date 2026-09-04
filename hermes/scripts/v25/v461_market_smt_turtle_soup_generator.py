#!/usr/bin/env python3
"""V461 no-outcome market-SMT Turtle-Soup generator.

Frozen ontology:
- source stock has an independently verified Turtle-Soup SSL reversal;
- on the stock raid date, a same-source equal-weight market composite has two
  already-confirmed 3L/3R swing lows forming a higher low;
- the composite does not raid that protected higher low on the stock raid date;
- stock reversal confirmation and next-open eligibility remain unchanged.

The composite is built causally from geometric-mean OHLC relatives versus each
stock's preceding close. No entry price, exit, PnL, or outcome is read.
"""
from __future__ import annotations
import csv, json, math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
SOURCE=AUD/'v454_turtle_soup_independent_oracle_latest.json'
OUT=AUD/f"v461_market_smt_turtle_soup_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST=AUD/'v461_market_smt_turtle_soup_latest.json'
YEARS=('2023','2024','2025','2026'); MIN_COMPONENTS=1000


def f(x):
    try:
        v=float(x); return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError): return 0.0


def ds(x): return ''.join(c for c in str(x or '') if c.isdigit())[:8]


def load(path):
    try: raw=json.loads(path.read_text())
    except (OSError,json.JSONDecodeError): return []
    out=[]
    for b in raw:
        r={k:f(b.get(k)) for k in ('o','h','l','c')}; d=ds(b.get('t') or b.get('date'))
        if d and all(r.values()): r['t']=d; out.append(r)
    return sorted(out,key=lambda r:r['t'])


def market_composite():
    sums=defaultdict(lambda:[0.0,0.0,0.0,0.0,0])
    scanned=0
    for n,path in enumerate(sorted(KDIR.glob('*_daily_750.json')),1):
        bars=load(path)
        if len(bars)<80: continue
        scanned+=1
        for prev,b in zip(bars,bars[1:]):
            pc=prev['c']
            ratios=[b[k]/pc for k in ('o','h','l','c')]
            if pc<=0 or any(x<=0 or not math.isfinite(x) for x in ratios): continue
            row=sums[b['t']]
            for j,x in enumerate(ratios): row[j]+=math.log(x)
            row[4]+=1
        if n%500==0: print(json.dumps({'composite_files':n}),flush=True)
    level=100.0; rows=[]
    for date in sorted(sums):
        row=sums[date]; count=row[4]
        if count<MIN_COMPONENTS: continue
        rel=[math.exp(row[j]/count) for j in range(4)]
        o,h,l,c=(level*x for x in rel)
        h=max(h,o,c); l=min(l,o,c)
        rows.append({'t':date,'o':o,'h':h,'l':l,'c':c,'components':count})
        level=c
    return rows,scanned


def confirmed_lows(bars):
    return [{'idx':i,'confirm_idx':i+3,'price':bars[i]['l']}
            for i in range(3,len(bars)-3)
            if all(bars[j]['l']>bars[i]['l'] for j in range(i-3,i+4) if j!=i)]


def smt_context(market,lows,date):
    by_date={b['t']:i for i,b in enumerate(market)}
    raid=by_date.get(date)
    if raid is None: return None,'MARKET_DATE_MISSING'
    visible=[x for x in lows if x['confirm_idx']<raid]
    if len(visible)<2: return None,'MARKET_TWO_CONFIRMED_LOWS_MISSING'
    previous,latest=visible[-2],visible[-1]
    if latest['price']<=previous['price']: return None,'MARKET_NOT_HIGHER_LOW'
    if market[raid]['l']<latest['price']*.997: return None,'MARKET_PROTECTED_LOW_RAIDED'
    return {'market_raid_idx':raid,'market_date':date,'market_prev_low_idx':previous['idx'],
            'market_prev_low_date':market[previous['idx']]['t'],
            'market_prev_low_confirm_idx':previous['confirm_idx'],
            'market_prev_low_confirm_date':market[previous['confirm_idx']]['t'],
            'market_prev_low':previous['price'],
            'market_protected_low_idx':latest['idx'],'market_protected_low_confirm_idx':latest['confirm_idx'],
            'market_protected_low_date':market[latest['idx']]['t'],
            'market_protected_low_confirm_date':market[latest['confirm_idx']]['t'],
            'market_protected_low':latest['price'],'market_raid_low':market[raid]['l'],
            'market_components':market[raid]['components']},'PASS'


def main():
    source=json.loads(SOURCE.read_text())
    if source.get('decision')!='INDEPENDENT_ORACLE_PASS__FROZEN_T1_REPLAY_ALLOWED':
        raise RuntimeError('V454 semantic oracle is not passed')
    with Path(source['artifacts']['passed_seeds']).open(newline='') as h: seeds=list(csv.DictReader(h))
    allowed_audit_fields={'no_outcome_fields'}
    forbidden=[c for c in (seeds[0] if seeds else {})
               if c not in allowed_audit_fields and any(x in c.lower() for x in ('pnl','exit','mfe','mae','winner','outcome'))]
    if forbidden: raise RuntimeError(f'forbidden source fields: {forbidden}')
    OUT.mkdir(parents=True,exist_ok=True)
    market,scanned=market_composite(); lows=confirmed_lows(market); counts=Counter(); rows=[]
    for seed in seeds:
        ctx,status=smt_context(market,lows,seed['raid_date']); counts[status]+=1
        if ctx is None: continue
        row={**seed,'ontology':'MARKET_SMT_TURTLE_SOUP_SSL_REVERSAL',
             **{k:(round(v,8) if isinstance(v,float) else v) for k,v in ctx.items()},
             'smt_semantic_order_valid':(
                 ctx['market_prev_low_confirm_date'] < ctx['market_protected_low_date']
                 < ctx['market_protected_low_confirm_date'] < seed['raid_date']
                 < seed['reversal_confirm_date'] < seed['eligible_entry_date']),
             'tradable':'false','buy_enabled':'false','no_outcome_fields':'true'}
        rows.append(row)
    yearly=Counter(r['eligible_entry_date'][:4] for r in rows); support=len(rows)>=300 and all(yearly.get(y,0)>=40 for y in YEARS)
    fields=list(rows[0]) if rows else ['symbol','ontology']; out_csv=OUT/'v461_market_smt_seeds.csv'
    with out_csv.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(rows)
    report={'version':'V461_MARKET_SMT_TURTLE_SOUP_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),
      'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'frozen_contract':'verified stock Turtle-Soup SSL raid -> same-day equal-weight market composite protects a previously confirmed higher swing low -> stock closes above raid high within 3 bars -> next-open eligibility',
      'distinct_information':'Cross-security SMT liquidity divergence against a causal same-source market composite; not a stock-only threshold, POI, stop, target, or hold variant.',
      'composite_contract':'geometric mean of all available stock OHLC relatives versus prior close; minimum 1000 components/date; 3L/3R confirmed lows only',
      'source_seed_count':len(seeds),'symbols_in_composite':scanned,'market_dates':len(market),'market_confirmed_lows':len(lows),
      'seed_count':len(rows),'yearly_seed_count':dict(sorted(yearly.items())),'rejection_counts':dict(counts),
      'support_gate':{'aggregate_n':300,'each_2023_2026_year_n':40,'pass':support},
      'invariants':{'source_oracle_pass':True,'forbidden_source_headers':forbidden,
        'semantic_order_failures':sum(not r['smt_semantic_order_valid'] for r in rows),
        'duplicate_symbol_entry':len(rows)-len(set((r['symbol'],r['eligible_entry_date']) for r in rows)),
        'all_nontradable':all(r['tradable']=='false' and r['buy_enabled']=='false' for r in rows),
        'no_outcome_fields':all(r['no_outcome_fields']=='true' for r in rows)},
      'decision':('MARKET_SMT_SEEDS_READY__INDEPENDENT_ORACLE_NEXT'
                  if support and not any(not r['smt_semantic_order_valid'] for r in rows)
                  else 'MARKET_SMT_PRE_OUTCOME_GATE_FAIL__NO_REPLAY'),
      'artifacts':{'out_dir':str(OUT),'seeds':str(out_csv),'latest':str(LATEST)}}
    text=json.dumps(report,ensure_ascii=False,indent=2); (OUT/'v461_report.json').write_text(text); LATEST.write_text(text); print(text)


if __name__=='__main__': main()
