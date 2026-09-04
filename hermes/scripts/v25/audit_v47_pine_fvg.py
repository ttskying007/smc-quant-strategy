#!/usr/bin/env python3
"""Dedicated Pine-like FVG audit for V46.1/V47 outputs."""
from __future__ import annotations
import json, pathlib, collections, time
ROOT=pathlib.Path('/root/.hermes')
CACHE=ROOT/'kline_cache'
AUD=ROOT/'smc_audit'
V46=ROOT/'smc_opt_v46_1_layered_3y'
V47=ROOT/'smc_opt_v47_candidate'

def f(x,d=0.0):
    try: return float(x or d)
    except Exception: return d

def load(p,default=None):
    try: return json.loads(pathlib.Path(p).read_text())
    except Exception: return default

def kpath(sym): return CACHE/(sym.replace('.','_')+'_daily_750.json')

def audit_trade(t):
    sym=t.get('symbol'); kl=load(kpath(sym),[]) or []
    zi=int(float(t.get('zone_idx') or t.get('signal_index') or -1))
    gl=f(t.get('gap_low') if t.get('gap_low') is not None else t.get('raw_zone_low'))
    gh=f(t.get('gap_high') if t.get('gap_high') is not None else t.get('raw_zone_high'))
    ei=int(float(t.get('entry_index') or -1))
    out={'symbol':sym,'entry_date':t.get('entry_date'),'zone_idx':zi,'entry_index':ei,'gap_low':gl,'gap_high':gh,'ok_bounds':gl>0 and gh>0 and gh>=gl}
    # Bull FVG Pine-like condition near zone index: low[i] > high[i-2].
    found=False; exact=False; touch=False; filled_before=False
    for j in range(max(2,zi-2), min(len(kl),zi+3)):
        low=f(kl[j].get('l')); h2=f(kl[j-2].get('h'))
        if low>h2:
            found=True
            if abs(low-gh)<=max(0.03,gh*0.01) or abs(h2-gl)<=max(0.03,gl*0.01) or (abs((low-h2)-(gh-gl))<=max(0.05,(gh-gl)*0.25)):
                exact=True
    if 0<=zi<len(kl) and ei>zi and gl and gh:
        for j in range(zi+1, min(ei+1,len(kl))):
            lo=f(kl[j].get('l')); hi=f(kl[j].get('h'))
            if lo<=gh and hi>=gl: touch=True
            if lo<=gl: filled_before=True
    out.update({'pine_like_near_zone':found,'pine_bounds_match':exact,'touched_before_entry':touch,'fully_filled_before_or_at_entry':filled_before})
    out['failures']=[k for k,v in [('NO_BOUNDS',out['ok_bounds']),('NO_PINE_FVG_NEAR_ZONE',found),('BOUNDS_NOT_MATCH_PINE',exact),('NO_TOUCH_BEFORE_ENTRY',touch)] if not v]
    return out

def run_one(name,path):
    trades=load(path,[]) or []
    fvg=[t for t in trades if 'FVG' in str(t.get('zone_type'))]
    rows=[audit_trade(t) for t in fvg]
    cnt=collections.Counter()
    for r in rows:
        for fail in r['failures']: cnt[fail]+=1
    return {'name':name,'path':str(path),'n_fvg':len(rows),'ok_bounds':sum(r['ok_bounds'] for r in rows),'pine_like_near_zone':sum(r['pine_like_near_zone'] for r in rows),'pine_bounds_match':sum(r['pine_bounds_match'] for r in rows),'touched_before_entry':sum(r['touched_before_entry'] for r in rows),'fully_filled_before_or_at_entry':sum(r['fully_filled_before_or_at_entry'] for r in rows),'failure_counts':dict(cnt),'bad_samples':[r for r in rows if r['failures']][:50]}

def main():
    result={'generated_at':time.strftime('%F %T'),'v46':run_one('v46_1',V46/'v46_1_trades.json')}
    if (V47/'v47_trades.json').exists(): result['v47']=run_one('v47',V47/'v47_trades.json')
    AUD.mkdir(exist_ok=True)
    (AUD/'v47_pine_fvg_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2)[:5000])
if __name__=='__main__': main()
