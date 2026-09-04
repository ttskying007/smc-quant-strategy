#!/usr/bin/env python3
"""Fast V70 signal gate search using set intersections."""
import json, math, statistics, itertools
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime
ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; SRC=ROOT/'smc_opt_v68_strict_ld'/'v68_trades.json'; OUT=ROOT/'smc_opt_v70_signal_gate'; OUT.mkdir(parents=True,exist_ok=True)
def f(x,d=0.0):
    try:
        if x is None or x=='': return d
        v=float(x); return v if math.isfinite(v) else d
    except Exception: return d
def date(b): return str(b.get('t') or b.get('date') or '')[:8]
def pct(a,b): return (a/b-1)*100 if b else 0
def ma(vals,n,i):
    return sum(vals[i-n+1:i+1])/n if i>=n-1 else None
def metrics_idx(rows, idxs):
    if not idxs: return {'n':0}
    pnls=[rows[i]['pnl_pct'] for i in idxs]; n=len(idxs); wins=sum(p>0 for p in pnls); sl=sum(rows[i]['exit_reason']=='SL_HIT' for i in idxs); tp=sum(rows[i]['exit_reason']=='TP1_HIT' for i in idxs)
    return {'n':n,'wr':round(wins/n*100,2),'avg_pnl':round(sum(pnls)/n,4),'sl_rate':round(sl/n*100,2),'tp_rate':round(tp/n*100,2)}
print('load features',datetime.now().strftime('%H:%M:%S'),flush=True)
ks_cache={}; market=defaultdict(lambda:{'n':0,'a20':0,'a60':0,'r20':0,'r5':0,'lim':0})
for kf in sorted(KDIR.glob('*_daily_750.json')):
    sym=kf.stem.replace('_daily_750','').replace('_SH','.SH').replace('_SZ','.SZ').replace('_BJ','.BJ')
    try: ks=json.loads(kf.read_text())
    except: continue
    if len(ks)<80: continue
    cs=[f(b.get('c')) for b in ks]
    rows=[]
    for i,b in enumerate(ks):
        m20=ma(cs,20,i); m60=ma(cs,60,i); c=cs[i]
        r20=pct(c,cs[i-20]) if i>=20 else 0; r5=pct(c,cs[i-5]) if i>=5 else 0
        rows.append({'d':date(b),'a20':bool(m20 and c>m20),'a60':bool(m60 and c>m60),'r20':r20,'r5':r5})
        if i>=60:
            m=market[date(b)]; m['n']+=1; m['a20']+=bool(m20 and c>m20); m['a60']+=bool(m60 and c>m60); m['r20']+=r20; m['r5']+=r5; m['lim']+= (i>0 and c/cs[i-1]-1>0.095)
    ks_cache[sym]=rows
for d,m in market.items():
    n=m['n'] or 1; m['breadth20']=m['a20']/n*100; m['breadth60']=m['a60']/n*100; m['avg_ret20']=m['r20']/n; m['avg_ret5']=m['r5']/n; m['limitup_pct']=m['lim']/n*100
raw=json.loads(SRC.read_text()); rows=[]
for t in raw:
    sk=ks_cache.get(t['symbol']); idx=int(t.get('entry_idx',-1))
    if not sk or idx<=65 or idx>=len(sk): continue
    prev=sk[idx-1]; mb=market.get(prev['d'],{})
    r={**t}; r.update({'pnl_pct':f(t['pnl_pct']),'stock_a20':prev['a20'],'stock_a60':prev['a60'],'stock_r20':prev['r20'],'stock_r5':prev['r5'],'m_b20':mb.get('breadth20',0),'m_b60':mb.get('breadth60',0),'m_r20':mb.get('avg_ret20',0),'m_r5':mb.get('avg_ret5',0),'m_lim':mb.get('limitup_pct',0),'fill_delay':int(t['entry_idx'])-int(t['confirm_bar']),'zone_width':pct(t['zone_high'],t['zone_low']),'year':t['entry_date'][:4]})
    rows.append(r)
allset=set(range(len(rows)))
gates=[
('m_b20_40_75',lambda r:40<=r['m_b20']<=75),('m_b20_45_70',lambda r:45<=r['m_b20']<=70),('m_b20_50_65',lambda r:50<=r['m_b20']<=65),('m_b60_35_70',lambda r:35<=r['m_b60']<=70),('m_r20_pos',lambda r:r['m_r20']>0),('m_r5_pos',lambda r:r['m_r5']>0),('m_lim_lt3',lambda r:r['m_lim']<3),
('stock_a20',lambda r:r['stock_a20']),('stock_a60',lambda r:r['stock_a60']),('stock_r20_pos',lambda r:r['stock_r20']>0),('stock_r5_pos',lambda r:r['stock_r5']>0),('stock_r5_-5_8',lambda r:-5<=r['stock_r5']<=8),
('risk_lt3',lambda r:r['risk_pct']<3),('risk_3_6',lambda r:3<=r['risk_pct']<6),('risk_lt6',lambda r:r['risk_pct']<6),('retrace_30_60',lambda r:30<=r['retrace_pct']<60),('retrace_50_80',lambda r:50<=r['retrace_pct']<80),
('disp_ge1_2',lambda r:r['disp_atr']>=1.2),('disp_ge1_8',lambda r:r['disp_atr']>=1.8),('pierce_ge0_3',lambda r:r['pierce_atr']>=0.3),('fill_le3',lambda r:r['fill_delay']<=3),('fill_2_8',lambda r:2<=r['fill_delay']<=8),('zone_w_lt3',lambda r:r['zone_width']<3),('zone_w_lt5',lambda r:r['zone_width']<5)]
sets={name:{i for i,r in enumerate(rows) if fn(r)} for name,fn in gates}
print('base',metrics_idx(rows,allset),'gates',len(gates),flush=True)
res=[]
for size in range(1,8):
    for combo in itertools.combinations([g[0] for g in gates],size):
        s=allset.copy()
        for name in combo:
            s &= sets[name]
            if len(s)<30: break
        if len(s)<30: continue
        m=metrics_idx(rows,s)
        if m['wr']>=82 or (m['n']>=100 and m['wr']>=78):
            years={y:metrics_idx(rows,{i for i in s if rows[i]['year']==y}) for y in sorted({rows[i]['year'] for i in s})}
            minyr=min((v['wr'] for v in years.values() if v['n']>=10), default=0)
            res.append({'combo':combo,'metrics':m,'min_year_wr_n10':round(minyr,2),'years':years})
res.sort(key=lambda x:(x['metrics']['wr'],min(x['metrics']['n'],500),x['min_year_wr_n10'],x['metrics']['avg_pnl']), reverse=True)
report={'generated_at':datetime.now().isoformat(timespec='seconds'),'base':metrics_idx(rows,allset),'passed_90_n100':sum(1 for x in res if x['metrics']['wr']>=90 and x['metrics']['n']>=100),'top100':res[:100]}
(OUT/'v70_fast_signal_gate_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str))
print(json.dumps(report,ensure_ascii=False,indent=2,default=str)[:30000])
print('Saved',OUT)
