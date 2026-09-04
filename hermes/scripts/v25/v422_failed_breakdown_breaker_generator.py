#!/usr/bin/env python3
"""V422 no-write failed-breakdown breaker lifecycle generator.

Story: confirmed swing-low -> bearish close-through -> rapid recovery above the
broken level -> close above breakdown-candle high -> first breaker retest,
reclaim and hold. This captures close-through traps excluded by wick-only sweep.
"""
from __future__ import annotations
import csv, json, math
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
OUT=AUD/f'v422_failed_breakdown_breaker_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST=AUD/'v422_failed_breakdown_breaker_latest.json'

def f(x):
    try:
        v=float(x); return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError): return 0.0

def day(b): return ''.join(c for c in str(b.get('t') or b.get('date') or '') if c.isdigit())[:8]
def sym(path):
    p=path.name.replace('_daily_750.json','').split('_'); return f'{p[0]}.{p[1]}'
def load(path):
    try: raw=json.loads(path.read_text())
    except Exception: return []
    return sorted([b for b in raw if day(b) and all(f(b.get(k))>0 for k in ('o','h','l','c'))],key=day)
def swing_lows(ks):
    out=[]
    for i in range(3,len(ks)-3):
        lo=f(ks[i]['l'])
        if all(lo<f(ks[j]['l']) for j in range(i-3,i+4) if j!=i): out.append((i,lo,i+3))
    return out
def lifecycle(ks,start,low,high):
    touch=reclaim=None
    for i in range(start+1,min(len(ks),start+31)):
        lo,cl=f(ks[i]['l']),f(ks[i]['c'])
        if cl<low: return 'CANCEL_BREAKER_INVALIDATED',i,touch,reclaim
        if touch is None:
            if lo<=high: touch=i
            continue
        if reclaim is None:
            if cl>high: reclaim=i
            continue
        if cl>high and lo>=low: return 'TAKEOVER_CONFIRMED',i,touch,reclaim
    full=start+30<len(ks)
    if touch is None: return ('EXPIRE_NO_TOUCH_30B' if full else 'WAIT_TOUCH_UNOBSERVED'),None,None,None
    if reclaim is None: return ('EXPIRE_NO_RECLAIM_30B' if full else 'WAIT_RECLAIM_UNOBSERVED'),None,touch,None
    return ('EXPIRE_NO_HOLD_30B' if full else 'WAIT_HOLD_UNOBSERVED'),None,touch,reclaim

def scan(path_s):
    path=Path(path_s); ks=load(path); rows=[]; cnt=Counter()
    if len(ks)<80: return rows,cnt
    lows=swing_lows(ks); used=set()
    for break_i in range(30,len(ks)):
        visible=[x for x in lows if x[2]<=break_i and break_i-x[0]<=60 and x[0] not in used]
        if not visible: continue
        pivot_i,level,confirm_i=max(visible,key=lambda x:x[0]); b=ks[break_i]
        if not (f(b['c'])<level*.998 and f(b['c'])<f(b['o'])): continue
        used.add(pivot_i); cnt['CONFIRMED_CLOSE_BREAKDOWN']+=1
        rec=next((j for j in range(break_i+1,min(len(ks),break_i+6)) if f(ks[j]['c'])>level*1.001),None)
        if rec is None: cnt['NO_RECOVERY_5B']+=1; continue
        sos=next((j for j in range(rec+1,min(len(ks),rec+11)) if f(ks[j]['c'])>f(b['h'])*1.002),None)
        if sos is None: cnt['NO_BREAKER_SOS_10B']+=1; continue
        zone_low,zone_high=f(b['c']),f(b['o'])
        status,end_i,touch,reclaim=lifecycle(ks,sos,zone_low,zone_high)
        at=lambda i: day(ks[i]) if i is not None else ''
        rows.append({'symbol':sym(path),'combo_key':'R4_FAILED_BREAKDOWN_BREAKER_LPS',
          'pivot_idx':pivot_i,'pivot_date':at(pivot_i),'pivot_price':round(level,6),'pivot_confirm_idx':confirm_i,
          'break_idx':break_i,'break_date':at(break_i),'break_low':round(f(b['l']),6),
          'recovery_idx':rec,'recovery_date':at(rec),'sos_idx':sos,'sos_date':at(sos),
          'zone_low':round(zone_low,6),'zone_high':round(zone_high,6),'lifecycle_state':status,
          'touch_idx':'' if touch is None else touch,'touch_date':at(touch),
          'reclaim_idx':'' if reclaim is None else reclaim,'reclaim_date':at(reclaim),
          'takeover_idx':'' if status!='TAKEOVER_CONFIRMED' else end_i,
          'takeover_date':at(end_i) if status=='TAKEOVER_CONFIRMED' else '',
          'semantic_contract':'confirmed swing low -> bearish close-through -> recovery -> breaker SOS -> retest -> reclaim -> hold',
          'tradable':'false','buy_enabled':'false','outcome_fields_present':'false'})
        cnt['SEMANTIC_CANDIDATE']+=1; cnt[status]+=1
    cnt['SYMBOL_SCANNED']+=1; return rows,cnt

def main():
    OUT.mkdir(parents=True,exist_ok=True); rows=[]; counts=Counter()
    paths=[str(p) for p in sorted(KDIR.glob('*_daily_750.json'))]
    with ProcessPoolExecutor(max_workers=12) as pool:
        for part,c in pool.map(scan,paths,chunksize=20): rows.extend(part); counts.update(c)
    rp=OUT/'v422_lifecycle_rows.csv'; fields=list(rows[0]) if rows else ['symbol','combo_key']
    with rp.open('w',newline='') as h: w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(rows)
    stages=Counter(r['lifecycle_state'] for r in rows)
    report={'version':'V422_FAILED_BREAKDOWN_BREAKER_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),
      'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'scope':'new pure-structure semantic generator only; no entries, exits, PnL, marks, or promotion',
      'frozen_contract':{'breakdown':'nearest visible unbroken 3L/3R swing low within 60 bars; bearish close 0.2% below',
       'recovery':'close 0.1% back above broken level within 5 bars','sos':'later close 0.2% above breakdown-candle high within 10 bars',
       'breaker':'breakdown candle body; post-SOS touch -> later reclaim -> hold; close below body low cancels'},
      'stage_counts':dict(counts),'lifecycle':dict(stages),'takeover_confirmed':stages['TAKEOVER_CONFIRMED'],
      'takeover_rate_pct':round(stages['TAKEOVER_CONFIRMED']/len(rows)*100,4) if rows else 0,
      'invariants':{'all_rows_non_tradable':all(r['tradable']=='false' for r in rows),'no_outcome_fields':all(r['outcome_fields_present']=='false' for r in rows)},
      'decision':'SEMANTIC_GENERATOR_READY__ONE_FROZEN_T1_STRUCTURAL_REPLAY_NEXT',
      'artifacts':{'out_dir':str(OUT),'rows':str(rp),'latest':str(LATEST)}}
    text=json.dumps(report,ensure_ascii=False,indent=2); (OUT/'v422_report.json').write_text(text); LATEST.write_text(text); print(text)
if __name__=='__main__': main()
