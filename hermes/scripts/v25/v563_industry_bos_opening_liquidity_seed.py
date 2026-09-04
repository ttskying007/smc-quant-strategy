#!/usr/bin/env python3
"""V563 no-outcome seed: industry daily BOS -> constituent opening-liquidity acceptance.

A distinct parent-to-child ontology from V562: the lower-timeframe event does
not use a post-hoc swing or generic M15 FVG.  It uses only an already finished
09:30-10:00 opening range, then requires a sweep of that known opening SSL and
acceptance above its known opening BSL before noon.  The parent industry BOS is
known only after D closes, so execution is strictly D+1 daily open.
"""
from __future__ import annotations
import csv,json
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
import importlib.util

ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'
spec=importlib.util.spec_from_file_location('v562',ROOT/'scripts/v25/v562_industry_bos_m15_ssl_choch_seed.py')
v562=importlib.util.module_from_spec(spec); spec.loader.exec_module(v562)
OUT=AUD/f'v563_industry_bos_opening_liquidity_seed_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST=AUD/'v563_industry_bos_opening_liquidity_seed_latest.json'
YEARS=('2025','2026')


def opening_acceptance(session):
    # Bars 0..1 establish an observable 09:30-10:00 liquidity range.
    if len(session)<9:return None,'M15_SHORT_SESSION'
    opening=session[:2]; ssl=min(x['l'] for x in opening); bsl=max(x['h'] for x in opening)
    # Only morning bars 10:00..11:30 are eligible, so no close from the
    # afternoon/future is used to form the signal.
    raid=next((i for i in range(2,min(8,len(session))) if session[i]['l']<ssl*.999 and session[i]['c']>ssl),None)
    if raid is None:return None,'NO_OPENING_SSL_SWEEP_RECLAIM'
    accept=next((i for i in range(raid+1,min(8,len(session))) if session[i]['c']>bsl*1.001),None)
    if accept is None:return None,'NO_OPENING_BSL_ACCEPTANCE'
    if any(x['c']<ssl for x in session[accept+1:8]):return None,'MORNING_ACCEPTANCE_INVALIDATED'
    return {'m15_open_range_start':opening[0]['t'],'m15_open_range_end':opening[-1]['t'],
            'm15_opening_ssl':round(ssl,8),'m15_opening_bsl':round(bsl,8),
            'm15_opening_raid_time':session[raid]['t'],'m15_opening_raid_low':round(session[raid]['l'],8),
            'm15_opening_accept_time':session[accept]['t']},'PASS'


def main():
    # Only raw Sina OHLCV and the immutable industry classification are read.
    mapping,sums,own,mapped=v562.build_industry_source(); OUT.mkdir(parents=True,exist_ok=False)
    rows=[]; rejects=Counter(); symbols=0
    for path in v562.DAILY.glob('*_daily.json.gz'):
        stem=path.name.replace('_daily.json.gz','').split('_',1)
        if len(stem)!=2:continue
        sym=f'{stem[0]}.{stem[1]}'; ind=mapping.get(sym)
        if not ind:continue
        parents=v562.industry_bos_by_date(v562.ex_stock_industry(sym,ind,sums,own))
        if not parents:continue
        byday=defaultdict(list)
        for b in v562.m15_bars(sym):byday[b['d']].append(b)
        daily=[b['t'] for b in v562.daily_bars(sym)]; next_date={a:b for a,b in zip(daily,daily[1:])}
        for d,parent in parents.items():
            if d[:4] not in YEARS:continue
            event,status=opening_acceptance(byday.get(d,[]));rejects[status]+=1
            entry=next_date.get(d)
            if event is None:continue
            if entry is None:rejects['NO_NEXT_DAILY_SESSION']+=1;continue
            assert parent['industry_anchor_confirm_date']<d
            assert event['m15_open_range_end']<event['m15_opening_raid_time']<event['m15_opening_accept_time']<entry+'000000'
            rows.append({'symbol':sym,'industry':ind,'event_date':d,'eligible_entry_date':entry,
              'ontology':'INDUSTRY_BOS_TO_OPENING_SSL_SWEEP_BSL_ACCEPTANCE','tradable':'false','buy_enabled':'false','no_outcome_fields':'true',**parent,**event})
        symbols+=1
        if symbols%500==0:print(json.dumps({'symbols':symbols,'seeds':len(rows)},ensure_ascii=False),flush=True)
    rows.sort(key=lambda r:(r['eligible_entry_date'],r['symbol'])); unique={(r['symbol'],r['eligible_entry_date']) for r in rows}; years=Counter(r['eligible_entry_date'][:4] for r in rows)
    fields=sorted({k for r in rows for k in r}) if rows else ['symbol','ontology']; seed=OUT/'v563_seeds.csv'
    with seed.open('w',newline='',encoding='utf-8') as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(rows)
    support=len(unique)>=1000 and all(years.get(y,0)>=300 for y in YEARS)
    report={'version':'V563_INDUSTRY_BOS_OPENING_LIQUIDITY_SEED_NO_OUTCOME','generated_at':datetime.now().isoformat(timespec='seconds'),'research_only':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'source_contract':'Sina source-isolated daily/M15 raw cache plus immutable Baostock industry map; 2025-2026 exploratory range; no bar substitution.',
      'frozen_ontology':'ex-stock industry confirmed-swing BOS on D -> constituent 09:30-10:00 range -> morning SSL sweep/reclaim -> morning BSL acceptance -> D+1 daily-open eligible',
      'causality':'The daily industry swing is right-side confirmed before D; the opening range completes before raid; acceptance completes before noon and before D+1. No outcomes/replays are read.',
      'source_mapped_symbols':mapped,'symbols_with_parent_bos_scanned':symbols,'raw_seed_count':len(rows),'unique_symbol_entry_count':len(unique),'yearly_seed_count':dict(sorted(years.items())),
      'support_gate':{'unique_n_min':1000,'each_available_year_n_min':300,'pass':support},
      'invariants':{'no_outcome_files_read':True,'all_nontradable':all(r['tradable']=='false' and r['buy_enabled']=='false' for r in rows),'all_entry_after_acceptance':all(r['m15_opening_accept_time'][:8]<r['eligible_entry_date'] for r in rows),'duplicate_symbol_entry_count':len(rows)-len(unique)},
      'rejection_counts':dict(rejects),'decision':'SEED_GATE_PASS__INDEPENDENT_ORACLE_REQUIRED_NEXT' if support else 'SEED_SUPPORT_INSUFFICIENT__NO_OUTCOMES_OPENED__NO_REPLAY',
      'artifacts':{'out_dir':str(OUT),'seeds':str(seed),'latest':str(LATEST)}}
    text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v563_report.json').write_text(text);LATEST.write_text(text);print(text)

if __name__=='__main__':main()
