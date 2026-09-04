#!/usr/bin/env python3
"""V470 independent raw-bar oracle for V469 industry lead-lag seeds."""
from __future__ import annotations
import csv,importlib.util,json,math
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes');AUD=ROOT/'smc_audit';SRC=AUD/'v469_industry_lead_stock_lag_latest.json'
OUT=AUD/f"v470_industry_lead_stock_lag_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}";LATEST=AUD/'v470_industry_lead_stock_lag_oracle_latest.json'
MAX_LAG=10;MIN_PEERS=15
spec=importlib.util.spec_from_file_location('v465',ROOT/'scripts/v25/v465_industry_smt_turtle_soup_generator.py');v465=importlib.util.module_from_spec(spec);spec.loader.exec_module(v465)

def index_without_stock(sym,industry,sums,own):
    level=100.0;out=[];mine=own.get(sym,{})
    for date in sorted(sums.get(industry,{})):
        total=sums[industry][date];n=int(total[4]);vals=[total[j] for j in range(4)]
        if date in mine:
            n-=1
            for j in range(4):vals[j]-=mine[date][j]
        if n<MIN_PEERS:continue
        rel=[math.exp(x/n) for x in vals];o,h,l,c=[level*x for x in rel]
        out.append({'t':date,'o':o,'h':max(h,o,c),'l':min(l,o,c),'c':c,'components':n});level=c
    return out

def pivots(rows):
    ans=[]
    for i in range(3,len(rows)-3):
        if rows[i]['l']==min(rows[j]['l'] for j in range(i-3,i+4)) and sum(rows[j]['l']==rows[i]['l'] for j in range(i-3,i+4))==1:
            ans.append((i,i+3,rows[i]['l']))
    return ans

def events(rows):
    ans=[]
    for pi,visible,price in pivots(rows):
        for raid in range(visible+1,len(rows)-1):
            b=rows[raid]
            if b['l']<price*0.997 and b['c']>price:
                for confirm in range(raid+1,min(len(rows),raid+4)):
                    if rows[confirm]['c']>b['h']:
                        ans.append((pi,visible,price,raid,confirm));break
                break
    return ans

def select(rows,evs,date):
    bydate={b['t']:i for i,b in enumerate(rows)};i=bydate.get(date)
    if i is None:return None
    eligible=[e for e in evs if e[4]<i and i-e[4]<=MAX_LAG]
    if not eligible:return None
    e=max(eligible,key=lambda x:x[4]);pi,visible,price,raid,confirm=e
    if any(rows[j]['c']<price for j in range(confirm+1,i+1)):return None
    return {'industry_ssl_idx':pi,'industry_ssl_confirm_idx':visible,'industry_raid_idx':raid,'industry_raid_date':rows[raid]['t'],
            'industry_confirm_idx':confirm,'industry_confirm_date':rows[confirm]['t'],'industry_stock_raid_idx':i,
            'industry_lead_lag_sessions':i-confirm}

def main():
    source=json.loads(SRC.read_text())
    if source.get('decision')!='INDUSTRY_LEAD_STOCK_LAG_SEEDS_READY__INDEPENDENT_ORACLE_NEXT':raise RuntimeError('V469 gate failed')
    with Path(source['artifacts']['seeds']).open(newline='') as h:expected=list(csv.DictReader(h))
    forbidden=[c for c in (expected[0] if expected else {}) if c!='no_outcome_fields' and any(x in c.lower() for x in ('pnl','exit','mfe','mae','winner','outcome','entry_price'))]
    if forbidden:raise RuntimeError(f'forbidden fields: {forbidden}')
    mapping,sums,own,_=v465.build_source();grouped=defaultdict(list)
    for row in expected:grouped[row['symbol']].append(row)
    passed=[];mismatches=[]
    for n,(sym,items) in enumerate(grouped.items(),1):
        industry=mapping.get(sym,'');rows=index_without_stock(sym,industry,sums,own);evs=events(rows)
        for row in items:
            got=select(rows,evs,row['raid_date'])
            if got is None:
                mismatches.append({'symbol':sym,'eligible_entry_date':row['eligible_entry_date'],'reason':'ORACLE_MISSING'});continue
            bad=[]
            for k,v in got.items():
                if str(row.get(k,''))!=str(v):bad.append(k)
            if bad:mismatches.append({'symbol':sym,'eligible_entry_date':row['eligible_entry_date'],'reason':'FIELD_MISMATCH:'+','.join(bad)})
            else:passed.append(row)
        if n%500==0:print(json.dumps({'symbols':n,'passed':len(passed),'mismatch':len(mismatches)}),flush=True)
    OUT.mkdir(parents=True,exist_ok=True);pcsv=OUT/'v470_oracle_passed_seeds.csv';mcsv=OUT/'v470_mismatches.csv'
    fields=list(passed[0]) if passed else ['symbol'];
    with pcsv.open('w',newline='') as h:w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(passed)
    with mcsv.open('w',newline='') as h:w=csv.DictWriter(h,fieldnames=['symbol','eligible_entry_date','reason']);w.writeheader();w.writerows(mismatches)
    report={'version':'V470_INDUSTRY_LEAD_STOCK_LAG_INDEPENDENT_ORACLE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'oracle_contract':'independent ex-stock industry geometric composite + unique 3L/3R SSL + raid/close-back + <=3-bar reversal + 1..10-session lead + hold-above-SSL',
      'expected_seed_count':len(expected),'oracle_pass_count':len(passed),'mismatch_total':len(mismatches),'mismatch_reasons':dict(Counter(r['reason'] for r in mismatches)),
      'invariants':{'forbidden_source_headers':forbidden,'duplicate_identity':len(passed)-len(set((r['symbol'],r['eligible_entry_date']) for r in passed)),'all_nontradable':all(str(r.get('tradable','')).lower()=='false' for r in passed)},
      'oracle_gate_pass':len(passed)==len(expected) and not mismatches,
      'decision':'INDUSTRY_LEAD_STOCK_LAG_ORACLE_PASS__FROZEN_T1_REPLAY_NEXT' if len(passed)==len(expected) and not mismatches else 'INDUSTRY_LEAD_STOCK_LAG_ORACLE_FAIL__NO_REPLAY',
      'artifacts':{'out_dir':str(OUT),'passed_seeds':str(pcsv),'mismatches':str(mcsv),'latest':str(LATEST)}}
    text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v470_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
