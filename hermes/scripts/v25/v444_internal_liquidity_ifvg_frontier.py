#!/usr/bin/env python3
"""V444 no-write frontier: two distinct causal daily SMC ontologies.

Frozen before outcomes:
A) INTERNAL_LIQUIDITY_TRANSFER: established external HH/HL -> confirmed internal
   high then higher-low -> wick sweep of internal low while external low holds ->
   close displacement through internal high -> next open.
B) BEAR_IFVG_ROLE_REVERSAL: causal bearish FVG -> close invalidates above the gap ->
   later retest -> later reclaim -> later hold -> next open.

One fixed strict-T+1 execution only. No threshold/exit search and no production writes.
"""
from __future__ import annotations
import csv, json, math, statistics
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
OUT=AUD/f"v444_internal_liquidity_ifvg_frontier_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST=AUD/'v444_internal_liquidity_ifvg_frontier_latest.json'
YEARS=('2023','2024','2025','2026'); MAX_HOLD=30
GATE={'n':300,'each_year_n':40,'wr_pct':55.0,'avg_pnl_pct':0.5,'each_year_wr_pct':50.0,'each_year_avg_pnl_pct':0.0,'t1_violations':0}

def f(x):
    try:
        v=float(x); return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError): return 0.0

def day(b): return ''.join(c for c in str(b.get('t') or b.get('date') or '') if c.isdigit())[:8]

def load(path):
    try: raw=json.loads(path.read_text())
    except (OSError,json.JSONDecodeError): return []
    out=[]
    for b in raw:
        r={k:f(b.get(k)) for k in ('o','h','l','c')}
        if day(b) and all(r.values()): r['t']=day(b); out.append(r)
    return sorted(out,key=lambda x:x['t'])

def sym(path):
    a,b=path.name.removesuffix('_daily_750.json').split('_'); return f'{a}.{b}'

def pivots(bars,left,right):
    hs=[]; ls=[]
    for i in range(left,len(bars)-right):
        h,l=bars[i]['h'],bars[i]['l']
        if all(bars[j]['h']<h for j in range(i-left,i+right+1) if j!=i): hs.append({'idx':i,'confirm':i+right,'price':h})
        if all(bars[j]['l']>l for j in range(i-left,i+right+1) if j!=i): ls.append({'idx':i,'confirm':i+right,'price':l})
    return hs,ls

def nearest_known_high(ext_highs,cutoff,entry):
    xs=[x for x in ext_highs if x['confirm']<=cutoff and x['price']>entry]
    return min(xs,key=lambda x:x['price']) if xs else None

def idm_rows(symbol,bars,ext_h,ext_l,int_h,int_l):
    rows=[]; seen=set()
    for i in range(20,len(bars)-2):
        eh=[x for x in ext_h if x['confirm']<=i]; el=[x for x in ext_l if x['confirm']<=i]
        ih=[x for x in int_h if x['confirm']<=i]; il=[x for x in int_l if x['confirm']<=i]
        if len(eh)<2 or len(el)<2 or not ih or not il: continue
        if not (eh[-1]['price']>eh[-2]['price'] and el[-1]['price']>el[-2]['price']): continue
        low=il[-1]
        highs_before=[x for x in ih if el[-1]['idx']<x['idx']<low['idx']]
        if not highs_before or low['price']<=el[-1]['price'] or low['idx']<=el[-1]['idx']: continue
        ihigh=highs_before[-1]; b=bars[i]
        if not (i>low['confirm'] and b['l']<low['price']*.997 and b['c']>low['price'] and b['c']>el[-1]['price']): continue
        event=None
        for j in range(i+1,min(len(bars),i+6)):
            if bars[j]['c']<el[-1]['price']: break
            if bars[j]['c']>ihigh['price']*1.002: event=j; break
        if event is None or event+1>=len(bars): continue
        key=(symbol,bars[event+1]['t'])
        if key in seen: continue
        seen.add(key)
        rows.append({'symbol':symbol,'ontology':'INTERNAL_LIQUIDITY_TRANSFER','external_low_idx':el[-1]['idx'],'external_low':el[-1]['price'],
          'internal_high_idx':ihigh['idx'],'internal_high':ihigh['price'],'internal_low_idx':low['idx'],'internal_low':low['price'],
          'sweep_idx':i,'sweep_date':bars[i]['t'],'event_idx':event,'event_date':bars[event]['t'],'takeover_idx':event,
          'takeover_date':bars[event]['t'],'eligible_entry_idx':event+1,'eligible_entry_date':bars[event+1]['t'],
          'zone_low':b['l'],'zone_high':low['price'],'semantic_order_valid':(el[-1]['idx']<ihigh['idx']<low['idx'] and max(el[-1]['confirm'],ihigh['confirm'],low['confirm'])<i<event<event+1)})
    return rows

