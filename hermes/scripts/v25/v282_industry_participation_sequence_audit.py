#!/usr/bin/env python3
"""V282 no-write audit: real industry participation overlay on V280 layered SMC grammar.

Purpose: continue the "too few opportunities" investigation by testing whether
chronological SMC grammar quality depends on market/industry participation known
before entry.  No production/frontend/watchlist writes.
"""
from __future__ import annotations
import csv, json, math, bisect
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median

BASE = Path('/root/.hermes')
KDIR = BASE / 'kline_cache'
AUDIT = BASE / 'smc_audit'
V280_DIR = AUDIT / 'v280_layered_state_grammar_no_write_20260702_205055'
EVENTS_CSV = V280_DIR / 'v280_events.csv'
INDMAP = AUDIT / 'v225_baostock_industry_participation_probe_20260627_031854/baostock_stock_industry.json'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v282_industry_participation_sequence_no_write_{TS}'
LATEST = AUDIT / 'v282_industry_participation_sequence_latest.json'
YEARS = ['2023','2024','2025','2026']


def sf(x, default=math.nan):
    try:
        if x is None or x == '': return default
        v = float(x)
        return v if not math.isnan(v) else default
    except Exception:
        return default


def dn(x):
    s = ''.join(ch for ch in str(x or '').replace('-', '')[:12] if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def symbol_from_path(p: Path) -> str:
    stem = p.stem.replace('_daily_750','')
    code, exch = stem.split('_',1)
    return f'{code}.{exch}'


def blank():
    return {'n':0,'wins':0,'sum':0.0,'loss':0,'micro':0,'tp':0,'sl':0,'time':0,'years':defaultdict(lambda:[0,0]),'symbols':set()}


def add(a, r):
    pnl = sf(r.get('pnl'),0.0); y = str(r.get('year') or dn(r.get('entry_date'))[:4]); reason=str(r.get('reason',''))
    a['n'] += 1; a['wins'] += pnl > 0; a['sum'] += pnl; a['loss'] += pnl <= 0; a['micro'] += 0 < pnl < 1
    a['tp'] += reason == 'TP'; a['sl'] += reason == 'SL'; a['time'] += reason.startswith('TIME')
    a['years'][y][0] += 1; a['years'][y][1] += pnl > 0; a['symbols'].add(r.get('symbol',''))


def metrics(a):
    n=a['n']
    if not n: return {'n':0}
    yc={y:int(a['years'][y][0]) for y in sorted(a['years']) if a['years'][y][0]}
    ywr={y:round(a['years'][y][1]/a['years'][y][0]*100,2) for y in sorted(a['years']) if a['years'][y][0]}
    return {'n':int(n),'wr':round(a['wins']/n*100,2),'avg':round(a['sum']/n,3),'loss':int(a['loss']),
            'micro':round(a['micro']/n*100,2),'tp_pct':round(a['tp']/n*100,2),'sl_pct':round(a['sl']/n*100,2),
            'time_pct':round(a['time']/n*100,2),'symbols':len(a['symbols']),'yc':yc,'ywr':ywr,
            'min_year_n':min(yc.values()) if yc else 0,'minwr':round(min(ywr.values()) if ywr else 0,2)}


def bucket_up(x):
    if math.isnan(x): return 'NA'
    if x < 35: return 'WEAK_<35'
    if x < 50: return 'NEUTRAL_35_50'
    if x < 65: return 'STRONG_50_65'
    return 'EUPHORIA_>=65'


def bucket_ret(x):
    if math.isnan(x): return 'NA'
    if x < -1: return 'RET<-1'
    if x < 0: return 'RET_-1_0'
    if x < 1: return 'RET_0_1'
    return 'RET>=1'


def bucket_rel(x):
    if math.isnan(x): return 'NA'
    if x < -10: return 'IND_UNDER<-10'
    if x < 0: return 'IND_UNDER_-10_0'
    if x < 10: return 'IND_LEAD_0_10'
    return 'IND_LEAD>=10'


def load_industry_map():
    items = json.loads(INDMAP.read_text())
    mp={}
    for r in items:
        sym=r.get('symbol'); ind=r.get('industry') or ''
        if sym and ind: mp[sym]=ind
    return mp


def build_prev_features(sym_ind):
    daily = defaultdict(list)          # date -> [(sym, ind, ret)]
    ind_daily = defaultdict(lambda: defaultdict(list))
    for fp in KDIR.glob('*_daily_750.json'):
        try: sym=symbol_from_path(fp)
        except Exception: continue
        ind = sym_ind.get(sym)
        if not ind: continue
        try: bars=json.loads(fp.read_text())
        except Exception: continue
        seq=[]
        for b in bars:
            d=dn(b.get('t') or b.get('date')); c=sf(b.get('c'))
            if d and not math.isnan(c): seq.append((d,c))
        seq.sort()
        for i in range(1,len(seq)):
            d,c=seq[i]; pc=seq[i-1][1]
            if pc and pc>0:
                ret=(c/pc-1)*100
                daily[d].append((sym,ind,ret)); ind_daily[d][ind].append(ret)
    dates=sorted(daily)
    mkt_by_date={}
    ind_by_date={}
    for d, rows in daily.items():
        vals=[r[2] for r in rows]
        vals_s=sorted(vals)
        mkt_by_date[d]={'mkt_n':len(vals),'mkt_up_pct':sum(v>0 for v in vals)/len(vals)*100,
                        'mkt_med_ret':median(vals_s),'mkt_strong1_pct':sum(v>1 for v in vals)/len(vals)*100}
    for d, mp in ind_daily.items():
        for ind, vals in mp.items():
            if len(vals) < 5: continue
            ind_by_date[(d,ind)]={'ind_n':len(vals),'ind_up_pct':sum(v>0 for v in vals)/len(vals)*100,
                                  'ind_med_ret':median(vals),'ind_strong1_pct':sum(v>1 for v in vals)/len(vals)*100}
    def prev_date(d):
        i=bisect.bisect_left(dates, d)-1
        return dates[i] if i>=0 else ''
    return prev_date, mkt_by_date, ind_by_date


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sym_ind=load_industry_map()
    prev_date, mkt_by_date, ind_by_date = build_prev_features(sym_ind)
    rows=[]
    with EVENTS_CSV.open(newline='') as f:
        for r in csv.DictReader(f):
            sym=r['symbol']; d=dn(r['entry_date']); ind=sym_ind.get(sym,'UNKNOWN'); pd=prev_date(d)
            mf=mkt_by_date.get(pd,{})
            inf=ind_by_date.get((pd,ind),{})
            nr=dict(r)
            nr.update({'industry':ind,'prev_date':pd})
            for k,v in mf.items(): nr['prev_'+k]=v
            for k,v in inf.items(): nr['prev_'+k]=v
            nr['prev_ind_vs_mkt_up'] = sf(nr.get('prev_ind_up_pct')) - sf(nr.get('prev_mkt_up_pct'))
            nr['prev_ind_vs_mkt_med_ret'] = sf(nr.get('prev_ind_med_ret')) - sf(nr.get('prev_mkt_med_ret'))
            rows.append(nr)
    # feature grids: simple, interpretable surfaces only; no production fit.
    aggs=defaultdict(blank)
    pockets=defaultdict(blank)
    for r in rows:
        fam=r['family']; reg=r['regime']; vol=r['vol_env']
        risk=sf(r.get('risk')); vr=sf(r.get('vol_ratio')); rng=sf(r.get('range60')); liq=sf(r.get('liq_age'))
        mup=sf(r.get('prev_mkt_up_pct')); mret=sf(r.get('prev_mkt_med_ret'))
        iup=sf(r.get('prev_ind_up_pct')); iret=sf(r.get('prev_ind_med_ret'))
        relup=sf(r.get('prev_ind_vs_mkt_up')); relret=sf(r.get('prev_ind_vs_mkt_med_ret'))
        dims={
            'family+prev_ind_ret': f'{fam}|{bucket_ret(iret)}',
            'family+prev_ind_up': f'{fam}|{bucket_up(iup)}',
            'family+prev_ind_rel_up': f'{fam}|{bucket_rel(relup)}',
            'family+prev_mkt_ret+ind_ret': f'{fam}|M_{bucket_ret(mret)}|I_{bucket_ret(iret)}',
            'family+regime+prev_mkt_ret+ind_ret': f'{fam}|{reg}|M_{bucket_ret(mret)}|I_{bucket_ret(iret)}',
        }
        for dim,val in dims.items():
            add(aggs[(dim,val)],r)
        # hypothesis pockets based on V280/V281 evidence.
        if fam=='RANGE_LOW_SWEEP_RECLAIM' and risk>8 and vol=='LOW_VOL':
            add(pockets[('RANGE_SWEEP_RISK8_LOWVOL + prev industry/market', f'M_{bucket_up(mup)}|I_{bucket_up(iup)}|REL_{bucket_rel(relup)}')], r)
        if fam=='ABSORB_SSL_FAST_MSS' and liq<=3 and rng<=25:
            add(pockets[('ABSORB_FAST_LIQ3_RANGE25 + prev industry/market', f'MRET_{bucket_ret(mret)}|IRET_{bucket_ret(iret)}|RELRET_{bucket_rel(relret)}')], r)
        if fam=='UP_CONT_BOS_OB' and reg=='DOWN' and risk>8:
            add(pockets[('DOWN_BOS_OB_RISK8 + prev industry/market', f'MRET_{bucket_ret(mret)}|IRET_{bucket_ret(iret)}|IUP_{bucket_up(iup)}')], r)
        if vr>=1.2 and risk>8 and vol=='LOW_VOL':
            add(pockets[('LOWVOL_VOLCONF_RISK8 + grammar + prev participation', f'{fam}|MRET_{bucket_ret(mret)}|IRET_{bucket_ret(iret)}|RELUP_{bucket_rel(relup)}')], r)

    surfaces=[]
    for (dim,val),a in aggs.items():
        m=metrics(a)
        if m['n']>=100:
            surfaces.append({'dimension':dim,'value':val,**m})
    pockets_out=[]
    for (dim,val),a in pockets.items():
        m=metrics(a)
        if m['n']>=25:
            pockets_out.append({'dimension':dim,'value':val,**m})
    surfaces.sort(key=lambda x:(x['minwr'],x['wr'],x['avg'],x['n']), reverse=True)
    pockets_out.sort(key=lambda x:(x['minwr'],x['wr'],x['avg'],x['n']), reverse=True)

    # loss decomposition for best stable pocket and best large surface.
    def select_best(xs, min_n, min_year_n):
        cand=[x for x in xs if x['n']>=min_n and x['min_year_n']>=min_year_n]
        return cand[0] if cand else (xs[0] if xs else None)
    best_pocket=select_best(pockets_out,100,20)
    best_large=select_best(surfaces,1000,150)

    summary={'version':'V282_INDUSTRY_PARTICIPATION_SEQUENCE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),
             'source_events':str(EVENTS_CSV),'industry_map':str(INDMAP),'rows':len(rows),'production_write':False,'frontend_write':False,'watchlist_write':False,
             'best_large_surface':best_large,'best_pocket':best_pocket,'top_surfaces':surfaces[:30],'top_pockets':pockets_out[:40]}
    (OUT/'v282_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    LATEST.write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    with (OUT/'v282_top_surfaces.csv').open('w',newline='') as f:
        fields=['dimension','value','n','wr','avg','min_year_n','minwr','tp_pct','sl_pct','time_pct','symbols','yc','ywr']
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for r in surfaces[:300]: w.writerow({k:r.get(k) for k in fields})
    with (OUT/'v282_top_pockets.csv').open('w',newline='') as f:
        fields=['dimension','value','n','wr','avg','min_year_n','minwr','tp_pct','sl_pct','time_pct','symbols','yc','ywr']
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for r in pockets_out[:300]: w.writerow({k:r.get(k) for k in fields})
    print(json.dumps({'out':str(OUT),'latest':str(LATEST),'rows':len(rows),'best_large':best_large,'best_pocket':best_pocket},ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
