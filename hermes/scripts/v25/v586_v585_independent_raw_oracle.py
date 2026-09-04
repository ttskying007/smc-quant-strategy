#!/usr/bin/env python3
"""Independent raw-data Oracle for V585; never imports its seed generator."""
from __future__ import annotations
import csv, json, math
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); AUDIT=ROOT/'smc_audit'; DAILY=ROOT/'kline_cache'
META=AUDIT/'v563_pit_event_archive_full_coverage_no_outcome_20260724_124935'/'v563_event_metadata.jsonl'
SEED=AUDIT/'v585_insider_reduction_plan_ssl_exhaustion_seed_latest.json'
LATEST=AUDIT/'v586_v585_independent_raw_oracle_latest.json'
OUT=AUDIT/f'v586_v585_independent_raw_oracle_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
YEARS={'2023','2024','2025'}

def d8(x):
    s=''.join(c for c in str(x or '') if c.isdigit()); return s[:8] if len(s)>=8 else ''
def pos(x):
    try:
        y=float(x); return y if math.isfinite(y) and y>0 else None
    except (TypeError,ValueError): return None

def raw_events():
    all_rows=[]
    for line in META.open(encoding='utf-8'):
        try: x=json.loads(line)
        except ValueError: continue
        title=str(x.get('title') or ''); date=d8(x.get('notice_date'))
        if (x.get('kind')=='HOLDER_DECREASE' and date[:4] in YEARS and '减持' in title and any(q in title for q in ('计划','预披露')) and not any(q in title for q in ('实施','完成','进展','时间过半','届满','结果'))):
            all_rows.append((str(x.get('symbol') or ''),date,str(x.get('announcement_id') or '')))
    canonical={}
    for symbol,date,aid in sorted(all_rows): canonical.setdefault((symbol,date),aid)
    return defaultdict(list, {s:[d for (ss,d),_ in canonical.items() if ss==s] for s in {s for s,d in canonical}})

def bars(symbol):
    try: raw=json.loads((DAILY/f'{symbol.replace(".","_")}_daily_750.json').read_text())
    except (OSError,ValueError): return []
    out=[]
    for x in raw if isinstance(raw,list) else []:
        date=d8(x.get('t') or x.get('date')); vals=[pos(x.get(k)) for k in ('o','h','l','c')]
        if len(date)==8 and all(v is not None for v in vals): out.append({'d':date,'o':vals[0],'h':vals[1],'l':vals[2],'c':vals[3]})
    return sorted(out,key=lambda x:x['d'])

def pivots(xs):
    lows=[]; highs=[]
    for i in range(3,len(xs)-3):
        if xs[i]['l']<min(x['l'] for x in xs[i-3:i]) and xs[i]['l']<=min(x['l'] for x in xs[i+1:i+4]): lows.append((i,i+3))
        if xs[i]['h']>max(x['h'] for x in xs[i-3:i]) and xs[i]['h']>=max(x['h'] for x in xs[i+1:i+4]): highs.append((i,i+3))
    return lows,highs

def rebuild(symbol,event_date,xs):
    dates=[x['d'] for x in xs]; start=bisect_right(dates,event_date)
    if start+53>=len(xs): return None
    for sweep in range(start,min(start+30,len(xs))):
        lows,_=pivots(xs[:sweep+1])
        candidates=[p for p in lows if p[1]<sweep and xs[p[0]]['l']>xs[sweep]['l'] and xs[sweep]['c']>xs[p[0]]['l']]
        if not candidates: continue
        for brk in range(sweep+1,min(sweep+11,len(xs))):
            _,highs=pivots(xs[:brk+1])
            if not [p for p in highs if p[1]<brk and xs[p[0]]['h']<xs[brk]['c']]: continue
            bearish=[i for i in range(sweep,brk+1) if xs[i]['c']<xs[i]['o']]
            if not bearish: continue
            poi=bearish[-1]; lo,hi=xs[poi]['l'],xs[poi]['o']
            for reclaim in range(brk+1,min(brk+11,len(xs))):
                if xs[reclaim]['l']<=hi and xs[reclaim]['h']>=lo and xs[reclaim]['c']>=hi and reclaim+1<len(xs): return (symbol,xs[reclaim+1]['d'])
    return None

def main():
    seed=json.loads(SEED.read_text())
    with Path(seed['artifacts']['seeds']).open(encoding='utf-8',newline='') as h: expected={(r['symbol'],r['planned_entry_date']) for r in csv.DictReader(h)}
    actual=set()
    for n,(symbol,dates) in enumerate(sorted(raw_events().items()),1):
        xs=bars(symbol)
        for date in dates:
            row=rebuild(symbol,date,xs)
            if row and row[1][:4] in YEARS: actual.add(row)
        if n%500==0: print(json.dumps({'symbols':n,'identities':len(actual)}),flush=True)
    missing,extra=expected-actual,actual-expected
    OUT.mkdir(parents=True,exist_ok=False); path=OUT/'v586_oracle_identities.csv'
    with path.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=['symbol','planned_entry_date']); w.writeheader(); w.writerows({'symbol':s,'planned_entry_date':d} for s,d in sorted(actual))
    report={'version':'V586_V585_INDEPENDENT_RAW_ORACLE_NO_OUTCOME','generated_at':datetime.now().isoformat(timespec='seconds'),
      'input_contract':'V585 expected identities plus raw PIT reduction-plan metadata and local daily OHLC only; no outcome/trade/PnL/exit/target/stop/replay file read.',
      'independent_rebuild':'Independently rebuilds deduplicated reduction-plan events and the confirmed SSL sweep -> BSL break -> demand POI reclaim lifecycle without importing V585 code.',
      'expected_identities':len(expected),'oracle_identities':len(actual),'missing':len(missing),'extra':len(extra),'identity_match':expected==actual,
      'missing_sample':[{'symbol':s,'planned_entry_date':d} for s,d in sorted(missing)[:20]],'extra_sample':[{'symbol':s,'planned_entry_date':d} for s,d in sorted(extra)[:20]],
      'invariants':{'no_outcome_files_read':True,'production_write':False,'frontend_write':False,'watchlist_write':False},
      'decision':'V586_ORACLE_PASS__ONE_FROZEN_STRICT_T1_REPLAY_AUTHORIZED' if expected==actual else 'V586_ORACLE_FAIL__NO_REPLAY_ALLOWED',
      'artifacts':{'out_dir':str(OUT),'oracle_identities':str(path),'latest':str(LATEST)}}
    text=json.dumps(report,ensure_ascii=False,indent=2); (OUT/'v586_report.json').write_text(text); LATEST.write_text(text); print(text)
if __name__=='__main__': main()
