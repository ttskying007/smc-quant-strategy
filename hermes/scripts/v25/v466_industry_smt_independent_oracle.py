#!/usr/bin/env python3
"""V466 independent raw-bar differential oracle for V465 industry SMT."""
from __future__ import annotations
import csv,json,math
from collections import defaultdict,Counter
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes');KDIR=ROOT/'kline_cache';AUD=ROOT/'smc_audit'
SRC=AUD/'v465_industry_smt_turtle_soup_latest.json';BASE=AUD/'v454_turtle_soup_independent_oracle_latest.json'
INDMAP=AUD/'v225_baostock_industry_participation_probe_20260627_031854/baostock_stock_industry.json'
OUT=AUD/f"v466_industry_smt_independent_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}";LATEST=AUD/'v466_industry_smt_independent_oracle_latest.json';MIN_PEERS=15

def n(x):
    try:
        v=float(x);return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError):return 0.0

def d(x):return ''.join(ch for ch in str(x or '') if ch.isdigit())[:8]
def sym(path):
    a=path.stem.replace('_daily_750','').split('_',1);return '.'.join(a) if len(a)==2 else ''
def bars(path):
    try:raw=json.loads(path.read_text())
    except (OSError,json.JSONDecodeError):return []
    out=[]
    for b in raw:
        day=d(b.get('t') or b.get('date'));v=[n(b.get(k)) for k in ('o','h','l','c')]
        if day and all(v):out.append({'t':day,'o':v[0],'h':v[1],'l':v[2],'c':v[3]})
    return sorted(out,key=lambda x:x['t'])

def source_tables():
    mp={r['symbol']:r['industry'] for r in json.loads(INDMAP.read_text()) if r.get('symbol') and r.get('industry')}
    totals=defaultdict(lambda:defaultdict(lambda:[0.,0.,0.,0.,0]));single={}
    for q,path in enumerate(sorted(KDIR.glob('*_daily_750.json')),1):
        s=sym(path);ind=mp.get(s);seq=bars(path)
        if not ind or len(seq)<80:continue
        own={}
        for prev,cur in zip(seq,seq[1:]):
            ratios=[cur[k]/prev['c'] for k in ('o','h','l','c')]
            if any(x<=0 or not math.isfinite(x) for x in ratios):continue
            logs=[math.log(x) for x in ratios];own[cur['t']]=logs;acc=totals[ind][cur['t']]
            for j in range(4):acc[j]+=logs[j]
            acc[4]+=1
        single[s]=own
        if q%500==0:print(json.dumps({'oracle_files':q}),flush=True)
    return mp,totals,single

def composite(s,ind,totals,single):
    level=100.;out=[];own=single.get(s,{})
    for day in sorted(totals.get(ind,{})):
        src=totals[ind][day];count=src[4]-(1 if day in own else 0)
        if count<MIN_PEERS:continue
        logs=[src[j]-(own[day][j] if day in own else 0.) for j in range(4)];rel=[math.exp(x/count) for x in logs]
        o,h,l,c=[level*x for x in rel];h=max(h,o,c);l=min(l,o,c);out.append({'t':day,'o':o,'h':h,'l':l,'c':c,'components':count});level=c
    return out

def pivots(seq):
    out=[]
    for i in range(3,len(seq)-3):
        if seq[i]['l']<min(seq[j]['l'] for j in range(i-3,i+4) if j!=i):out.append((i,i+3,seq[i]['l']))
    return out

def qualifies(seq,pivs,raid_date):
    by={x['t']:i for i,x in enumerate(seq)};ri=by.get(raid_date)
    if ri is None:return None
    known=[x for x in pivs if x[1]<ri]
    if len(known)<2:return None
    prior,protected=known[-2],known[-1]
    if protected[2]<=prior[2] or seq[ri]['l']<protected[2]*.997:return None
    return prior,protected,ri

def key(r):return r['symbol'],r['eligible_entry_date']

