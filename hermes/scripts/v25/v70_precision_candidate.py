#!/usr/bin/env python3
"""Materialize V70 precision candidate from non-leaky signal-layer gates.

Gate source: v70_fast_signal_gate_search.py top result.
This is candidate artifact only. Frontend/production remains unchanged until volume and
robustness gates are accepted.
"""
import json, math, statistics
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime
ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; SRC=ROOT/'smc_opt_v68_strict_ld'/'v68_trades.json'; OUT=ROOT/'smc_opt_v70_precision'
OUT.mkdir(parents=True,exist_ok=True)
def f(x,d=0.0):
    try:
        if x is None or x=='': return d
        v=float(x); return v if math.isfinite(v) else d
    except Exception: return d
def date(b): return str(b.get('t') or b.get('date') or '')[:8]
def ma(vals,n,i): return sum(vals[i-n+1:i+1])/n if i>=n-1 else None
def pct(a,b): return (a/b-1)*100 if b else 0
def metrics(rows):
    if not rows: return {'n':0}
    pnls=[f(r['pnl_pct']) for r in rows]; wins=[p for p in pnls if p>0]; losses=[p for p in pnls if p<=0]
    sl=sum(1 for r in rows if r['exit_reason']=='SL_HIT'); tp=sum(1 for r in rows if r['exit_reason']=='TP1_HIT')
    return {'n':len(rows),'wr':round(len(wins)/len(rows)*100,2),'avg_pnl':round(sum(pnls)/len(rows),4),'sl_rate':round(sl/len(rows)*100,2),'tp_rate':round(tp/len(rows)*100,2),'avg_win':round(sum(wins)/len(wins),4) if wins else 0,'avg_loss':round(sum(losses)/len(losses),4) if losses else 0,'cum_pnl':round(sum(pnls),2)}
# Features cache
ks_cache={}; market=defaultdict(lambda:{'n':0,'a20':0,'a60':0,'r20':0,'r5':0,'lim':0})
for kf in sorted(KDIR.glob('*_daily_750.json')):
    sym=kf.stem.replace('_daily_750','').replace('_SH','.SH').replace('_SZ','.SZ').replace('_BJ','.BJ')
    try: ks=json.loads(kf.read_text())
    except: continue
    if len(ks)<80: continue
    cs=[f(b.get('c')) for b in ks]; rows=[]
    for i,b in enumerate(ks):
        m20=ma(cs,20,i); m60=ma(cs,60,i); c=cs[i]
        r20=pct(c,cs[i-20]) if i>=20 else 0; r5=pct(c,cs[i-5]) if i>=5 else 0
        rows.append({'d':date(b),'a20':bool(m20 and c>m20),'a60':bool(m60 and c>m60),'r20':r20,'r5':r5})
        if i>=60:
            m=market[date(b)]; m['n']+=1; m['a20']+=bool(m20 and c>m20); m['a60']+=bool(m60 and c>m60); m['r20']+=r20; m['r5']+=r5; m['lim']+=(i>0 and c/cs[i-1]-1>0.095)
    ks_cache[sym]=rows
for d,m in market.items():
    n=m['n'] or 1; m['breadth20']=m['a20']/n*100; m['breadth60']=m['a60']/n*100; m['avg_ret20']=m['r20']/n; m['avg_ret5']=m['r5']/n; m['limitup_pct']=m['lim']/n*100

def enrich(t):
    sk=ks_cache.get(t['symbol']); idx=int(t.get('entry_idx',-1))
    if not sk or idx<=65 or idx>=len(sk): return None
    prev=sk[idx-1]; mb=market.get(prev['d'],{})
    r=dict(t)
    r.update({'engine':'V70_PRECISION_90WR_SIGNAL_GATE','definition_version':'V70_precision_nonleaky_market_stock_zone_gate','stock_a20':prev['a20'],'stock_a60':prev['a60'],'stock_r20':round(prev['r20'],3),'stock_r5':round(prev['r5'],3),'m_b20':round(mb.get('breadth20',0),3),'m_b60':round(mb.get('breadth60',0),3),'m_r20':round(mb.get('avg_ret20',0),3),'m_r5':round(mb.get('avg_ret5',0),3),'m_lim':round(mb.get('limitup_pct',0),3),'fill_delay':int(t['entry_idx'])-int(t['confirm_bar']),'zone_width_pct':round(pct(t['zone_high'],t['zone_low']),3)})
    return r

def gate(r):
    return (50 <= r['m_b20'] <= 65 and 35 <= r['m_b60'] <= 70 and r['stock_r20'] > 0 and r['stock_r5'] > 0 and 3 <= r['risk_pct'] < 6 and r['pierce_atr'] >= 0.3 and r['zone_width_pct'] < 3)
rows=[]
for t in json.loads(SRC.read_text()):
    r=enrich(t)
    if r and gate(r):
        r['signal_gate']='m_b20_50_65 + m_b60_35_70 + stock_r20_pos + stock_r5_pos + risk_3_6 + pierce_ge0_3 + zone_width_lt3'
        r['pick_scope']='V70_PRECISION_RESEARCH'
        rows.append(r)
by_year={y:metrics([r for r in rows if r['entry_date'].startswith(y)]) for y in sorted(set(r['entry_date'][:4] for r in rows))}
# latest per symbol picks
latest={}
for r in sorted(rows,key=lambda x:(x['entry_date'],x['symbol'])): latest[r['symbol']]=r
picks=sorted(latest.values(), key=lambda x:x['entry_date'], reverse=True)[:200]
for p in picks:
    p['source']='V70_PRECISION_90WR_SIGNAL_GATE'; p['status']='WATCH_ONLY'; p['is_active_pick']=False; p['reason']='V70 precision research candidate: non-leaky signal-layer gates reached >90% WR but n<100 production gate.'
report={'generated_at':datetime.now().isoformat(timespec='seconds'),'source':str(SRC),'gate':rows[0]['signal_gate'] if rows else '', 'metrics':metrics(rows),'by_year':by_year,'audit':{'semantic_order_fail':sum(not (r['liq_bar']<r['confirm_bar'] and r['zone_bar']<=r['confirm_bar']+1 and r['entry_idx']>max(r['zone_bar'],r['confirm_bar'])) for r in rows),'t_plus_1_fail':sum(r.get('exit_idx',999)<=r.get('entry_idx',-1) for r in rows),'field_fail':sum(any(r.get(k) in (None,'',0,0.0) for k in ['symbol','entry_date','join_date','zone_type','zone_low','zone_high','cost_line','smart_money_cost','volatility_pct','entry_price','sl','tp1']) for r in rows)},'promotion_decision':'NO_PRODUCTION_YET_WR_OK_BUT_N_LT_100_AND_2023_2024_2026_SPARSE'}
(OUT/'v70_precision_trades.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
(OUT/'v70_precision_picks.json').write_text(json.dumps(picks,ensure_ascii=False,indent=2))
(OUT/'v70_precision_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
print('Saved',OUT)
