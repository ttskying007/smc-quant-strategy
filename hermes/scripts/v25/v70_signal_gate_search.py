#!/usr/bin/env python3
"""V70 signal-layer gate search toward >=90% WR.

Uses V68 strict FVG L→D trades as the executable base, then audits missing
non-leaky gates available at entry time:
- market breadth / regime known before entry
- stock trend context known before entry
- liquidity / displacement / zone geometry
- entry timing / retrace quality

No production/frontend writes.
"""
import json, math, statistics
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

ROOT=Path('/root/.hermes')
KDIR=ROOT/'kline_cache'
SRC=ROOT/'smc_opt_v68_strict_ld'/'v68_trades.json'
OUT=ROOT/'smc_opt_v70_signal_gate'
OUT.mkdir(parents=True, exist_ok=True)

def f(x,d=0.0):
    try:
        if x is None or x=='': return d
        v=float(x); return v if math.isfinite(v) else d
    except Exception: return d

def date(b): return str(b.get('t') or b.get('date') or '')[:8]

def ma(vals,n,i):
    if i-n+1<0: return None
    s=vals[i-n+1:i+1]
    return sum(s)/len(s) if s else None

def pct(a,b): return (a/b-1)*100 if b else 0

def metrics(rows):
    if not rows: return {'n':0}
    pnls=[f(r['pnl_pct']) for r in rows]
    wins=[p for p in pnls if p>0]; losses=[p for p in pnls if p<=0]
    sl=sum(1 for r in rows if r.get('exit_reason')=='SL_HIT')
    tp=sum(1 for r in rows if r.get('exit_reason')=='TP1_HIT')
    return {'n':len(rows),'wr':round(len(wins)/len(rows)*100,2),'avg_pnl':round(statistics.mean(pnls),4),'sl_rate':round(sl/len(rows)*100,2),'tp_rate':round(tp/len(rows)*100,2),'avg_win':round(statistics.mean(wins),4) if wins else 0,'avg_loss':round(statistics.mean(losses),4) if losses else 0}

# Load all klines and build market breadth by date from information available at prior close.
print('load klines', datetime.now().strftime('%H:%M:%S'), flush=True)
ks_cache={}
market_by_date=defaultdict(lambda:{'n':0,'above20':0,'above60':0,'ret20_sum':0.0,'ret5_sum':0.0,'limitup_like':0,'down20_sum':0.0})
for i,kf in enumerate(sorted(KDIR.glob('*_daily_750.json')),1):
    sym=kf.stem.replace('_daily_750','').replace('_SH','.SH').replace('_SZ','.SZ').replace('_BJ','.BJ')
    try: ks=json.loads(kf.read_text())
    except Exception: continue
    if len(ks)<80: continue
    closes=[f(b.get('c')) for b in ks]
    highs=[f(b.get('h')) for b in ks]
    rows=[]
    for idx,b in enumerate(ks):
        c=closes[idx]
        m20=ma(closes,20,idx); m60=ma(closes,60,idx)
        ret20=pct(c,closes[idx-20]) if idx>=20 else 0
        ret5=pct(c,closes[idx-5]) if idx>=5 else 0
        h20=max(highs[max(0,idx-20):idx+1]) if idx>=5 else c
        down20=pct(c,h20)
        rows.append({'date':date(b),'idx':idx,'c':c,'ma20':m20,'ma60':m60,'ret20':ret20,'ret5':ret5,'down20':down20,'above20':bool(m20 and c>m20),'above60':bool(m60 and c>m60)})
        if idx>=60:
            mb=market_by_date[date(b)]
            mb['n']+=1; mb['above20']+= c>m20; mb['above60']+= c>m60; mb['ret20_sum']+=ret20; mb['ret5_sum']+=ret5; mb['down20_sum']+=down20
            if idx>0 and c/closes[idx-1]-1 > 0.095: mb['limitup_like']+=1
    ks_cache[sym]=rows
    if i%500==0: print('  klines',i,flush=True)
for d,m in market_by_date.items():
    n=m['n'] or 1
    m['breadth20']=m['above20']/n*100; m['breadth60']=m['above60']/n*100; m['avg_ret20']=m['ret20_sum']/n; m['avg_ret5']=m['ret5_sum']/n; m['avg_down20']=m['down20_sum']/n; m['limitup_pct']=m['limitup_like']/n*100