def main():
    src=json.loads(SRC.read_text());base=json.loads(BASE.read_text())
    if src.get('decision')!='INDUSTRY_SMT_SEEDS_READY__INDEPENDENT_ORACLE_NEXT':raise RuntimeError('V465 gate failed')
    with Path(src['artifacts']['seeds']).open(newline='') as h:selected=list(csv.DictReader(h))
    with Path(base['artifacts']['passed_seeds']).open(newline='') as h:universe=list(csv.DictReader(h))
    mp,totals,single=source_tables();grouped=defaultdict(list)
    for r in universe:grouped[r['symbol']].append(r)
    expected=set();ctx_cache={}
    for q,(s,items) in enumerate(grouped.items(),1):
        ind=mp.get(s)
        if not ind:continue
        seq=composite(s,ind,totals,single);pv=pivots(seq);ctx_cache[s]=(seq,pv)
        for r in items:
            if qualifies(seq,pv,r['raid_date']):expected.add(key(r))
        if q%500==0:print(json.dumps({'oracle_symbols':q,'expected':len(expected)}),flush=True)
    observed={key(r) for r in selected};extra=observed-expected;missing=expected-observed;field_bad=0;stock_bad=0;stock_cache={}
    for r in selected:
        s=r['symbol'];seq,pv=ctx_cache[s];q=qualifies(seq,pv,r['raid_date'])
        if q is None:field_bad+=1;continue
        prior,protected,ri=q
        checks=(int(r['industry_prev_low_idx'])==prior[0],int(r['industry_prev_low_confirm_idx'])==prior[1],int(r['industry_protected_low_idx'])==protected[0],int(r['industry_protected_low_confirm_idx'])==protected[1],abs(n(r['industry_prev_low'])-prior[2])<1e-6,abs(n(r['industry_protected_low'])-protected[2])<1e-6,abs(n(r['industry_raid_low'])-seq[ri]['l'])<1e-6,int(r['industry_components'])==seq[ri]['components'])
        if not all(checks):field_bad+=1
        if s not in stock_cache:stock_cache[s]=bars(KDIR/f"{s.replace('.','_')}_daily_750.json")
        sb=stock_cache[s];by={x['t']:i for i,x in enumerate(sb)};a=by.get(r['raid_date']);b=by.get(r['reversal_confirm_date']);c=by.get(r['eligible_entry_date'])
        if a is None or b is None or c is None or not(a<b<c) or sb[a]['l']>=n(r['ssl_price'])*.997 or sb[a]['c']<=n(r['ssl_price']) or sb[b]['c']<=sb[a]['h'] or c!=b+1:stock_bad+=1
    failures=len(extra)+len(missing)+field_bad+stock_bad;OUT.mkdir(parents=True,exist_ok=True);mf=OUT/'v466_mismatches.csv'
    with mf.open('w',newline='') as h:
        w=csv.writer(h);w.writerow(['type','symbol','eligible_entry_date'])
        for x in sorted(extra):w.writerow(['V465_EXTRA',*x])
        for x in sorted(missing):w.writerow(['V465_MISSING',*x])
    yearly=Counter(r['eligible_entry_date'][:4] for r in selected);passed=failures==0 and len(observed)>=300 and all(yearly.get(y,0)>=40 for y in ('2023','2024','2025','2026'))
    report={'version':'V466_INDUSTRY_SMT_INDEPENDENT_ORACLE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'oracle_contract':'independently rebuild every ex-stock industry composite, unique 3L/3R pivots, complete expected subset from all V454 passed seeds, and every stock raid-confirmation tuple',
      'source_seed_count':len(selected),'expected_seed_count':len(expected),'observed_seed_count':len(observed),'extra_seed_count':len(extra),'missing_seed_count':len(missing),'industry_field_mismatch':field_bad,'stock_semantic_mismatch':stock_bad,'mismatch_total':failures,'yearly_seed_count':dict(sorted(yearly.items())),
      'invariants':{'identity_set_equal':observed==expected,'duplicate_symbol_entry':len(selected)-len(observed),'no_outcomes_read':True},'oracle_gate_pass':passed,
      'decision':'INDUSTRY_SMT_INDEPENDENT_ORACLE_PASS__FROZEN_T1_REPLAY_NEXT' if passed else 'INDUSTRY_SMT_ORACLE_FAIL__NO_REPLAY',
      'artifacts':{'out_dir':str(OUT),'passed_seeds':src['artifacts']['seeds'],'mismatches':str(mf),'latest':str(LATEST)}}
    text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v466_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
