#!/usr/bin/env python3
"""Compare alternative SMC semantics on Phase2 L->D setups (300/all stocks).
Focus: prove which missing concepts explain low winrate, not curve-fit params.
"""
import json, sys
from pathlib import Path
from collections import defaultdict
sys.path.insert(0,'/root/.hermes/scripts/v25')
from phase2_strict_ld_backtest import KLINE_DIR, f, d, atr, is_swing_low, is_swing_high, swings_until, find_ssl_sweeps, find_displacement_after, simulate, metrics
N=int(sys.argv[1]) if len(sys.argv)>1 else 300
OUT=Path('/root/.hermes/smc_opt_v25/phase2_smc_semantic_ablation.json')

def demand_pois_fixed(ks,lbar,dbar):
    pois=[]
    # FVG: true bullish FVG from 3-candle displacement, use c1 high -> c3 low, not arbitrary future range
    for i in range(max(lbar+2,dbar-3), min(dbar+3,len(ks))):
        h1=f(ks[i-2].get('h')); l3=f(ks[i].get('l'))
        mid_body=abs(f(ks[i-1].get('c'))-f(ks[i-1].get('o')))
        if l3>h1 and (l3-h1)>=atr(ks,i)*0.15 and mid_body>=atr(ks,i)*0.30:
            # unmitigated between creation and dbar
            if not any(f(ks[j].get('l'))<=h1 for j in range(i+1,dbar+1)):
                pois.append({'type':'FVG_Demand','bar':i-1,'low':h1,'high':l3,'origin':'true_3bar_fvg'})
    # OB: last down candle before displacement; separate, not preferred over FVG
    for j in range(dbar-1, max(lbar-1,dbar-10), -1):
        op,cl=f(ks[j].get('o')),f(ks[j].get('c'))
        if cl<op and abs(cl-op)>=atr(ks,j)*0.15:
            pois.append({'type':'OB_Demand','bar':j,'low':f(ks[j].get('l')),'high':max(op,cl),'origin':'last_down_ob'})
            break
    return pois

def entry_original(ks,poi,dbar):
    zl,zh=poi['low'],poi['high']
    for e in range(dbar+1,min(len(ks)-61,dbar+13)):
        op,cl,hi,lo=f(ks[e].get('o')),f(ks[e].get('c')),f(ks[e].get('h')),f(ks[e].get('l'))
        if not (lo<=zh and hi>=zl): continue
        if cl<zl: return None
        if (cl>=max(zl,(zl+zh)/2) and cl>op) or ((min(op,cl)-lo)>=abs(cl-op)*1.3 and cl>=zl): return e
    return None

def entry_inside_zone(ks,poi,dbar):
    zl,zh=poi['low'],poi['high']
    for e in range(dbar+1,min(len(ks)-61,dbar+8)):
        op,cl,hi,lo=f(ks[e].get('o')),f(ks[e].get('c')),f(ks[e].get('h')),f(ks[e].get('l'))
        if not (lo<=zh and hi>=zl): continue
        if cl<zl: return None
        # require close still inside/near demand, not chased far above zone
        if cl<=zh*1.01 and cl>op and cl>=zl: return e
    return None

def entry_immediate_fvg(ks,poi,dbar):
    # test old lesson: FVG retrace may be wrong; enter next day after displacement if gap unfilled
    e=dbar+1
    if e>=len(ks)-61: return None
    if f(ks[e].get('l'))<=poi['low']: return None
    return e

def bsl_rr(ks,e,ep,sl):
    _, highs=swings_until(ks,e,3,3)
    highs=[h for h in highs if h['bar']<e and h['price']>ep]
    if not highs or ep<=sl: return 0
    tgt=min(highs,key=lambda h:h['price'])['price']
    return (tgt-ep)/(ep-sl)

def build(sym,ks,mode):
    rows=[]; best={}
    for L in find_ssl_sweeps(ks):
        D=find_displacement_after(ks,L['bar'])
        if not D: continue
        for poi in demand_pois_fixed(ks,L['bar'],D['bar']):
            if poi['type']!='FVG_Demand': continue
            e = entry_immediate_fvg(ks,poi,D['bar']) if mode=='fvg_immediate' else (entry_inside_zone(ks,poi,D['bar']) if mode=='inside_zone' else entry_original(ks,poi,D['bar']))
            if e is None: continue
            ep=f(ks[e].get('o')) if mode=='fvg_immediate' else f(ks[e].get('c'))
            sl=min(poi['low']*0.985, poi['low']-atr(ks,e)*0.25)
            risk=(ep/sl-1)*100 if sl>0 else 999
            if risk<1 or risk>8: continue
            # structural liquidity target gate variant
            if mode=='bsl_target' and bsl_rr(ks,e,ep,sl)<0.8: continue
            tp1=ep+(ep-sl)*0.8
            sim=simulate(ks,e,ep,sl,tp1)
            if not sim: continue
            t={'symbol':sym,'mode':mode,'zone_type':poi['type'],'liq_bar':L['bar'],'confirm_bar':D['bar'],'entry_idx':e,
               'liq_date':d(ks[L['bar']]),'confirm_date':d(ks[D['bar']]),'entry_date':d(ks[e]),'zone_bar':poi['bar'],'zone_date':d(ks[poi['bar']]),
               'entry_price':round(ep,4),'sl':round(sl,4),'tp1':round(tp1,4),'risk_pct':round(risk,3),'pierce_atr':round(L['pierce_atr'],3),'disp_atr':round(D['disp_atr'],3),**sim}
            k=(e,mode)
            old=best.get(k)
            if old is None or t['disp_atr']>old['disp_atr']: best[k]=t
    return list(best.values())

def bucket(ts,fn):
    g=defaultdict(list)
    for t in ts:g[fn(t)].append(t)
    return {str(k):metrics(v) for k,v in sorted(g.items(),key=lambda x:str(x[0]))}

def main():
    files=sorted(KLINE_DIR.glob('*_daily_750.json'))
    if N>0: files=files[:N]
    all=[]
    modes=['original_reclaim','inside_zone','fvg_immediate','bsl_target']
    for i,kf in enumerate(files,1):
        ks=json.loads(kf.read_text())
        if len(ks)<180: continue
        for b in ks:
            for k in ('o','h','l','c','v'):
                if k in b: b[k]=f(b[k])
        sym=kf.stem.replace('_daily_750','').replace('_SH','.SH').replace('_SZ','.SZ').replace('_BJ','.BJ')
        for m in modes: all.extend(build(sym,ks,m))
        if i%500==0: print(i,len(all),flush=True)
    rep={'n_stocks':len(files),'metrics':metrics(all),'by_mode':bucket(all,lambda t:t['mode'])}
    OUT.write_text(json.dumps(rep,ensure_ascii=False,indent=2))
    print(json.dumps(rep,ensure_ascii=False,indent=2)[:10000]);print('Saved:',OUT)
if __name__=='__main__': main()
