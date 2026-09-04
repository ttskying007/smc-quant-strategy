#!/usr/bin/env python3
"""V507 outcome-blind weekly bearish-FVG inversion -> daily support transfer."""
from __future__ import annotations
import csv,json,math
from collections import Counter
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes');KDIR=ROOT/'kline_cache';AUD=ROOT/'smc_audit'
OUT=AUD/f"v507_weekly_ifvg_support_transfer_no_write_{datetime.now():%Y%m%d_%H%M%S}";LATEST=AUD/'v507_weekly_ifvg_support_transfer_latest.json';YEARS=('2023','2024','2025','2026')

def f(x):
    try:v=float(x);return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError):return 0.0

def ds(x):return ''.join(c for c in str(x or '') if c.isdigit())[:8]

def load(path):
    try:raw=json.loads(path.read_text())
    except (OSError,json.JSONDecodeError):return []
    out=[]
    for b in raw:
        r={k:f(b.get(k)) for k in ('o','h','l','c')};d=ds(b.get('t') or b.get('date'))
        if d and min(r.values())>0:r['t']=d;out.append(r)
    return sorted(out,key=lambda x:x['t'])

def symbol(path):
    code,ex=path.name.removesuffix('_daily_750.json').split('_');return f'{code}.{ex}'

def weeks(daily):
    groups=[];key=None
    for b in daily:
        k=datetime.strptime(b['t'],'%Y%m%d').date().isocalendar()[:2]
        if k!=key:groups.append([]);key=k
        groups[-1].append(b)
    return [{'start_date':g[0]['t'],'end_date':g[-1]['t'],'o':g[0]['o'],'h':max(x['h'] for x in g),'l':min(x['l'] for x in g),'c':g[-1]['c']} for g in groups[:-1] if g]

def lifecycle(daily,start_date,zl,zh):
    start=next((i for i,b in enumerate(daily) if b['t']>start_date),None)
    if start is None:return None,'NO_DAILY_AFTER_INVERSION'
    touch=reclaim=None
    for i in range(start,min(len(daily),start+41)):
        b=daily[i]
        if b['c']<zl:return None,'IFVG_INVALIDATED_BEFORE_HOLD'
        if touch is None:
            if b['l']<=zh and b['h']>=zl:touch=i
            continue
        if reclaim is None:
            if i>touch and b['c']>zh:reclaim=i
            continue
        if i>reclaim and b['c']>zh and b['l']>=zl:return (touch,reclaim,i,i+1 if i+1<len(daily) else None),'PASS'
    if touch is None:return None,'NO_TOUCH_40D'
    if reclaim is None:return None,'NO_RECLAIM_40D'
    return None,'NO_HOLD_40D'

def generate(sym,daily):
    ws=weeks(daily);rows=[];rejects=Counter();raw=0
    for i in range(2,len(ws)):
        zl,zh=ws[i]['h'],ws[i-2]['l']
        if zl>=zh*.9995:continue
        inversion=next((j for j in range(i+1,len(ws)) if ws[j]['c']>zh*1.003),None)
        if inversion is None:rejects['NO_WEEKLY_CLOSE_INVERSION']+=1;continue
        raw+=1;life,reason=lifecycle(daily,ws[inversion]['end_date'],zl,zh)
        if life is None:rejects[reason]+=1;continue
        touch,reclaim,hold,eligible=life
        if eligible is None:rejects['ENTRY_RIGHT_EDGE']+=1;continue
        order=ws[i-2]['end_date']<ws[i]['end_date']<ws[inversion]['end_date']<daily[touch]['t']<daily[reclaim]['t']<daily[hold]['t']<daily[eligible]['t'] and eligible==hold+1
        rows.append({'symbol':sym,'ontology':'WEEKLY_BEAR_FVG_BULLISH_INVERSION_DAILY_SUPPORT_TRANSFER','weekly_fvg_left_idx':i-2,'weekly_fvg_create_idx':i,
          'weekly_fvg_left_end_date':ws[i-2]['end_date'],'weekly_fvg_create_end_date':ws[i]['end_date'],'weekly_inversion_idx':inversion,'weekly_inversion_end_date':ws[inversion]['end_date'],
          'weekly_inversion_close':round(ws[inversion]['c'],6),'zone_low':round(zl,6),'zone_high':round(zh,6),'touch_idx':touch,'touch_date':daily[touch]['t'],
          'reclaim_idx':reclaim,'reclaim_date':daily[reclaim]['t'],'hold_idx':hold,'hold_date':daily[hold]['t'],'eligible_entry_idx':eligible,'eligible_entry_date':daily[eligible]['t'],
          'semantic_order_valid':order,'tradable':False,'buy_enabled':False,'no_outcome_fields':True})
    return rows,rejects,raw

