#!/usr/bin/env python3
"""V462 independent raw-bar oracle for V461 market-SMT seeds."""
from __future__ import annotations
import csv,json,math
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes');KDIR=ROOT/'kline_cache';AUD=ROOT/'smc_audit'
SRC=AUD/'v461_market_smt_turtle_soup_latest.json';BASE=AUD/'v454_turtle_soup_independent_oracle_latest.json'
OUT=AUD/f"v462_market_smt_independent_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}";LATEST=AUD/'v462_market_smt_independent_oracle_latest.json'
MIN_COMPONENTS=1000

def num(x):
    try:
        z=float(x);return z if math.isfinite(z) else 0.0
    except (TypeError,ValueError):return 0.0

def date(x):return ''.join(ch for ch in str(x or '') if ch.isdigit())[:8]

def rawbars(path):
    try:data=json.loads(path.read_text())
    except (OSError,json.JSONDecodeError):return []
    ans=[]
    for b in data:
        d=date(b.get('t') or b.get('date'));vals=[num(b.get(k)) for k in ('o','h','l','c')]
        if d and all(vals):ans.append({'t':d,'o':vals[0],'h':vals[1],'l':vals[2],'c':vals[3]})
    return sorted(ans,key=lambda b:b['t'])

def rebuild_index():
    aggregate={}
    for n,path in enumerate(sorted(KDIR.glob('*_daily_750.json')),1):
        bars=rawbars(path)
        if len(bars)<80:continue
        for a,b in zip(bars,bars[1:]):
            values=(b['o']/a['c'],b['h']/a['c'],b['l']/a['c'],b['c']/a['c'])
            if any(v<=0 or not math.isfinite(v) for v in values):continue
            acc=aggregate.setdefault(b['t'],[0.0,0.0,0.0,0.0,0])
            acc[0]+=math.log(values[0]);acc[1]+=math.log(values[1]);acc[2]+=math.log(values[2]);acc[3]+=math.log(values[3]);acc[4]+=1
        if n%500==0:print(json.dumps({'oracle_files':n}),flush=True)
    level=100.0;out=[]
    for d in sorted(aggregate):
        acc=aggregate[d]
        if acc[4]<MIN_COMPONENTS:continue
        ratios=[math.exp(acc[j]/acc[4]) for j in range(4)]
        o,h,l,c=[level*r for r in ratios];h=max(h,o,c);l=min(l,o,c)
        out.append({'t':d,'o':o,'h':h,'l':l,'c':c,'components':acc[4]});level=c
    return out

def pivots(bars):
    result=[]
    for p in range(3,len(bars)-3):
        if min(bars[q]['l'] for q in range(p-3,p+4) if q!=p)>bars[p]['l']:
            result.append((p,p+3,bars[p]['l']))
    return result

def oracle_pass(index,lows,raid_date):
    positions={b['t']:n for n,b in enumerate(index)};raid=positions.get(raid_date)
    if raid is None:return False
    known=[x for x in lows if x[1]<raid]
    if len(known)<2:return False
    prior,protected=known[-2],known[-1]
    return protected[2]>prior[2] and index[raid]['l']>=protected[2]*.997

def key(row):return row['symbol'],row['eligible_entry_date']

def main():
    src=json.loads(SRC.read_text());base=json.loads(BASE.read_text())
    if src.get('decision')!='MARKET_SMT_SEEDS_READY__INDEPENDENT_ORACLE_NEXT':raise RuntimeError('V461 gate failed')
    with Path(src['artifacts']['seeds']).open(newline='') as h:selected=list(csv.DictReader(h))
    with Path(base['artifacts']['passed_seeds']).open(newline='') as h:universe=list(csv.DictReader(h))
    index=rebuild_index();lows=pivots(index)
    expected={key(r) for r in universe if oracle_pass(index,lows,r['raid_date'])}
    observed={key(r) for r in selected};extra=observed-expected;missing=expected-observed
    stock_mismatch=0;market_field_mismatch=0;cache={}
    pos={b['t']:n for n,b in enumerate(index)}
    for r in selected:
        sym=r['symbol']
        if sym not in cache:cache[sym]=rawbars(KDIR/f"{sym.replace('.','_')}_daily_750.json")
        bars=cache[sym];byday={b['t']:i for i,b in enumerate(bars)};raid=byday.get(r['raid_date']);conf=byday.get(r['reversal_confirm_date']);eligible=byday.get(r['eligible_entry_date'])
        if raid is None or conf is None or eligible is None or not (raid<conf<eligible) or bars[raid]['l']>=num(r['ssl_price'])*.997 or bars[raid]['c']<=num(r['ssl_price']) or bars[conf]['c']<=bars[raid]['h'] or eligible!=conf+1:
            stock_mismatch+=1
        mi=pos.get(r['raid_date']);known=[x for x in lows if mi is not None and x[1]<mi]
        if mi is None or len(known)<2:market_field_mismatch+=1;continue
        a,b=known[-2],known[-1]
        checks=(int(r['market_prev_low_idx'])==a[0],int(r['market_prev_low_confirm_idx'])==a[1],int(r['market_protected_low_idx'])==b[0],int(r['market_protected_low_confirm_idx'])==b[1],abs(num(r['market_prev_low'])-a[2])<1e-6,abs(num(r['market_protected_low'])-b[2])<1e-6,abs(num(r['market_raid_low'])-index[mi]['l'])<1e-6)
        if not all(checks):market_field_mismatch+=1
    failures=len(extra)+len(missing)+stock_mismatch+market_field_mismatch
    OUT.mkdir(parents=True,exist_ok=True)
    mismatch_file=OUT/'v462_mismatches.csv'
    with mismatch_file.open('w',newline='') as h:
        w=csv.writer(h);w.writerow(['type','symbol','eligible_entry_date'])
        for x in sorted(extra):w.writerow(['V461_EXTRA',*x])
        for x in sorted(missing):w.writerow(['V461_MISSING',*x])
    passed=failures==0 and len(observed)>=300
    report={'version':'V462_MARKET_SMT_INDEPENDENT_ORACLE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'oracle_contract':'independently rebuild geometric equal-weight market OHLC index and 3L/3R pivots; derive complete SMT subset from all V454 oracle-passed Turtle-Soup seeds; recheck every stock raid/confirmation tuple from raw bars',
      'source_seed_count':len(selected),'expected_seed_count':len(expected),'observed_seed_count':len(observed),'extra_seed_count':len(extra),'missing_seed_count':len(missing),'stock_semantic_mismatch':stock_mismatch,'market_field_mismatch':market_field_mismatch,'mismatch_total':failures,
      'invariants':{'identity_set_equal':observed==expected,'duplicate_symbol_entry':len(selected)-len(observed),'no_outcomes_read':True},
      'oracle_gate_pass':passed,'decision':'MARKET_SMT_INDEPENDENT_ORACLE_PASS__FROZEN_T1_REPLAY_NEXT' if passed else 'MARKET_SMT_ORACLE_FAIL__NO_REPLAY',
      'artifacts':{'out_dir':str(OUT),'passed_seeds':src['artifacts']['seeds'],'mismatches':str(mismatch_file),'latest':str(LATEST)}}
    text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v462_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
