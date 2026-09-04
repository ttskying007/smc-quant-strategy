#!/usr/bin/env python3
"""V465 no-outcome ex-stock industry-SMT Turtle-Soup generator.

Frozen ontology: verified stock Turtle-Soup SSL raid -> same-day ex-stock
industry composite protects an already-confirmed higher swing low -> stock
reversal confirmation -> next-session eligibility. No outcome fields are read.
"""
from __future__ import annotations
import csv,json,math
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes');KDIR=ROOT/'kline_cache';AUD=ROOT/'smc_audit'
SOURCE=AUD/'v454_turtle_soup_independent_oracle_latest.json'
INDMAP=AUD/'v225_baostock_industry_participation_probe_20260627_031854/baostock_stock_industry.json'
OUT=AUD/f"v465_industry_smt_turtle_soup_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST=AUD/'v465_industry_smt_turtle_soup_latest.json'
YEARS=('2023','2024','2025','2026');MIN_PEERS=15

def f(x):
    try:
        v=float(x);return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError):return 0.0

def ds(x):return ''.join(c for c in str(x or '') if c.isdigit())[:8]

def symbol(path):
    p=path.stem.replace('_daily_750','').split('_',1)
    return f'{p[0]}.{p[1]}' if len(p)==2 else ''

def load(path):
    try:raw=json.loads(path.read_text())
    except (OSError,json.JSONDecodeError):return []
    rows=[]
    for b in raw:
        d=ds(b.get('t') or b.get('date'));vals=[f(b.get(k)) for k in ('o','h','l','c')]
        if d and all(vals):rows.append({'t':d,'o':vals[0],'h':vals[1],'l':vals[2],'c':vals[3]})
    return sorted(rows,key=lambda r:r['t'])

def build_source():
    mapping={r['symbol']:r.get('industry','') for r in json.loads(INDMAP.read_text()) if r.get('symbol') and r.get('industry')}
    sums=defaultdict(lambda:defaultdict(lambda:[0.0,0.0,0.0,0.0,0]))
    own={};covered=0
    for n,path in enumerate(sorted(KDIR.glob('*_daily_750.json')),1):
        sym=symbol(path);ind=mapping.get(sym);bars=load(path)
        if not ind or len(bars)<80:continue
        covered+=1;ratios={}
        for a,b in zip(bars,bars[1:]):
            vals=tuple(b[k]/a['c'] for k in ('o','h','l','c'))
            if any(v<=0 or not math.isfinite(v) for v in vals):continue
            logs=tuple(math.log(v) for v in vals);ratios[b['t']]=logs;acc=sums[ind][b['t']]
            for j,v in enumerate(logs):acc[j]+=v
            acc[4]+=1
        own[sym]=ratios
        if n%500==0:print(json.dumps({'source_files':n,'mapped':covered}),flush=True)
    return mapping,sums,own,covered

def ex_stock_index(sym,ind,sums,own):
    level=100.0;rows=[];mine=own.get(sym,{})
    for d in sorted(sums.get(ind,{})):
        acc=sums[ind][d];logs=list(acc[:4]);count=acc[4]
        if d in mine:
            count-=1
            for j in range(4):logs[j]-=mine[d][j]
        if count<MIN_PEERS:continue
        rel=[math.exp(logs[j]/count) for j in range(4)];o,h,l,c=[level*x for x in rel]
        h=max(h,o,c);l=min(l,o,c);rows.append({'t':d,'o':o,'h':h,'l':l,'c':c,'components':count});level=c
    return rows

def lows(bars):
    return [(i,i+3,bars[i]['l']) for i in range(3,len(bars)-3)
            if all(bars[j]['l']>bars[i]['l'] for j in range(i-3,i+4) if j!=i)]

def context(index,pivots,date):
    pos={b['t']:i for i,b in enumerate(index)};raid=pos.get(date)
    if raid is None:return None,'INDUSTRY_DATE_MISSING'
    known=[x for x in pivots if x[1]<raid]
    if len(known)<2:return None,'INDUSTRY_TWO_CONFIRMED_LOWS_MISSING'
    prior,protected=known[-2],known[-1]
    if protected[2]<=prior[2]:return None,'INDUSTRY_NOT_HIGHER_LOW'
    if index[raid]['l']<protected[2]*.997:return None,'INDUSTRY_PROTECTED_LOW_RAIDED'
    return {'industry_raid_idx':raid,'industry_prev_low_idx':prior[0],'industry_prev_low_confirm_idx':prior[1],
            'industry_prev_low_date':index[prior[0]]['t'],'industry_prev_low_confirm_date':index[prior[1]]['t'],
            'industry_prev_low':prior[2],'industry_protected_low_idx':protected[0],
            'industry_protected_low_confirm_idx':protected[1],'industry_protected_low_date':index[protected[0]]['t'],
            'industry_protected_low_confirm_date':index[protected[1]]['t'],'industry_protected_low':protected[2],
            'industry_raid_low':index[raid]['l'],'industry_components':index[raid]['components']},'PASS'

