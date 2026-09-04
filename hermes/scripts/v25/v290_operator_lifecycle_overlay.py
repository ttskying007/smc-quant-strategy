#!/usr/bin/env python3
"""V290 no-write: operator lifecycle overlay on same-source 60m-first rows.

Adds pre-entry lifecycle evidence to V288 rows: accumulation compression, manipulation
sweep depth, MSS impulse, same-day post-MSS hold/retest. This tests whether the
missing layer is not more parameter tuning but active operator lifecycle state.
"""
from __future__ import annotations
import csv, json, math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
BASE=Path('/root/.hermes'); AUDIT=BASE/'smc_audit'; K60=BASE/'kline_cache_60min'
V288=json.loads((AUDIT/'v288_same_source_60m_first_latest.json').read_text()); ROWS=Path(V288['artifacts']['best_rows'])
TS=datetime.now().strftime('%Y%m%d_%H%M%S'); OUT=AUDIT/f'v290_operator_lifecycle_overlay_no_write_{TS}'; LATEST=AUDIT/'v290_operator_lifecycle_overlay_latest.json'

def sf(x:Any,d=math.nan):
    try:
        if x is None or x=='': return d
        v=float(x); return v if not math.isnan(v) else d
    except Exception: return d

def dn(x):
    s=''.join(ch for ch in str(x or '').replace('-','') if ch.isdigit()); return s[:8] if len(s)>=8 else ''

def path60(sym):
    code,ex=sym.split('.'); return K60/f'{code}_{ex}_60min_500.json'

def brange(x):
    if math.isnan(x): return 'ACC_NA'
    if x<4: return 'ACC_TIGHT<4'
    if x<7: return 'ACC_MID4_7'
    return 'ACC_WIDE>=7'

def bdepth(x):
    if math.isnan(x): return 'SWP_NA'
    if x<1: return 'SWP_SHALLOW<1'
    if x<3: return 'SWP_MID1_3'
    return 'SWP_DEEP>=3'

def bimp(x):
    if math.isnan(x): return 'IMP_NA'
    if x<0.5: return 'IMP_WEAK<0.5'
    if x<1.5: return 'IMP_MID0.5_1.5'
    return 'IMP_STRONG>=1.5'

def bhold(x):
    if math.isnan(x): return 'HOLD_NA'
    if x<0: return 'HOLD_FAIL'
    if x<1: return 'HOLD_THIN0_1'
    return 'HOLD_STRONG>=1'

def blank(): return {'n':0,'wins':0,'sum':0.0,'loss':0,'micro':0,'tp':0,'sl':0,'gap_sl':0,'time':0,'years':defaultdict(lambda:[0,0]),'months':defaultdict(lambda:[0,0]),'symbols':set()}

def add(a,r):
    pnl=sf(r.get('pnl'),0); reason=str(r.get('reason',''))
    a['n']+=1; a['wins']+=pnl>0; a['sum']+=pnl; a['loss']+=pnl<=0; a['micro']+=0<pnl<1
    a['tp']+=reason=='TP'; a['sl']+=reason=='SL'; a['gap_sl']+=reason=='GAP_SL'; a['time']+=reason.startswith('TIME')
    y=r['entry_date'][:4]; m=r['entry_date'][:6]; a['years'][y][0]+=1; a['years'][y][1]+=pnl>0; a['months'][m][0]+=1; a['months'][m][1]+=pnl>0; a['symbols'].add(r['symbol'])

def metrics(a,stock_count):
    n=a['n']
    if not n: return {'n':0}
    yc={y:int(v[0]) for y,v in sorted(a['years'].items())}; ywr={y:round(v[1]/v[0]*100,2) for y,v in sorted(a['years'].items())}
    mc={m:int(v[0]) for m,v in sorted(a['months'].items())}; mwr={m:round(v[1]/v[0]*100,2) for m,v in sorted(a['months'].items())}
    return {'n':int(n),'wr':round(a['wins']/n*100,4),'avg':round(a['sum']/n,4),'loss':int(a['loss']),'micro':round(a['micro']/n*100,2),'tp_pct':round(a['tp']/n*100,2),'sl_pct':round(a['sl']/n*100,2),'gap_sl_pct':round(a['gap_sl']/n*100,2),'time_pct':round(a['time']/n*100,2),'symbols':len(a['symbols']),'per_stock':round(n/stock_count,4),'year_counts':yc,'year_wr':ywr,'min_year_n':min(yc.values()) if yc else 0,'min_year_wr':round(min(ywr.values()) if ywr else 0,2),'month_count':len(mc),'min_month_n':min(mc.values()) if mc else 0,'min_month_wr':round(min(mwr.values()) if mwr else 0,2)}

