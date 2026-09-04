#!/usr/bin/env python3
"""V645 source-only pilot: official raw terms transport for convertible conversion-price documents."""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
CACHE = ROOT / 'kline_cache'
CONTRACT = AUD / 'v645_convertible_bond_conversion_price_terms_source_pilot_contract.json'
OUT = AUD / f'v645_convertible_bond_conversion_price_terms_source_pilot_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v645_convertible_bond_conversion_price_terms_source_pilot_latest.json'
META = 'https://np-anotice-stock.eastmoney.com/api/security/ann'
BODY = 'https://np-cnotice-stock.eastmoney.com/api/content/ann'
YEARS = ('2023', '2024', '2025')
TITLE = re.compile(r'(?:可转债|可转换公司债券|可转换债券).*转股价格|转股价格.*(?:可转债|可转换公司债券|可转换债券)')
DOWN = re.compile(r'(?:向下修正|下修)')
PRICE = re.compile(r'转股价格')
YUAN_PER_SHARE = re.compile(r'\d+(?:\.\d+)?元\s*/\s*股')


def stratum(symbol: str) -> str:
    code = symbol[:6]
    if code.startswith(('4', '8', '9')): return 'BJ'
    if code.startswith('688'): return 'SH_STAR'
    if code.startswith(('600', '601', '603', '605')): return 'SH_MAIN'
    if code.startswith(('300', '301')): return 'SZ_CHINEXT'
    if code.startswith(('000', '001')): return 'SZ_MAIN'
    return 'SZ_OTHER'


def universe() -> list[str]:
    found = set()
    for path in CACHE.glob('*_daily_750.json'):
        token = path.name.removesuffix('_daily_750.json')
        if re.fullmatch(r'\d{6}_(?:SH|SZ|BJ)', token):
            found.add(token.replace('_', '.'))
    return sorted(found)


def sampled_symbols() -> list[str]:
    groups: dict[str, list[str]] = {}
    for symbol in universe(): groups.setdefault(stratum(symbol), []).append(symbol)
    result = []
    for group, rows in sorted(groups.items()):
        ranked = sorted(rows, key=lambda s: hashlib.sha256(('V645|' + s).encode()).hexdigest())
        result.extend(ranked[:max(1, round(500 * len(rows) / sum(map(len, groups.values()))))])
    return sorted(result)


def get_json(session: requests.Session, url: str, params: dict) -> dict:
    last = None
    for attempt in range(3):
        try:
            response = session.get(url, params=params, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            last = exc; time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f'{type(last).__name__}: {last}')


def fetch_candidates(symbol: str) -> dict:
    session = requests.Session(); session.trust_env = False
    out, page = [], 1
    try:
        while True:
            payload = get_json(session, META, {'client_source':'web','page_size':100,'page_index':page,'ann_type':'A','stock_list':symbol[:6],'begin_time':'2023-01-01','end_time':'2025-12-31'})
            if payload.get('success') != 1: raise RuntimeError(f"metadata_success={payload.get('success')}")
            data = payload.get('data') or {}; rows = data.get('list') or []
            for row in rows:
                title = str(row.get('title') or '')
                if TITLE.search(title):
                    out.append({'symbol':symbol,'announcement_id':str(row.get('art_code') or ''),'notice_date':str(row.get('notice_date') or '')[:10],'publication_time':str(row.get('eiTime') or ''),'title':title})
            if page * 100 >= int(data.get('total_hits') or 0) or not rows: break
            page += 1
        return {'symbol':symbol,'ok':True,'candidates':out,'error':''}
    except Exception as exc:
        return {'symbol':symbol,'ok':False,'candidates':[],'error':f'{type(exc).__name__}: {exc}'}