def main():
    OUT.mkdir(parents=True,exist_ok=True);raw=[];rejects=Counter();scanned=complete=0
    for n,path in enumerate(sorted(KDIR.glob('*_daily_750.json')),1):
        daily=load(path)
        if len(daily)<150:continue
        scanned+=1;rows,bad,count=generate(symbol(path),daily);raw.extend(rows);rejects.update(bad);complete+=count
        if n%500==0:print(json.dumps({'progress':n,'raw':len(raw)}),flush=True)
    dedup={}
    for r in raw:
        key=(r['symbol'],r['eligible_entry_date']);old=dedup.get(key)
        if old is None or r['weekly_inversion_idx']<old['weekly_inversion_idx']:dedup[key]=r
    rows=list(dedup.values());yearly=Counter(r['eligible_entry_date'][:4] for r in rows);support=len(rows)>=300 and all(yearly.get(y,0)>=40 for y in YEARS)
    seed=OUT/'v507_semantic_seeds.csv';fields=list(rows[0]) if rows else ['symbol','ontology']
    with seed.open('w',newline='') as h:w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(rows)
    inv={'semantic_order_failures':sum(not r['semantic_order_valid'] for r in rows),'duplicate_symbol_entry':len(rows)-len(set((r['symbol'],r['eligible_entry_date']) for r in rows)),'no_outcome_fields':all(r['no_outcome_fields'] for r in rows),'all_nontradable':all(not r['tradable'] and not r['buy_enabled'] for r in rows)}
    ok=support and not inv['semantic_order_failures'] and not inv['duplicate_symbol_entry']
    result={'version':'V507_WEEKLY_IFVG_SUPPORT_TRANSFER_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'frozen_contract':'completed weekly bearish FVG >=0.05% -> first later completed weekly close above FVG high by >=0.3% creates bullish IFVG support -> first post-inversion daily touch -> later close reclaim -> later hold -> next-open eligibility; daily close below IFVG low cancels',
      'distinct_information':'Polarity-flip support created by failure of a weekly supply imbalance; distinct from bullish weekly FVG demand, breaker candle, rejection block, BOS-demand, and SSL-CHOCH ontologies.',
      'planned_execution_if_oracle_passes':'next open; SL=IFVG low*0.99; TP=nearest higher confirmed weekly swing high visible by hold; time30; fee0.2%; serial strict T+1; one replay',
      'promotion_gate':{'n':300,'each_year_n':40,'gross_wr_pct':55.0,'avg_net_pnl_pct':0.5,'each_year_gross_wr_pct':50.0,'each_year_avg_net_pnl_pct':0.0,'profit_factor':1.15,'payoff_rr':0.7,'t1_violations':0},
      'symbols_scanned':scanned,'raw_complete_inversions':complete,'raw_seed_count':len(raw),'seed_count':len(rows),'yearly_seed_count':dict(sorted(yearly.items())),'rejection_counts':dict(rejects),'support_gate_pass':support,'invariants':inv,
      'decision':'WEEKLY_IFVG_SUPPORT_SEEDS_READY__INDEPENDENT_ORACLE_NEXT' if ok else 'WEEKLY_IFVG_SUPPORT_SUPPORT_OR_SEMANTIC_FAIL__NO_REPLAY','artifacts':{'out_dir':str(OUT),'seeds':str(seed),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2);(OUT/'v507_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
