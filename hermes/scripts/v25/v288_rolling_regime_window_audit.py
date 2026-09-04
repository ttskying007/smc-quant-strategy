#!/usr/bin/env python3
"""V288 no-write: rolling market/industry regime windows for the V287 pocket.

V287 found a high-quality but low-volume pocket:
UP_CONT_BOS_OB + DOWN + previous-day market/industry strength. The bad months
suggest previous-day strength alone is too myopic. Test entry-before rolling
3/5/10/20-day market and industry participation windows.
"""
from __future__ import annotations

import bisect, csv, importlib.util, json, math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

BASE = Path('/root/.hermes')
AUDIT = BASE / 'smc_audit'
KDIR = BASE / 'kline_cache'
EVENTS = AUDIT / 'v280_layered_state_grammar_no_write_20260702_205055/v280_events.csv'
INDMAP = AUDIT / 'v225_baostock_industry_participation_probe_20260627_031854/baostock_stock_industry.json'
V286 = BASE / 'scripts/v25/v286_parent_regime_walkforward_audit.py'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v288_rolling_regime_window_no_write_{TS}'
LATEST = AUDIT / 'v288_rolling_regime_window_latest.json'
WINDOWS = [3, 5, 10, 20]

spec = importlib.util.spec_from_file_location('v286_mod', V286)
v286 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v286)  # type: ignore[union-attr]


def sf(x: Any, d: float = math.nan) -> float:
    return v286.sf(x, d)


def blank():
    return {'n':0,'wins':0,'sum':0.0,'loss':0,'tp':0,'sl':0,'time':0,'micro':0,'years':defaultdict(lambda:[0,0]),'symbols':set()}


def add(a, r):
    pnl=sf(r.get('pnl'),0.0); y=str(r.get('year') or v286.dn(r.get('entry_date'))[:4]); reason=str(r.get('reason') or '')
    a['n']+=1; a['wins']+=pnl>0; a['sum']+=pnl; a['loss']+=pnl<=0; a['tp']+=reason=='TP'; a['sl']+=reason=='SL'; a['time']+=reason.startswith('TIME'); a['micro']+=0<pnl<1
    a['years'][y][0]+=1; a['years'][y][1]+=pnl>0; a['symbols'].add(r.get('symbol',''))


def metrics(a):
    n=int(a['n'])
    if not n: return {'n':0}
    yc={y:int(v[0]) for y,v in sorted(a['years'].items()) if v[0]}; ywr={y:round(v[1]/v[0]*100,2) for y,v in sorted(a['years'].items()) if v[0]}
    return {'n':n,'wr':round(a['wins']/n*100,4),'avg':round(a['sum']/n,4),'loss':int(a['loss']),'micro':round(a['micro']/n*100,2),'tp_pct':round(a['tp']/n*100,2),'sl_pct':round(a['sl']/n*100,2),'time_pct':round(a['time']/n*100,2),'symbols':len(a['symbols']),'yc':yc,'ywr':ywr,'min_year_n':min(yc.values()) if yc else 0,'minwr':round(min(ywr.values()) if ywr else 0,2)}


def load_industry_map():
    return {r['symbol']: r.get('industry') or 'UNKNOWN' for r in json.loads(INDMAP.read_text()) if r.get('symbol')}


def build_daily_ret_tables(sym_ind):
    daily=defaultdict(list); ind_daily=defaultdict(lambda: defaultdict(list))
    for fp in KDIR.glob('*_daily_750.json'):
        try: sym=v286.symbol_from_path(fp)
        except Exception: continue
        ind=sym_ind.get(sym)
        if not ind: continue
        try: bars=json.loads(fp.read_text())
        except Exception: continue
        seq=[]
        for b in bars:
            d=v286.dn(b.get('t') or b.get('date')); c=sf(b.get('c'))
            if d and not math.isnan(c): seq.append((d,c))
        seq.sort()
        for i in range(1,len(seq)):
            d,c=seq[i]; pc=seq[i-1][1]
            if pc>0:
                ret=(c/pc-1)*100; daily[d].append(ret); ind_daily[d][ind].append(ret)
    dates=sorted(daily)
    mkt_day={}
    ind_day={}
    for d, vals in daily.items():
        mkt_day[d]={'med_ret':median(vals),'up_pct':sum(v>0 for v in vals)/len(vals)*100,'strong1_pct':sum(v>1 for v in vals)/len(vals)*100,'n':len(vals)}
    for d, mp in ind_daily.items():
        for ind, vals in mp.items():
            if len(vals)>=5:
                ind_day[(d,ind)]={'med_ret':median(vals),'up_pct':sum(v>0 for v in vals)/len(vals)*100,'strong1_pct':sum(v>1 for v in vals)/len(vals)*100,'n':len(vals)}
    return dates, mkt_day, ind_day


