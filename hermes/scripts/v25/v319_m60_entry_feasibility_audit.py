#!/usr/bin/env python3
"""V319 no-write audit: 60min cache coverage and intraday entry feasibility.

After V315-V318 closed row-level scalar / exit / broader candidate-supply paths,
this tests whether the next information source (60min cache) is actually usable
for multi-year production research and whether same-day 60min limit/reclaim entry
would materially improve RR on rows where data exists.
"""
from __future__ import annotations

import json, math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median

ROOT=Path('/root/.hermes')
V185=ROOT/'smc_opt_v185_combined_production_candidate/v185_trades.json'
K60=ROOT/'kline_cache_60min'
AUD=ROOT/'smc_audit'
TS=datetime.now().strftime('%Y%m%d_%H%M%S')
OUTDIR=AUD/f'v319_m60_entry_feasibility_no_write_{TS}'
LATEST=AUD/'v319_m60_entry_feasibility_latest.json'

def f(x, default=None):
    try:
        if x in (None,''): return default
        v=float(x)
        return default if math.isnan(v) or math.isinf(v) else v
    except Exception:
        return default

def dkey(v):
    s=''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s)>=8 else ''

def load60(sym):
    if not sym or '.' not in sym: return []
    code,ex=sym.split('.')
    p=K60/f'{code}_{ex}_60min_500.json'
    if not p.exists(): return []
    try: data=json.load(open(p))
    except Exception: return []
    out=[]
    for b in data if isinstance(data,list) else []:
        t=str(b.get('t') or b.get('date') or '')
        o,h,l,c=f(b.get('o')),f(b.get('h')),f(b.get('l')),f(b.get('c'))
        if len(t)>=8 and None not in (o,h,l,c): out.append({'t':t,'date':t[:8],'o':o,'h':h,'l':l,'c':c})
    return sorted(out,key=lambda x:x['t'])

def pct(a,b):
    return None if a is None or b in (None,0) else (a/b-1)*100

def metrics(rows):
    n=len(rows)
    if not n: return {'n':0}
    vals=[r['pnl_pct'] for r in rows]
    yrs=defaultdict(list)
    for r,p in zip(rows,vals): yrs[str(r['entry_date'])[:4]].append(p)
    yc={y:len(v) for y,v in sorted(yrs.items())}
    yw={y:round(sum(x>=0.8 for x in v)/len(v)*100,4) for y,v in sorted(yrs.items())}
    return {'n':n,'wr':round(sum(x>=0.8 for x in vals)/n*100,4),'avg':round(mean(vals),4),'median':round(median(vals),4),'min_year_n':min(yc.values()) if yc else 0,'year_counts':yc,'year_wr':yw,'all_year_wr_min':round(min(yw.values()),4) if yw else 0,'loss_pct':round(sum(x<0 for x in vals)/n*100,4)}

def simulate_limit(row, entry, reason):
    old_entry=f(row.get('entry_price'))
    old_sl=f(row.get('sl') or row.get('sl_price'))
    if not old_entry or not old_sl or old_sl>=old_entry or entry<=old_sl: return None
    risk=entry-old_sl
    tp=entry+risk*1.5
    bars=[]
    # daily T+1 path from local daily via simple import from v316
    import importlib.util
    spec=importlib.util.spec_from_file_location('v316','/root/.hermes/scripts/v25/v316_v185_exit_mechanism_frontier_audit.py')
    v316=importlib.util.module_from_spec(spec); spec.loader.exec_module(v316)
    path=v316.t1_path(row)
    if not path: return None
    best=-1e18; worst=1e18
    for i,b in enumerate(path,1):
        best=max(best,b['h']); worst=min(worst,b['l'])
        if b['o']<=old_sl:
            pnl=pct(b['o'],entry); return {'symbol':row.get('symbol'),'entry_date':dkey(row.get('entry_date')),'pnl_pct':round(pnl,4),'exit_reason':'GAP_SL','entry_mode':reason,'mfe_r':round((best-entry)/risk,4),'mae_r':round((worst-entry)/risk,4),'same_day_exit_violation':False}
        if b['l']<=old_sl:
            pnl=pct(old_sl,entry); return {'symbol':row.get('symbol'),'entry_date':dkey(row.get('entry_date')),'pnl_pct':round(pnl,4),'exit_reason':'SL','entry_mode':reason,'mfe_r':round((best-entry)/risk,4),'mae_r':round((worst-entry)/risk,4),'same_day_exit_violation':False}
        if b['h']>=tp:
            pnl=pct(tp,entry); return {'symbol':row.get('symbol'),'entry_date':dkey(row.get('entry_date')),'pnl_pct':round(pnl,4),'exit_reason':'TP','entry_mode':reason,'mfe_r':round((best-entry)/risk,4),'mae_r':round((worst-entry)/risk,4),'same_day_exit_violation':False}
        if i>=10:
            pnl=pct(b['c'],entry); return {'symbol':row.get('symbol'),'entry_date':dkey(row.get('entry_date')),'pnl_pct':round(pnl,4),'exit_reason':'TIME','entry_mode':reason,'mfe_r':round((best-entry)/risk,4),'mae_r':round((worst-entry)/risk,4),'same_day_exit_violation':False}
    b=path[-1]; pnl=pct(b['c'],entry)
    return {'symbol':row.get('symbol'),'entry_date':dkey(row.get('entry_date')),'pnl_pct':round(pnl,4),'exit_reason':'OPEN_MARK','entry_mode':reason,'mfe_r':round((best-entry)/risk,4),'mae_r':round((worst-entry)/risk,4),'same_day_exit_violation':False}