def ifvg_rows(symbol,bars):
    rows=[]; seen=set()
    for born in range(2,len(bars)-4):
        low=bars[born]['h']; high=bars[born-2]['l']
        if not high>low*1.0005: continue
        failure=None
        for j in range(born+1,min(len(bars),born+21)):
            if bars[j]['c']>high*1.002: failure=j; break
        if failure is None: continue
        touch=reclaim=hold=None; cancelled=False
        for j in range(failure+1,min(len(bars),failure+31)):
            b=bars[j]
            if b['c']<low: cancelled=True; break
            if touch is None:
                if b['l']<=high and b['h']>=low: touch=j
                continue
            if reclaim is None:
                if j>touch and b['c']>high: reclaim=j
                continue
            if j>reclaim and b['c']>high and b['l']>=low: hold=j; break
        if cancelled or hold is None or hold+1>=len(bars): continue
        key=(symbol,bars[hold+1]['t'])
        if key in seen: continue
        seen.add(key)
        rows.append({'symbol':symbol,'ontology':'BEAR_IFVG_ROLE_REVERSAL','fvg_born_idx':born,'fvg_born_date':bars[born]['t'],
          'failure_idx':failure,'failure_date':bars[failure]['t'],'touch_idx':touch,'touch_date':bars[touch]['t'],
          'reclaim_idx':reclaim,'reclaim_date':bars[reclaim]['t'],'takeover_idx':hold,'takeover_date':bars[hold]['t'],
          'eligible_entry_idx':hold+1,'eligible_entry_date':bars[hold+1]['t'],'zone_low':low,'zone_high':high,
          'semantic_order_valid':born<failure<touch<reclaim<hold<hold+1})
    return rows

def replay(row,bars,ext_h):
    e=int(row['eligible_entry_idx']); t=int(row['takeover_idx'])
    if e!=t+1 or e+MAX_HOLD>=len(bars): return None
    entry=bars[e]['o']; sl=f(row['zone_low'])*.99
    if not 0<sl<entry: return None
    target=nearest_known_high(ext_h,t,entry); tp=target['price'] if target else None
    last=e+MAX_HOLD; xi=last; xp=bars[last]['c']; reason='TIME30_NO_TARGET' if tp is None else 'TIME30_TARGET_UNREACHED'; collision=False
    for j in range(e+1,last+1):
        b=bars[j]
        if b['o']<=sl: xi,xp,reason=j,b['o'],'SL_GAP_T1'; break
        if tp is not None and b['o']>=tp: xi,xp,reason=j,b['o'],'TP_GAP_T1'; break
        hs=b['l']<=sl; ht=tp is not None and b['h']>=tp
        if hs and ht: xi,xp,reason,collision=j,sl,'SL_TP_COLLISION_T1',True; break
        if hs: xi,xp,reason=j,sl,'STRUCTURE_SL_T1'; break
        if ht: xi,xp,reason=j,tp,'KNOWN_LIQUIDITY_TP_T1'; break
    pnl=(xp/entry-1)*100; risk=(entry/sl-1)*100; reward=((tp/entry-1)*100 if tp else None)
    return {**row,'entry_date':bars[e]['t'],'entry_price':round(entry,6),'sl':round(sl,6),'tp':'' if tp is None else round(tp,6),
      'planned_rr':'' if reward is None else round(reward/risk,4),'exit_idx':xi,'exit_date':bars[xi]['t'],'exit_price':round(xp,6),
      'exit_reason':reason,'hold_bars':xi-e,'pnl_pct':round(pnl,6),'t1_violation':bars[xi]['t']<=bars[e]['t'],'same_bar_collision':collision}

