#!/usr/bin/env python3
"""V406 no-write availability gate for strict-prior-date northbound holdings.

Each frozen V381 identity queries its own preceding 30 calendar days only.
HOLD_DATE must be strictly before completed hold_time. Empty history is a valid
zero feature; HTTP/data failures are not. No outcomes are read.
"""
from __future__ import annotations
import csv, json, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
import requests

ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'
V381=AUD/'v381_true_mtf_raw_daily_poi_m60_replay_latest.json'
OUT=AUD/f'v406_pit_northbound_holdings_availability_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST=AUD/'v406_pit_northbound_holdings_availability_latest.json'
URL='https://datacenter-web.eastmoney.com/api/data/v1/get'
HEADERS={'User-Agent':'Mozilla/5.0','Referer':'https://data.eastmoney.com/'}


def fetch(target):
    symbol, hold_time=target; code, market=symbol[:6], ('001' if symbol.endswith('.SH') else '003')
    cutoff=hold_time[:10]; start=(datetime.strptime(cutoff,'%Y-%m-%d')-timedelta(days=30)).date().isoformat()
    params={'reportName':'RPT_MUTUAL_HOLD_DET','columns':'SECURITY_CODE,HOLD_DATE,HOLD_NUM,HOLD_SHARES_RATIO,HOLD_MARKET_CAP,HOLD_MARKET_CAPONE,HOLD_MARKET_CAPFIVE',
            'filter':f'(SECURITY_CODE="{code}")(MARKET_CODE="{market}")(HOLD_DATE>=\'{start}\')(HOLD_DATE<=\'{cutoff}\')',
            'pageNumber':'1','pageSize':'500','sortColumns':'HOLD_DATE','sortTypes':'-1','source':'WEB','client':'WEB'}
    err=''
    for attempt in range(3):
        try:
            r=requests.get(URL,params=params,headers=HEADERS,timeout=40)
            r.raise_for_status(); result=r.json().get('result')
            if result is None: raise RuntimeError('NULL_RESULT')
            rows=result.get('data') or []
            # The 30d response should fit one page; never silently truncate.
            if int(result.get('pages') or 1)>1: raise RuntimeError(f'MULTIPAGE:{result.get("pages")}')
            prior=[x for x in rows if str(x.get('HOLD_DATE') or '')[:10] < cutoff]
            latest=prior[0] if prior else {}
            return {'symbol':symbol,'hold_time':hold_time,'feature_cutoff':hold_time,'lookback_start':start,
                    'northbound_prior_records':len(prior),'northbound_latest_prior_date':str(latest.get('HOLD_DATE') or '')[:10],
                    'northbound_latest_hold_num':float(latest.get('HOLD_NUM') or 0),'northbound_latest_hold_ratio':float(latest.get('HOLD_SHARES_RATIO') or 0),
                    'northbound_latest_change_1d':float(latest.get('HOLD_MARKET_CAPONE') or 0),'query_error':''}
        except Exception as exc:
            err=f'{type(exc).__name__}:{exc}'; time.sleep(0.4*(attempt+1))
    return {'symbol':symbol,'hold_time':hold_time,'feature_cutoff':hold_time,'lookback_start':start,'northbound_prior_records':0,
            'northbound_latest_prior_date':'','northbound_latest_hold_num':0,'northbound_latest_hold_ratio':0,'northbound_latest_change_1d':0,'query_error':err}


def main():
    OUT.mkdir(parents=True,exist_ok=True); report=json.loads(V381.read_text())
    with Path(report['artifacts']['trades']).open(newline='') as f: targets=sorted({(r['symbol'],r['hold_time']) for r in csv.DictReader(f)})
    rows=[]
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures=[pool.submit(fetch,t) for t in targets]
        for n,future in enumerate(as_completed(futures),1):
            rows.append(future.result())
            if n%250==0: print(f'progress={n}/{len(targets)}',flush=True)
    rows.sort(key=lambda x:(x['symbol'],x['hold_time']))
    failed=[x for x in rows if x['query_error']]
    feature=OUT/'v406_northbound_availability_features.csv'
    with feature.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    gate={'target_rows':len(targets),'feature_rows':len(rows),'query_failures':len(failed),'all_targets_accounted':len(rows)==len(targets),
          'all_feature_cutoffs_equal_hold_time':all(x['feature_cutoff']==x['hold_time'] for x in rows),
          'all_hold_dates_strictly_before_cutoff':all(not x['northbound_latest_prior_date'] or x['northbound_latest_prior_date']<x['hold_time'][:10] for x in rows),
          'outcome_fields_read_or_emitted':False}
    passed=all((not gate['query_failures'],gate['all_targets_accounted'],gate['all_feature_cutoffs_equal_hold_time'],gate['all_hold_dates_strictly_before_cutoff'],not gate['outcome_fields_read_or_emitted']))
    result={'version':'V406_PIT_NORTHBOUND_HOLDINGS_AVAILABILITY_GATE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),
            'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
            'contract':'Eastmoney northbound holdings with HOLD_DATE strictly before completed V381 hold_time; no same-date use','gate':gate,
            'decision':'PIT_NORTHBOUND_AVAILABILITY_PASS__OUTCOME_BLIND_REPLAY_ALLOWED' if passed else 'PIT_NORTHBOUND_AVAILABILITY_FAIL__STOP',
            'artifacts':{'features':str(feature),'latest':str(LATEST)},'failure_samples':failed[:20]}
    text=json.dumps(result,ensure_ascii=False,indent=2);(OUT/'v406_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__': main()