def main():
    src=json.loads(SOURCE.read_text())
    if src.get('decision')!='INDEPENDENT_ORACLE_PASS__FROZEN_T1_REPLAY_ALLOWED':raise RuntimeError('V454 gate failed')
    with Path(src['artifacts']['passed_seeds']).open(newline='') as h:seeds=list(csv.DictReader(h))
    forbidden=[c for c in (seeds[0] if seeds else {}) if c!='no_outcome_fields' and any(x in c.lower() for x in ('pnl','exit','mfe','mae','winner','outcome'))]
    if forbidden:raise RuntimeError(f'forbidden source fields: {forbidden}')
    OUT.mkdir(parents=True,exist_ok=True);mapping,sums,own,covered=build_source();grouped=defaultdict(list)
    for seed in seeds:grouped[seed['symbol']].append(seed)
    rows=[];counts=Counter();unmapped=0
    for n,(sym,items) in enumerate(grouped.items(),1):
        ind=mapping.get(sym)
        if not ind:unmapped+=len(items);continue
        index=ex_stock_index(sym,ind,sums,own);pivots=lows(index)
        for seed in items:
            ctx,status=context(index,pivots,seed['raid_date']);counts[status]+=1
            if ctx is None:continue
            row={**seed,'ontology':'INDUSTRY_SMT_TURTLE_SOUP_SSL_REVERSAL','industry':ind,
                 **{k:(round(v,8) if isinstance(v,float) else v) for k,v in ctx.items()},
                 'smt_semantic_order_valid':ctx['industry_prev_low_confirm_date']<ctx['industry_protected_low_date']<ctx['industry_protected_low_confirm_date']<seed['raid_date']<seed['reversal_confirm_date']<seed['eligible_entry_date'],
                 'tradable':'false','buy_enabled':'false','no_outcome_fields':'true'}
            rows.append(row)
        if n%500==0:print(json.dumps({'symbols':n,'seeds':len(rows)}),flush=True)
    yearly=Counter(r['eligible_entry_date'][:4] for r in rows);support=len(rows)>=300 and all(yearly.get(y,0)>=40 for y in YEARS)
    outcsv=OUT/'v465_industry_smt_seeds.csv';fields=list(rows[0]) if rows else ['symbol','ontology']
    with outcsv.open('w',newline='') as h:w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(rows)
    report={'version':'V465_INDUSTRY_SMT_TURTLE_SOUP_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'frozen_contract':'verified stock Turtle-Soup SSL raid -> same-day ex-stock industry composite protects a previously confirmed higher swing low -> stock reversal confirms -> next-open eligibility',
      'distinct_information':'Cross-security industry-level SMT divergence from same local OHLCV; source stock is excluded from its industry composite.',
      'composite_contract':f'geometric mean OHLC relatives of mapped same-industry peers excluding source stock; minimum {MIN_PEERS} peers/date; unique 3L/3R pivots',
      'source_seed_count':len(seeds),'industry_mapped_symbols':covered,'unmapped_source_seeds':unmapped,'seed_count':len(rows),'yearly_seed_count':dict(sorted(yearly.items())),'rejection_counts':dict(counts),
      'support_gate':{'aggregate_n':300,'each_2023_2026_year_n':40,'pass':support},
      'invariants':{'forbidden_source_headers':forbidden,'semantic_order_failures':sum(not r['smt_semantic_order_valid'] for r in rows),'duplicate_symbol_entry':len(rows)-len(set((r['symbol'],r['eligible_entry_date']) for r in rows)),'all_nontradable':all(r['tradable']=='false' and r['buy_enabled']=='false' for r in rows),'no_outcome_fields':all(r['no_outcome_fields']=='true' for r in rows)},
      'decision':'INDUSTRY_SMT_SEEDS_READY__INDEPENDENT_ORACLE_NEXT' if support and all(r['smt_semantic_order_valid'] for r in rows) else 'INDUSTRY_SMT_PRE_OUTCOME_GATE_FAIL__NO_REPLAY',
      'artifacts':{'out_dir':str(OUT),'seeds':str(outcsv),'latest':str(LATEST)}}
    text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v465_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