def mean(xs):
    xs=[x for x in xs if not math.isnan(x)]
    return sum(xs)/len(xs) if xs else math.nan


def enrich_rows():
    sym_ind=load_industry_map(); dates,mkt_day,ind_day=build_daily_ret_tables(sym_ind)
    rows=[]
    with EVENTS.open(newline='') as f:
        for r in csv.DictReader(f):
            if r.get('year') not in {'2023','2024','2025','2026'}: continue
            sym=r['symbol']; ind=sym_ind.get(sym,'UNKNOWN'); d=v286.dn(r.get('entry_date'))
            idx=bisect.bisect_left(dates,d)
            nr=dict(r); nr['industry']=ind
            for w in WINDOWS:
                ds=dates[max(0,idx-w):idx]
                nr[f'mkt{w}_med_ret_avg']=mean([mkt_day[x]['med_ret'] for x in ds if x in mkt_day])
                nr[f'mkt{w}_up_avg']=mean([mkt_day[x]['up_pct'] for x in ds if x in mkt_day])
                nr[f'mkt{w}_strong1_avg']=mean([mkt_day[x]['strong1_pct'] for x in ds if x in mkt_day])
                nr[f'ind{w}_med_ret_avg']=mean([ind_day[(x,ind)]['med_ret'] for x in ds if (x,ind) in ind_day])
                nr[f'ind{w}_up_avg']=mean([ind_day[(x,ind)]['up_pct'] for x in ds if (x,ind) in ind_day])
                nr[f'ind{w}_strong1_avg']=mean([ind_day[(x,ind)]['strong1_pct'] for x in ds if (x,ind) in ind_day])
            rows.append(nr)
    return rows


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    rows=enrich_rows()
    def base(r): return r['family']=='UP_CONT_BOS_OB' and r['regime']=='DOWN'
    def risk8(r): return sf(r.get('risk'))>=8
    aggs=defaultdict(blank)
    for r in rows:
        if r['year'] not in {'2024','2025','2026'}: continue
        if not base(r): continue
        add(aggs[('BASE_UPCONT_DOWN','ALL')],r)
        if risk8(r): add(aggs[('BASE_UPCONT_DOWN_RISK8','ALL')],r)
        for w in WINDOWS:
            mret=sf(r.get(f'mkt{w}_med_ret_avg')); iret=sf(r.get(f'ind{w}_med_ret_avg'))
            mup=sf(r.get(f'mkt{w}_up_avg')); iup=sf(r.get(f'ind{w}_up_avg'))
            ms1=sf(r.get(f'mkt{w}_strong1_avg')); is1=sf(r.get(f'ind{w}_strong1_avg'))
            conds={
                f'W{w}_RET_POS': mret>0 and iret>0,
                f'W{w}_RET_STRONG_0_5': mret>=0.5 and iret>=0.5,
                f'W{w}_UP55': mup>=55 and iup>=55,
                f'W{w}_UP60': mup>=60 and iup>=60,
                f'W{w}_STRONG1_25': ms1>=25 and is1>=25,
                f'W{w}_RET_POS_UP55': mret>0 and iret>0 and mup>=55 and iup>=55,
                f'W{w}_RET_STRONG_UP60': mret>=0.5 and iret>=0.5 and mup>=60 and iup>=60,
            }
            for name, ok in conds.items():
                if ok:
                    add(aggs[('UPCONT_DOWN_ROLLING',name)],r)
                    if risk8(r): add(aggs[('UPCONT_DOWN_RISK8_ROLLING',name)],r)
    rows_out=[]
    for (dim,val),a in aggs.items():
        m=metrics(a)
        if m['n']>=25:
            rows_out.append({'dimension':dim,'value':val,**m})
    rows_out.sort(key=lambda x:(x['minwr'],x['wr'],x['avg'],x['n']), reverse=True)
    summary={'version':'V288_ROLLING_REGIME_WINDOW_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'inputs':{'events':str(EVENTS),'industry_map':str(INDMAP),'rows':len(rows),'windows':WINDOWS},'top_surfaces':rows_out[:80],'artifacts':{'summary':str(OUT/'v288_summary.json')}}
    (OUT/'v288_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)); LATEST.write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    with (OUT/'v288_surfaces.csv').open('w',newline='') as f:
        fields=['dimension','value','n','wr','avg','min_year_n','minwr','tp_pct','sl_pct','time_pct','symbols','yc','ywr']
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); [w.writerow({k:r.get(k) for k in fields}) for r in rows_out]
    print(json.dumps({'latest':str(LATEST),'out':str(OUT),'top':rows_out[:20]},ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