def stats(rows):
    if not rows: return {'n':0,'wr_pct':0,'avg_pnl_pct':0,'payoff_rr':0,'profit_factor':0}
    p=[f(r['pnl_pct']) for r in rows]; w=[x for x in p if x>0]; l=[x for x in p if x<=0]
    return {'n':len(p),'wr_pct':round(len(w)/len(p)*100,4),'avg_pnl_pct':round(sum(p)/len(p),4),'median_pnl_pct':round(statistics.median(p),4),
      'avg_win_pct':round(sum(w)/len(w),4) if w else 0,'avg_loss_pct':round(sum(l)/len(l),4) if l else 0,
      'payoff_rr':round((sum(w)/len(w))/abs(sum(l)/len(l)),4) if w and l and sum(l) else 0,
      'profit_factor':round(sum(w)/abs(sum(l)),4) if l and sum(l) else 0,'cum_pnl_pct':round(sum(p),4),
      'sl_pct':round(sum('SL' in r['exit_reason'] for r in rows)/len(rows)*100,4)}

def pass_gate(overall,yearly,t1):
    return overall['n']>=GATE['n'] and overall['wr_pct']>=GATE['wr_pct'] and overall['avg_pnl_pct']>=GATE['avg_pnl_pct'] and all(yearly[y]['n']>=GATE['each_year_n'] and yearly[y]['wr_pct']>=GATE['each_year_wr_pct'] and yearly[y]['avg_pnl_pct']>GATE['each_year_avg_pnl_pct'] for y in YEARS) and t1==0

def main():
    OUT.mkdir(parents=True,exist_ok=True); seeds=[]; trades=[]; counts=Counter(); scanned=0
    for n,path in enumerate(sorted(KDIR.glob('*_daily_750.json')),1):
        bars=load(path)
        if len(bars)<80: continue
        scanned+=1; s=sym(path); eh,el=pivots(bars,5,5); ih,il=pivots(bars,2,2)
        generated=idm_rows(s,bars,eh,el,ih,il)+ifvg_rows(s,bars)
        seeds.extend(generated)
        for r in generated:
            counts[r['ontology']]+=1
            x=replay(r,bars,eh)
            if x: trades.append(x)
        if n%500==0: print(json.dumps({'progress':n,'seeds':len(seeds),'trades':len(trades)}),flush=True)
    fields=sorted({k for r in seeds for k in r}); tf=sorted({k for r in trades for k in r})
    with (OUT/'v444_semantic_seeds.csv').open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(seeds)
    with (OUT/'v444_frozen_t1_trades.csv').open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=tf); w.writeheader(); w.writerows(trades)
    summary={}
    for onto in ('INTERNAL_LIQUIDITY_TRANSFER','BEAR_IFVG_ROLE_REVERSAL'):
        rs=[r for r in trades if r['ontology']==onto]; yearly={y:stats([r for r in rs if r['entry_date'][:4]==y]) for y in YEARS}; overall=stats(rs); t1=sum(bool(r['t1_violation']) for r in rs)
        summary[onto]={'overall':overall,'yearly':yearly,'exit_reasons':dict(Counter(r['exit_reason'] for r in rs)),'t1_violations':t1,'promotion_gate_pass':pass_gate(overall,yearly,t1)}
    report={'version':'V444_INTERNAL_LIQUIDITY_IFVG_FRONTIER_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'frozen_contracts':{'INTERNAL_LIQUIDITY_TRANSFER':'external HH/HL -> confirmed internal high/HL -> internal-low sweep while external low holds -> internal-high displacement -> next open','BEAR_IFVG_ROLE_REVERSAL':'bear FVG -> close above gap -> later retest -> later reclaim -> later hold -> next open','execution':'zone_low*0.99 SL; nearest pre-entry confirmed external swing-high target; time30; strict T+1; same-bar collision=SL'},
      'promotion_gate':GATE,'symbols_scanned':scanned,'seed_counts':dict(counts),'semantic_order_failures':sum(not r['semantic_order_valid'] for r in seeds),'duplicate_symbol_entry_ontology':len(seeds)-len(set((r['symbol'],r['eligible_entry_date'],r['ontology']) for r in seeds)),
      'summary':summary,'decision':('AT_LEAST_ONE_NEW_ONTOLOGY_PASSES_RESEARCH_GATE' if any(x['promotion_gate_pass'] for x in summary.values()) else 'BOTH_NEW_ONTOLOGIES_FAIL_FROZEN_ECONOMIC_GATE'),
      'artifacts':{'out_dir':str(OUT),'seeds':str(OUT/'v444_semantic_seeds.csv'),'trades':str(OUT/'v444_frozen_t1_trades.csv'),'latest':str(LATEST)}}
    text=json.dumps(report,ensure_ascii=False,indent=2); (OUT/'v444_report.json').write_text(text); LATEST.write_text(text); print(text)
if __name__=='__main__': main()