def enrich(r, cache):
    sym=r['symbol']
    if sym not in cache:
        p=path60(sym); cache[sym]=json.loads(p.read_text()) if p.exists() else []
    bars=cache[sym]; sweep=int(float(r['sweep_i60'])); mss=int(float(r['mss_i60'])); zl=sf(r['zone_low'])
    out=dict(r)
    if not bars or sweep<25 or mss>=len(bars): return out
    pre=bars[max(0,sweep-20):sweep]
    hs=[sf(b.get('h')) for b in pre]; ls=[sf(b.get('l')) for b in pre]; vs=[sf(b.get('v'),0) for b in pre]
    if hs and ls and min(ls)>0: out['acc_range_pct']=(max(hs)/min(ls)-1)*100
    if vs:
        out['acc_vol_med']=sorted(vs)[len(vs)//2]
    out['sweep_depth2']=sf(r.get('sweep_depth'))
    out['mss_impulse']=sf(r.get('local_high_break'))
    sig_day=dn(r.get('signal_time'))
    post=[b for b in bars[mss+1:min(len(bars),mss+5)] if dn(b.get('t'))==sig_day]
    if post and zl>0:
        out['post_hold_min_pct']=(min(sf(b.get('l')) for b in post)/zl-1)*100
        out['post_close_pos_pct']=(sf(post[-1].get('c'))/zl-1)*100
    else:
        out['post_hold_min_pct']=math.nan; out['post_close_pos_pct']=math.nan
    acc=brange(sf(out.get('acc_range_pct'))); sw=bdepth(sf(out.get('sweep_depth2'))); imp=bimp(sf(out.get('mss_impulse'))); hold=bhold(sf(out.get('post_hold_min_pct')))
    if acc=='ACC_TIGHT<4' and sw!='SWP_SHALLOW<1' and imp!='IMP_WEAK<0.5' and hold.startswith('HOLD_STRONG'):
        stage='FULL_ACC_MAN_TAKEOVER_HOLD'
    elif sw!='SWP_SHALLOW<1' and imp!='IMP_WEAK<0.5' and not hold.startswith('HOLD_FAIL'):
        stage='MAN_TAKEOVER_NO_ACC'
    elif hold.startswith('HOLD_FAIL'):
        stage='TAKEOVER_FAILS_SAMEDAY'
    else:
        stage='PARTIAL_OR_WEAK'
    out.update({'acc_bucket':acc,'sweep_bucket':sw,'impulse_bucket':imp,'hold_bucket':hold,'lifecycle_stage':stage})
    return out

def main():
    OUT.mkdir(parents=True,exist_ok=True); rows=[]; cache={}
    with ROWS.open() as f:
        for r in csv.DictReader(f): rows.append(enrich(r,cache))
    stock_count=len({r['symbol'] for r in rows}); raw=blank(); ag=defaultdict(blank)
    for r in rows:
        add(raw,r)
        dims={'stage':r.get('lifecycle_stage','NA'),'acc+sweep+imp':f"{r.get('acc_bucket')}|{r.get('sweep_bucket')}|{r.get('impulse_bucket')}",'stage+risk':f"{r.get('lifecycle_stage')}|{r.get('risk_bucket')}",'stage+gap':f"{r.get('lifecycle_stage')}|{r.get('gap_bucket')}",'hold':r.get('hold_bucket','NA'),'acc':r.get('acc_bucket','NA')}
        for dim,val in dims.items(): add(ag[(dim,val)],r)
    surfaces=[]
    for (dim,val),a in ag.items():
        m=metrics(a,stock_count)
        if m['n']>=25: surfaces.append({'dimension':dim,'value':val,**m})
    surfaces.sort(key=lambda x:(x['min_year_wr'],x['wr'],x['avg'],x['n']), reverse=True)
    out_rows=OUT/'v290_enriched_rows.csv'
    with out_rows.open('w',newline='') as f:
        fields=list(rows[0].keys()); w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    summary={'version':'V290_OPERATOR_LIFECYCLE_OVERLAY_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source_rows':str(ROWS),'rows':len(rows),'raw':metrics(raw,stock_count),'best_large':next((x for x in surfaces if x['n']>=100 and x['min_year_n']>=20),surfaces[0] if surfaces else None),'top_surfaces':surfaces[:50],'artifacts':{'out_dir':str(OUT),'enriched_rows':str(out_rows)}}
    (OUT/'v290_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)); LATEST.write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps({'latest':str(LATEST),'raw':summary['raw'],'best_large':summary['best_large'],'top10':surfaces[:10]},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