def main():
    OUTDIR.mkdir(parents=True,exist_ok=True)
    rows=json.load(open(V185))
    coverage=[]; limit_rows=[]; reclaim_rows=[]
    for r in rows:
        sym=r.get('symbol'); ed=dkey(r.get('entry_date')); bars=load60(sym)
        before=[b for b in bars if b['date']<=ed]
        same=[b for b in bars if b['date']==ed]
        after=[b for b in bars if b['date']>=ed]
        zl,zh,ep=f(r.get('zone_low') or r.get('dz_low')),f(r.get('zone_high') or r.get('dz_high')),f(r.get('entry_price'))
        cov={'symbol':sym,'entry_date':ed,'has_file':bool(bars),'bars':len(bars),'first':bars[0]['t'] if bars else '', 'last':bars[-1]['t'] if bars else '', 'entry_day_bars':len(same),'has_entry_day':bool(same),'year':ed[:4]}
        coverage.append(cov)
        if same and zl and zh and ep:
            lows=[b['l'] for b in same]; closes=[b['c'] for b in same]
            # feasible only if same-day 60min actually traded near zone; execution still exits T+1 in replay.
            touched=[b for b in same if b['l']<=zh and b['h']>=zl]
            if touched:
                entry=min(ep, zh)  # optimistic but executable zone-high touch; still no future exit leak
                sim=simulate_limit(r,entry,'M60_SAME_DAY_ZONE_LIMIT_HIGH')
                if sim: limit_rows.append(sim)
            reclaimed=[b for b in same if b['l']<=zh and b['c']>=zh]
            if reclaimed:
                entry=min(ep, reclaimed[0]['c'])
                sim=simulate_limit(r,entry,'M60_SAME_DAY_RECLAIM_CLOSE')
                if sim: reclaim_rows.append(sim)
    by_year=Counter(c['year'] for c in coverage)
    has_by_year=Counter(c['year'] for c in coverage if c['has_entry_day'])
    coverage_summary={'rows':len(rows),'m60_file_rows':sum(c['has_file'] for c in coverage),'entry_day_rows':sum(c['has_entry_day'] for c in coverage),'by_year':dict(by_year),'entry_day_by_year':dict(has_by_year),'entry_day_pct':round(sum(c['has_entry_day'] for c in coverage)/len(rows)*100,2)}
    base=[{'symbol':r.get('symbol'),'entry_date':dkey(r.get('entry_date')),'pnl_pct':f(r.get('pnl_pct'),0),'exit_reason':r.get('exit_reason')} for r in rows]
    report={'version':'V319_M60_ENTRY_FEASIBILITY_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'input':str(V185),'m60_cache':str(K60),'coverage':coverage_summary,'baseline_v185':metrics(base),'m60_zone_limit_rows':metrics(limit_rows),'m60_reclaim_rows':metrics(reclaim_rows),'decision':'M60_CACHE_NOT_MULTIYEAR_PRODUCTION_USABLE__DO_NOT_ITERATE_M60_FULL_BACKTEST' if coverage_summary['entry_day_rows']<250 or min(has_by_year.values() or [0])<40 else 'M60_CACHE_COVERAGE_OK__CAN_RUN_FULL_M60_MATRIX','artifacts':{'report':str(OUTDIR/'v319_report.json'),'coverage_rows':str(OUTDIR/'v319_coverage_rows.json'),'limit_rows':str(OUTDIR/'v319_limit_rows.json'),'reclaim_rows':str(OUTDIR/'v319_reclaim_rows.json'),'latest':str(LATEST)}}
    json.dump(report,open(OUTDIR/'v319_report.json','w'),ensure_ascii=False,indent=2)
    json.dump(coverage,open(OUTDIR/'v319_coverage_rows.json','w'),ensure_ascii=False,indent=2)
    json.dump(limit_rows,open(OUTDIR/'v319_limit_rows.json','w'),ensure_ascii=False,indent=2)
    json.dump(reclaim_rows,open(OUTDIR/'v319_reclaim_rows.json','w'),ensure_ascii=False,indent=2)
    json.dump(report,open(LATEST,'w'),ensure_ascii=False,indent=2)
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
