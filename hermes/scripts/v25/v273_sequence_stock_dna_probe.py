#!/usr/bin/env python3
"""V273 no-write: stock-DNA check for broad chronological sequence variants.

Tests whether the broad time-ordered BOS->Demand->Retest sequence is low-volume
per stock, and whether per-stock DNA selection can rescue quality.
"""
from __future__ import annotations
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
import pandas as pd

BASE=Path('/root/.hermes'); KLINE_DIR=BASE/'kline_cache'; TS=datetime.now().strftime('%Y%m%d_%H%M%S')
OUT=BASE/f'smc_audit/v273_sequence_stock_dna_no_write_{TS}'; LATEST=BASE/'smc_audit/v273_sequence_stock_dna_latest.json'
VARIANTS=[('best_quality_strict',10,5,5,'strict_v262'),('max_volume_support',10,12,20,'support_hold')]

def f(x:Any,d=0.0):
    try:return float(x)
    except Exception:return d

def ds(b): return str(b.get('t',b.get('date',''))).replace('.0','')[:8]
def sym(p:Path):
    s=p.stem.replace('_daily_750',''); c,e=s.split('_',1); return f'{c}.{e}'
def mode_ok(mode,b,zl,zh):
    o=f(b.get('o')); c=f(b.get('c')); h=f(b.get('h')); l=f(b.get('l')); rng=max(h-l,1e-9)
    if l>zh*1.005: return False
    if mode=='strict_v262': return c>=zh and c>o and (c-l)/rng>=0.55
    if mode=='support_hold': return c>=zl
    return False
def replay(bars,ei,entry,sl):
    if ei+1>=len(bars): return None
    tp=entry+(entry-sl)*1.5; last=min(len(bars)-1,ei+10); xp=f(bars[last].get('c'))
    for i in range(ei+1,last+1):
        if f(bars[i].get('l'))<=sl: xp=sl; break
        if f(bars[i].get('h'))>=tp: xp=tp; break
    return (xp/entry-1)*100
def scan_variant(bars,bos_lb,demand_lb,wait,mode):
    out=[]; seen=set()
    for event_i in range(max(40,bos_lb),len(bars)-2):
        e=bars[event_i]; o=f(e.get('o')); c=f(e.get('c')); h=f(e.get('h')); l=f(e.get('l'))
        if c<=o or h<=l: continue
        ph=max(f(x.get('h')) for x in bars[event_i-bos_lb:event_i])
        if c<=ph: continue
        di=None
        for k in range(event_i-1,max(event_i-demand_lb-1,-1),-1):
            if f(bars[k].get('c'))<f(bars[k].get('o')): di=k; break
        if di is None: continue
        zl=f(bars[di].get('l')); zh=max(f(bars[di].get('o')),f(bars[di].get('c')))
        if zl<=0 or zh<=zl: continue
        ri=None
        for j in range(event_i+1,min(event_i+wait,len(bars)-2)+1):
            if mode_ok(mode,bars[j],zl,zh): ri=j; break
        if ri is None: continue
        ei=ri+1
        if ei in seen: continue
        entry=f(bars[ei].get('o')); sl=zl*0.99; risk=(entry/sl-1)*100
        if not (0.8<=risk<=12): continue
        pnl=replay(bars,ei,entry,sl)
        if pnl is None: continue
        seen.add(ei); out.append((ds(bars[ei]),pnl))
    return out
def met(vals):
    if not vals: return {'n':0}
    pnl=[v[1] for v in vals]; yrs=defaultdict(list)
    for d,p in vals: yrs[d[:4]].append(p)
    return {'n':len(vals),'wr':round(sum(p>0 for p in pnl)/len(pnl)*100,2),'avg':round(sum(pnl)/len(pnl),4),'year_counts':{y:len(v) for y,v in sorted(yrs.items())},'year_wr':{y:round(sum(p>0 for p in v)/len(v)*100,2) for y,v in sorted(yrs.items())}}
def main():
    OUT.mkdir(parents=True,exist_ok=True); paths=sorted(KLINE_DIR.glob('*_daily_750.json'))
    per={name:[] for name,*_ in VARIANTS}; allvals={name:[] for name,*_ in VARIANTS}
    for idx,p in enumerate(paths,1):
        try: bars=json.loads(p.read_text())
        except Exception: continue
        s=sym(p)
        for name,bos,dlb,wait,mode in VARIANTS:
            vals=scan_variant(bars,bos,dlb,wait,mode); allvals[name].extend(vals)
            m=met(vals); m['symbol']=s; per[name].append(m)
        if idx%500==0: print('scanned',idx,'/',len(paths),flush=True)
    summary={'version':'V273_SEQUENCE_STOCK_DNA_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'out_dir':str(OUT),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'inputs':{'kline_files':len(paths)},'variants':{}}
    for name,*_ in VARIANTS:
        df=pd.DataFrame(per[name]); df.to_csv(OUT/f'{name}_per_stock.csv',index=False)
        qualified=df[df['n']>=8].copy()
        hi=qualified[(qualified['wr']>=60)&(qualified['avg']>0)]
        top=qualified.sort_values(['wr','avg','n'],ascending=[False,False,False]).head(30).to_dict('records')
        summary['variants'][name]={'overall':met(allvals[name]),'stocks_with_n_ge_1':int((df['n']>=1).sum()),'stocks_with_n_ge_8':int((df['n']>=8).sum()),'stocks_wr60_avgpos_n8':int(len(hi)),'dna_filtered_n':int(hi['n'].sum()) if len(hi) else 0,'dna_filtered_wr':round((hi['wr']*hi['n']).sum()/hi['n'].sum(),2) if len(hi) else 0,'top_stocks':top[:20],'artifact':str(OUT/f'{name}_per_stock.csv')}
    (OUT/'v273_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)); LATEST.write_text(json.dumps(summary,ensure_ascii=False,indent=2)); print(json.dumps(summary,ensure_ascii=False,indent=2)[:8000])
if __name__=='__main__': main()