trades=json.loads(SRC.read_text())
rows=[]
for t in trades:
    sym=t['symbol']; ed=t['entry_date']; sk=ks_cache.get(sym)
    if not sk: continue
    idx=int(t['entry_idx'])
    if idx<=65 or idx>=len(sk): continue
    # use prior bar stock features to avoid entry-day leakage where possible
    prev=sk[idx-1]
    mb=market_by_date.get(prev['date'], {})
    r=dict(t)
    r.update({
        'stock_above20': prev['above20'], 'stock_above60': prev['above60'],
        'stock_ret20': prev['ret20'], 'stock_ret5': prev['ret5'], 'stock_down20': prev['down20'],
        'm_breadth20': mb.get('breadth20',0), 'm_breadth60': mb.get('breadth60',0), 'm_avg_ret20': mb.get('avg_ret20',0), 'm_avg_ret5': mb.get('avg_ret5',0), 'm_down20': mb.get('avg_down20',0), 'm_limitup_pct': mb.get('limitup_pct',0),
        'fill_delay': int(t['entry_idx'])-int(t['confirm_bar']),
        'zone_width_pct': pct(t['zone_high'],t['zone_low']),
        'year': ed[:4], 'month': ed[:6],
    })
    rows.append(r)
print('base', metrics(rows), flush=True)

def gate_defs():
    return [
        ('market_breadth20_40_75', lambda r: 40<=r['m_breadth20']<=75),
        ('market_breadth20_45_70', lambda r: 45<=r['m_breadth20']<=70),
        ('market_breadth60_35_70', lambda r: 35<=r['m_breadth60']<=70),
        ('market_ret20_pos', lambda r: r['m_avg_ret20']>0),
        ('market_ret5_pos', lambda r: r['m_avg_ret5']>0),
        ('market_not_overheat_limitup_lt3', lambda r: r['m_limitup_pct']<3),
        ('stock_above20', lambda r: r['stock_above20']),
        ('stock_above60', lambda r: r['stock_above60']),
        ('stock_ret20_pos', lambda r: r['stock_ret20']>0),
        ('stock_ret5_pos', lambda r: r['stock_ret5']>0),
        ('stock_not_far_from_high', lambda r: r['stock_down20']>-12),
        ('stock_pullback_ok', lambda r: -10<=r['stock_ret5']<=8),
        ('risk_lt3', lambda r: r['risk_pct']<3),
        ('risk_3_6', lambda r: 3<=r['risk_pct']<6),
        ('risk_lt6', lambda r: r['risk_pct']<6),
        ('retrace_30_60', lambda r: 30<=r['retrace_pct']<60),
        ('retrace_50_80', lambda r: 50<=r['retrace_pct']<80),
        ('disp_ge1_2', lambda r: r['disp_atr']>=1.2),
        ('disp_ge1_8', lambda r: r['disp_atr']>=1.8),
        ('pierce_ge0_3', lambda r: r['pierce_atr']>=0.3),
        ('fill_delay_le3', lambda r: r['fill_delay']<=3),
        ('fill_delay_2_8', lambda r: 2<=r['fill_delay']<=8),
        ('zone_width_lt3', lambda r: r['zone_width_pct']<3),
        ('zone_width_lt5', lambda r: r['zone_width_pct']<5),
    ]

gates=gate_defs()
# single and combos up to 6 gates; accept n>=50 for discovery, production target n>=100.
results=[]
from itertools import combinations
for size in range(1,7):
    for combo in combinations(gates,size):
        selected=[r for r in rows if all(fn(r) for _,fn in combo)]
        if len(selected)<30: continue
        m=metrics(selected)
        if m['wr']>=80 or (len(selected)>=100 and m['wr']>=75):
            # robustness by year
            years={y:metrics([x for x in selected if x['year']==y]) for y in sorted(set(x['year'] for x in selected))}
            minyr=min((v['wr'] for v in years.values() if v['n']>=10), default=0)
            results.append({'combo':[n for n,_ in combo], 'metrics':m, 'min_year_wr_n10':round(minyr,2), 'years':years})
results.sort(key=lambda x:(x['metrics']['wr'], min(x['metrics']['n'],500), x['min_year_wr_n10'], x['metrics']['avg_pnl']), reverse=True)
report={'generated_at':datetime.now().isoformat(timespec='seconds'),'source':str(SRC),'base':metrics(rows),'gate_search_count':len(results),'passed_90':sum(1 for x in results if x['metrics']['wr']>=90 and x['metrics']['n']>=100),'top100':results[:100]}
(OUT/'v70_signal_gate_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2)[:20000])
print('Saved',OUT)
