#!/usr/bin/env python3
"""V469 no-outcome industry-lead -> stock-lag SSL transmission generator.

Frozen ontology:
1. ex-stock industry composite raids a previously confirmed 3L/3R SSL and
   closes back above it;
2. within three sessions the industry closes above the raid-bar high;
3. during the following ten sessions, while industry closes stay above the
   swept SSL, the stock prints an independently verified Turtle-Soup SSL raid;
4. stock reversal confirmation makes next-session entry eligible.

No outcome, entry price, exit, PnL, MFE, or MAE field is read.
"""
from __future__ import annotations
import csv, importlib.util, json
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'
SOURCE=AUD/'v454_turtle_soup_independent_oracle_latest.json'
OUT=AUD/f"v469_industry_lead_stock_lag_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST=AUD/'v469_industry_lead_stock_lag_latest.json'
YEARS=('2023','2024','2025','2026'); MAX_LAG=10

spec=importlib.util.spec_from_file_location('v465',ROOT/'scripts/v25/v465_industry_smt_turtle_soup_generator.py')
v465=importlib.util.module_from_spec(spec); spec.loader.exec_module(v465)


def industry_events(bars):
    lows=v465.lows(bars); events=[]
    for low_idx,confirm_idx,level in lows:
        for raid in range(confirm_idx+1,len(bars)-1):
            b=bars[raid]
            if b['l'] < level*.997 and b['c'] > level:
                reversal=None
                for j in range(raid+1,min(len(bars),raid+4)):
                    if bars[j]['c'] > b['h']:
                        reversal=j; break
                if reversal is not None:
                    events.append({'ssl_idx':low_idx,'ssl_confirm_idx':confirm_idx,'ssl_price':level,
                                   'raid_idx':raid,'raid_date':b['t'],'raid_low':b['l'],'raid_high':b['h'],
                                   'confirm_idx':reversal,'confirm_date':bars[reversal]['t']})
                break
    return events


def lead_context(bars,events,stock_raid_date):
    pos={b['t']:i for i,b in enumerate(bars)}; stock_i=pos.get(stock_raid_date)
    if stock_i is None:return None,'INDUSTRY_DATE_MISSING'
    eligible=[e for e in events if e['confirm_idx'] < stock_i and stock_i-e['confirm_idx'] <= MAX_LAG]
    if not eligible:return None,'NO_RECENT_CONFIRMED_INDUSTRY_SSL_REVERSAL'
    event=max(eligible,key=lambda e:e['confirm_idx'])
    if any(bars[j]['c'] < event['ssl_price'] for j in range(event['confirm_idx']+1,stock_i+1)):
        return None,'INDUSTRY_REVERSAL_INVALIDATED_BEFORE_STOCK_RAID'
    return {f'industry_{k}':v for k,v in event.items()} | {
        'industry_stock_raid_idx':stock_i,'industry_stock_raid_date':stock_raid_date,
        'industry_lead_lag_sessions':stock_i-event['confirm_idx'],
        'industry_components':bars[stock_i]['components']},'PASS'


def main():
    src=json.loads(SOURCE.read_text())
    if src.get('decision')!='INDEPENDENT_ORACLE_PASS__FROZEN_T1_REPLAY_ALLOWED':raise RuntimeError('V454 gate failed')
    with Path(src['artifacts']['passed_seeds']).open(newline='') as h:seeds=list(csv.DictReader(h))
    forbidden=[c for c in (seeds[0] if seeds else {}) if c!='no_outcome_fields' and any(x in c.lower() for x in ('pnl','exit','mfe','mae','winner','outcome','entry_price'))]
    if forbidden:raise RuntimeError(f'forbidden source fields: {forbidden}')
    OUT.mkdir(parents=True,exist_ok=True); mapping,sums,own,covered=v465.build_source(); grouped=defaultdict(list)
    for seed in seeds:grouped[seed['symbol']].append(seed)
    rows=[];counts=Counter();event_count=0;unmapped=0
    for n,(sym,items) in enumerate(grouped.items(),1):
        ind=mapping.get(sym)
        if not ind:unmapped+=len(items);continue
        bars=v465.ex_stock_index(sym,ind,sums,own);events=industry_events(bars);event_count+=len(events)
        for seed in items:
            ctx,status=lead_context(bars,events,seed['raid_date']);counts[status]+=1
            if ctx is None:continue
            row={**seed,'ontology':'INDUSTRY_LEAD_STOCK_LAG_SSL_TRANSMISSION','industry':ind,
                 **{k:(round(v,8) if isinstance(v,float) else v) for k,v in ctx.items()},
                 'lead_semantic_order_valid':bars[ctx['industry_ssl_confirm_idx']]['t']<ctx['industry_raid_date']<ctx['industry_confirm_date']<seed['raid_date']<seed['reversal_confirm_date']<seed['eligible_entry_date'],
                 'tradable':'false','buy_enabled':'false','no_outcome_fields':'true'}
            rows.append(row)
        if n%500==0:print(json.dumps({'symbols':n,'seeds':len(rows)}),flush=True)
    yearly=Counter(r['eligible_entry_date'][:4] for r in rows);support=len(rows)>=300 and all(yearly.get(y,0)>=40 for y in YEARS)
    duplicates=len(rows)-len(set((r['symbol'],r['eligible_entry_date']) for r in rows));order_fail=sum(not r['lead_semantic_order_valid'] for r in rows)
    outcsv=OUT/'v469_industry_lead_stock_lag_seeds.csv';fields=list(rows[0]) if rows else ['symbol','ontology']
    with outcsv.open('w',newline='') as h:w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(rows)
    report={'version':'V469_INDUSTRY_LEAD_STOCK_LAG_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'frozen_contract':'ex-stock industry SSL raid+close-back -> industry close above raid high within 3 sessions -> stock SSL raid within next 10 sessions while industry holds swept SSL -> stock reversal confirmation -> next-open eligibility',
      'distinct_information':'Cross-security temporal lead-lag transmission; unlike V465 same-day divergence, the industry liquidity reversal must be completed before the stock raid.',
      'source_seed_count':len(seeds),'industry_mapped_symbols':covered,'unmapped_source_seeds':unmapped,'industry_event_count_across_ex_stock_composites':event_count,
      'seed_count':len(rows),'yearly_seed_count':dict(sorted(yearly.items())),'rejection_counts':dict(counts),'support_gate':{'aggregate_n':300,'each_2023_2026_year_n':40,'pass':support},
      'invariants':{'forbidden_source_headers':forbidden,'semantic_order_failures':order_fail,'duplicate_symbol_entry':duplicates,'all_nontradable':all(r['tradable']=='false' and r['buy_enabled']=='false' for r in rows),'no_outcome_fields':all(r['no_outcome_fields']=='true' for r in rows)},
      'decision':'INDUSTRY_LEAD_STOCK_LAG_SEEDS_READY__INDEPENDENT_ORACLE_NEXT' if support and order_fail==0 and duplicates==0 else 'INDUSTRY_LEAD_STOCK_LAG_PRE_OUTCOME_GATE_FAIL__NO_REPLAY',
      'artifacts':{'out_dir':str(OUT),'seeds':str(outcsv),'latest':str(LATEST)}}
    text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v469_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
