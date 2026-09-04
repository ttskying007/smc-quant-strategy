#!/usr/bin/env python3
"""V563 full PIT corporate-event metadata coverage audit; no market data/outcomes."""
from __future__ import annotations

import argparse
import csv
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
MAPPING = AUD / 'v399_pit_shareholder_holdings_feasibility_no_write_20260712_194542' / 'v399_fixed_identity_pit_holder_mapping.csv'
OUT = AUD / f'v563_pit_event_archive_full_coverage_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v563_pit_event_archive_full_coverage_latest.json'
API = 'https://np-anotice-stock.eastmoney.com/api/security/ann'
START, END, WORKERS, PAGES_MAX = '2023-01-01', '2026-07-23', 4, 10
PATTERNS = {
    'BUYBACK': re.compile(r'回购'), 'HOLDER_INCREASE': re.compile(r'增持'),
    'HOLDER_DECREASE': re.compile(r'减持'), 'EARNINGS_PREANNOUNCEMENT': re.compile(r'业绩(?:预告|快报)'),
    'LOCKUP': re.compile(r'(?:限售股|解除限售|解禁)'),
}


def kind_of(title: str) -> str | None:
    for k, rx in PATTERNS.items():
        if rx.search(title): return k
    return None


def fetch(symbol: str) -> dict:
    session, events, total_hits = requests.Session(), [], 0
    for page in range(1, PAGES_MAX + 1):
        payload = None; error = ''
        params = {'client_source':'web','page_size':100,'page_index':page,'ann_type':'A','stock_list':symbol[:6],'begin_time':START,'end_time':END}
        for attempt in range(3):
            try:
                r = session.get(API, params=params, timeout=30, headers={'User-Agent':'Mozilla/5.0'})
                payload = r.json()
                if payload.get('success') != 1: raise ValueError(f"api_success={payload.get('success')}")
                break
            except Exception as exc:
                error=f'{type(exc).__name__}: {exc}'; payload=None; time.sleep(0.75*(attempt+1))
        if payload is None: return {'symbol':symbol,'ok':False,'error':error,'events':[],'total_hits':total_hits,'truncated':False}
        data=payload.get('data') or {}; items=data.get('list') or []; total_hits=int(data.get('total_hits') or 0)
        for item in items:
            title=str(item.get('title') or ''); kind=kind_of(title)
            if kind:
                events.append({'symbol':symbol,'kind':kind,'announcement_id':str(item.get('art_code') or ''),'notice_date':str(item.get('notice_date') or ''),'publication_time':str(item.get('eiTime') or ''),'title':title})
        if page*100 >= total_hits or not items: break
        time.sleep(0.12)
    return {'symbol':symbol,'ok':True,'error':'','events':events,'total_hits':total_hits,'truncated':total_hits>PAGES_MAX*100}


def main() -> None:
    global WORKERS, PAGES_MAX
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=WORKERS)
    ap.add_argument('--pages-max', type=int, default=PAGES_MAX)
    args = ap.parse_args()
    WORKERS = max(args.workers, 1)
    PAGES_MAX = max(args.pages_max, 1)
    OUT.mkdir(parents=True, exist_ok=True)
    symbols=sorted({r['symbol'] for r in csv.DictReader(MAPPING.open(encoding='utf-8-sig')) if r.get('symbol')})
    rows=[]
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        fs=[pool.submit(fetch,s) for s in symbols]
        for n,f in enumerate(as_completed(fs),1):
            rows.append(f.result())
            if n%200==0: print(f'PROGRESS {n}/{len(symbols)}',flush=True)
    rows.sort(key=lambda r:r['symbol'])
    events=[e for r in rows if r['ok'] for e in r['events']]
    for e in events: e['event_year']=e['notice_date'][:4]
    with (OUT/'v563_event_metadata.jsonl').open('w',encoding='utf-8') as f:
        for e in events: f.write(json.dumps(e,ensure_ascii=False)+'\n')
    years=['2023','2024','2025','2026']
    ok=[r for r in rows if r['ok']]
    summary={
      'version':'V563_PIT_EVENT_ARCHIVE_FULL_COVERAGE_NO_OUTCOME','generated_at':datetime.now().isoformat(timespec='seconds'),
      'purpose':'Full canonical-universe PIT event metadata coverage audit before defining any event-to-SMC seed generator.',
      'source_contract':{'provider':'Eastmoney public announcement metadata endpoint','range':[START,END],'workers':WORKERS,'pages_max':PAGES_MAX,'fields_read':['symbol','announcement_id','title','notice_date','publication_time'],'prohibited':['price','volume','SMC seed','trade outcome','holder values'],'same_day_execution_forbidden':True},
      'universe':{'symbols_requested':len(symbols),'http_ok':len(ok),'http_ok_pct':round(100*len(ok)/len(symbols),4) if symbols else 0,'truncated_symbols':sum(r['truncated'] for r in ok)},
      'events':{'classified_count':len(events),'timestamp_complete_count':sum(bool(e['notice_date'] and e['publication_time']) for e in events),'by_kind':{k:sum(e['kind']==k for e in events) for k in PATTERNS},'by_year':{y:sum(e['event_year']==y for e in events) for y in years}},
      'coverage_gate':{'http_ok_pct_min':95.0,'no_truncated_symbol_required':True,'all_classified_events_timestamped_required':True,'pass':False},
      'invariants':{'no_price_or_outcome_fields_read':True,'no_production_write':True,'no_frontend_write':True,'no_watchlist_write':True},
      'artifacts':{'out_dir':str(OUT),'event_metadata':str(OUT/'v563_event_metadata.jsonl'),'latest':str(LATEST)}}
    summary['coverage_gate']['pass']=(summary['universe']['http_ok_pct']>=95 and summary['universe']['truncated_symbols']==0 and summary['events']['timestamp_complete_count']==summary['events']['classified_count'])
    summary['decision']='EVENT_METADATA_FULL_COVERAGE_PASS__FROZEN_ONTOLOGY_DEFINITION_NEXT' if summary['coverage_gate']['pass'] else 'EVENT_METADATA_COVERAGE_FAIL__NO_ONTOLOGY_OR_REPLAY'
    (OUT/'v563_report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    LATEST.write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
