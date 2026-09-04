#!/usr/bin/env python3
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List
from v81_full_market_scan import KLINE_DIR, load_json
from v91_shadow_zone_entry_scanner import bar_date, num

BASE=Path('/root/.hermes/smc_opt_v97_structural_rr_contract')
ROWS=json.loads((BASE/'v97_structural_trades.json').read_text())
MAX_HOLD=80

def f(x:Any,d:float=0.0)->float: return num(x,d)
def kpath(sym:str)->Path:
    code,ex=sym.split('.')
    return KLINE_DIR/f'{code}_{ex}_daily_750.json'

def support_candidates(r:Dict[str,Any], ks:List[Dict[str,Any]])->List[float]:
    ep=f(r.get('entry_price')); ei=int(f(r.get('entry_idx'),-1))
    vals=[]
    for k in ['zone_low','prior_structure_low','break_level','equilibrium']:
        v=f(r.get(k))
        if 0<v<ep: vals.append(v)
    ref=r.get('structural_sl_ref') or {}
    v=f(ref.get('price'))
    if 0<v<ep: vals.append(v)
    if ei>0:
        for lb in [10,20,40,60]:
            prior=ks[max(0,ei-lb):ei]
            if prior:
                v=min(f(b.get('l')) for b in prior)
                if 0<v<ep: vals.append(v)
    # de-dup prices
    return sorted(set(round(v,4) for v in vals if v>0), reverse=True)

def choose_sl(r,ks,mode):
    ep=f(r.get('entry_price'))
    vals=support_candidates(r,ks)
    if not vals: return f(r.get('sl'))
    # convert support to buffered SL
    sls=[min(v*0.995, ep*0.995) for v in vals]
    sls=[s for s in sls if 0<s<ep]
    if not sls: return f(r.get('sl'))
    if mode=='current': return f(r.get('sl'))
    if mode=='deep_4pct':
        cand=[s for s in sls if (ep/s-1)*100<=4.0]
        return min(cand) if cand else f(r.get('sl'))
    if mode=='deep_3pct':
        cand=[s for s in sls if (ep/s-1)*100<=3.0]
        return min(cand) if cand else f(r.get('sl'))
    if mode=='deep_2pct':
        cand=[s for s in sls if (ep/s-1)*100<=2.0]
        return min(cand) if cand else f(r.get('sl'))
    if mode=='second_support':
        return sorted(sls, reverse=True)[1] if len(sls)>1 else sls[0]
    if mode=='prior_struct_or_deep3':
        ps=f(r.get('prior_structure_low'))
        if 0<ps<ep and (ep/(ps*0.995)-1)*100<=3.5:
            return min(ps*0.995, ep*0.995)
        cand=[s for s in sls if (ep/s-1)*100<=3.0]
        return min(cand) if cand else f(r.get('sl'))
    return f(r.get('sl'))

def simulate(ks,r,sl):
    ei=int(f(r.get('entry_idx'))); ep=f(r.get('entry_price')); tp2=f(r.get('tp2')); tp3=f(r.get('tp3'))
    if ei<0 or ep<=0 or sl<=0 or sl>=ep: return None
    risk=ep-sl
    rr2=(tp2-ep)/risk if tp2>ep else 0
    rr3=(tp3-ep)/risk if tp3>ep else 0
    if rr2<5 or rr3<8: return None
    exit_price=ep; reason='TIME_STOP'; exit_idx=min(len(ks)-1,ei+MAX_HOLD); maxh=ep; minl=ep
    for i in range(ei+1,min(len(ks),ei+MAX_HOLD+1)):
        h=f(ks[i].get('h')); l=f(ks[i].get('l')); c=f(ks[i].get('c'))
        maxh=max(maxh,h); minl=min(minl,l)
        if l<=sl:
            exit_price=sl; exit_idx=i; reason='SL_HIT'; break
        if tp2 and h>=tp2:
            exit_price=tp2; exit_idx=i; reason='TP2_MAIN_HIT'; break
        if tp3 and h>=tp3:
            exit_price=tp3; exit_idx=i; reason='TP3_RUNNER_HIT'; break
        exit_price=c
    return {'pnl':(exit_price/ep-1)*100,'reason':reason,'rr2':rr2,'rr3':rr3,'risk_pct':(ep/sl-1)*100,'mfe_r':(maxh-ep)/risk,'hold':exit_idx-ei}

def metric(results):
    n=len(results); wins=sum(1 for x in results if x['pnl']>0); sl=sum(1 for x in results if x['reason']=='SL_HIT')
    return {'n':n,'wr':round(wins/n*100,2) if n else 0,'sl_rate':round(sl/n*100,2) if n else 0,'avg_pnl':round(sum(x['pnl'] for x in results)/n,4) if n else 0,'cum_pnl':round(sum(x['pnl'] for x in results),2),'avg_risk_pct':round(sum(x['risk_pct'] for x in results)/n,4) if n else 0,'avg_rr2':round(sum(x['rr2'] for x in results)/n,4) if n else 0,'exit_counts':dict(Counter(x['reason'] for x in results))}

def main():
    prod=[r for r in ROWS if r.get('production_grade')=='A_PRODUCTION']
    cache={}
    modes=['current','second_support','deep_2pct','deep_3pct','deep_4pct','prior_struct_or_deep3']
    out={}
    for mode in modes:
        res=[]
        for r in prod:
            sym=r['symbol']
            if sym not in cache: cache[sym]=load_json(kpath(sym))
            sl=choose_sl(r,cache[sym],mode)
            s=simulate(cache[sym],r,sl)
            if s: res.append(s)
        out[mode]=metric(res)
    print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