def body_for(candidate: dict) -> dict:
    session = requests.Session(); session.trust_env = False
    try:
        data = (get_json(session, BODY, {'art_code':candidate['announcement_id'],'client_source':'web','page_index':1}).get('data') or {})
        valid_identity = data.get('art_code') == candidate['announcement_id'] and str(data.get('eitime') or '')[:19] == candidate['publication_time'][:19]
        text = str(data.get('notice_content') or '')
        transport = 'inline'
        if not text.strip():
            url = data.get('attach_url_web') or data.get('attach_url')
            if not url: raise RuntimeError('EMPTY_INLINE_NO_OFFICIAL_ATTACHMENT')
            pdf = session.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=60); pdf.raise_for_status()
            if not pdf.content.startswith(b'%PDF'): raise RuntimeError('OFFICIAL_ATTACHMENT_NOT_PDF')
            with tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / 'source.pdf'; target = Path(directory) / 'source.txt'; source.write_bytes(pdf.content)
                subprocess.run(['pdftotext', str(source), str(target)], check=True, timeout=60, capture_output=True)
                text = target.read_text(encoding='utf-8', errors='replace')
            transport = 'official_pdf_attachment'
        normalized = re.sub(r'\s+', '', text)
        return {**candidate, 'payload_art_code':data.get('art_code'),'payload_publication_time':data.get('eitime'),'identity_valid':valid_identity,'text_nonempty':bool(normalized),'transport':transport,'has_downward_revision_phrase':bool(DOWN.search(normalized)),'has_conversion_price_phrase':bool(PRICE.search(normalized)),'has_yuan_per_share_token':bool(YUAN_PER_SHARE.search(normalized)),'content_sha256':hashlib.sha256(text.encode()).hexdigest(),'error':''}
    except Exception as exc:
        return {**candidate,'identity_valid':False,'text_nonempty':False,'transport':'none','has_downward_revision_phrase':False,'has_conversion_price_phrase':False,'has_yuan_per_share_token':False,'content_sha256':'','error':f'{type(exc).__name__}: {exc}'}


def main() -> None:
    contract = json.loads(CONTRACT.read_text())
    assert contract['research_lane'] == 'B_CORPORATE_ACTION_TERMS'
    OUT.mkdir(parents=True, exist_ok=False)
    sample = sampled_symbols(); fetched = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch_candidates, symbol) for symbol in sample]
        for future in as_completed(futures): fetched.append(future.result())
    candidates = sorted({row['announcement_id']: row for batch in fetched for row in batch['candidates'] if row['announcement_id']}.values(), key=lambda r:(r['publication_time'],r['announcement_id']))
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(body_for, candidates))
    years = {year: sum(str(row['notice_date']).startswith(year) for row in rows) for year in YEARS}
    identity_ok = all(row['identity_valid'] and row['text_nonempty'] for row in rows)
    field_ok = [row for row in rows if row['has_downward_revision_phrase'] and row['has_conversion_price_phrase'] and row['has_yuan_per_share_token']]
    report = {'version':'V645_CONVERTIBLE_BOND_CONVERSION_PRICE_TERMS_SOURCE_PILOT_NO_OUTCOME','generated_at':datetime.now().isoformat(timespec='seconds'),'research_only':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'scope':'Source transport and raw-field availability only; no OHLCV values, SMC, seed, trade, outcome, PnL, stop or target was read.','contract':str(CONTRACT),'sample':{'symbols_requested':len(sample),'metadata_fetch_ok':sum(row['ok'] for row in fetched),'metadata_fetch_failures':sum(not row['ok'] for row in fetched),'strata':{key:sum(stratum(s)==key for s in sample) for key in sorted({stratum(s) for s in sample})}},'candidate_transport':{'title_located_documents':len(rows),'by_year':years,'identity_and_text_valid_count':sum(row['identity_valid'] and row['text_nonempty'] for row in rows),'identity_or_text_failures':sum(not (row['identity_valid'] and row['text_nonempty']) for row in rows),'transport_counts':{key:sum(row['transport']==key for row in rows) for key in ('inline','official_pdf_attachment','none')}},'raw_field_availability':{'all_three_terms_count':len(field_ok),'downward_revision_phrase_count':sum(row['has_downward_revision_phrase'] for row in rows),'conversion_price_phrase_count':sum(row['has_conversion_price_phrase'] for row in rows),'yuan_per_share_token_count':sum(row['has_yuan_per_share_token'] for row in rows)},'decision':'PILOT_PASS__FULL_UNIVERSE_SOURCE_COVERAGE_CONTRACT_MAY_BE_PREREGISTERED__NO_SEMANTIC_CATALOG_OR_MARKET_DATA' if rows and identity_ok and field_ok else 'PILOT_FAIL__CLOSE_CONVERTIBLE_BOND_TERMS_TRANSPORT_OBJECT__NO_TERM_INFERENCE_OR_STRATEGY','artifacts':{'dir':str(OUT),'payload_audit':str(OUT/'v645_candidate_payload_audit.csv')}}
    with (OUT/'v645_candidate_payload_audit.csv').open('w',newline='',encoding='utf-8') as handle:
        fields=['symbol','announcement_id','notice_date','publication_time','title','payload_art_code','payload_publication_time','identity_valid','text_nonempty','transport','has_downward_revision_phrase','has_conversion_price_phrase','has_yuan_per_share_token','content_sha256','error']
        writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v645_report.json').write_text(text);LATEST.write_text(text);print(text)

if __name__ == '__main__': main()
