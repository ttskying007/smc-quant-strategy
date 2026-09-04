#!/usr/bin/env python3
"""Root-cause audit for Phase2 Strict L->D low winrate.
Quantifies which SMC components are missing/weak in losing setups.
"""
import json, sys
from pathlib import Path
from collections import defaultdict
sys.path.insert(0,'/root/.hermes/scripts/v25')
from phase2_strict_ld_backtest import replay_file, KLINE_DIR, f, atr, d, swings_until, metrics
OUT=Path('/root/.hermes/smc_opt_v25/phase2_ld_root_cause_audit.json')
N=int(sys.argv[1]) if len(sys.argv)>1 else 0

def loadks(sym):
    key=sym.replace('.','_')+'_daily_750.json'
    p=KLINE_DIR/key
    if not p.exists(): return []
    ks=json.loads(p.read_text())
    for b in ks:
        for k in ('o','h','l','c','v'):
            if k in b: b[k]=f(b[k])
    return ks

def close_below(ks,a,b,px):
    return any(f(ks[i].get('c'))<px for i in range(max(0,a),min(len(ks),b+1)))

def touch_count(ks,a,b,zl,zh):
    n=0
    for i in range(max(0,a),min(len(ks),b+1)):
        if f(ks[i].get('l'))<=zh and f(ks[i].get('h'))>=zl: n+=1
    return n

def struct_ctx(ks, idx):
    lows, highs=swings_until(ks,idx,3,3)
    lows=lows[-3:]; highs=highs[-3:]
    if len(lows)<2 or len(highs)<2: return 'unknown'
    hl=lows[-1]['price']>lows[-2]['price']; hh=highs[-1]['price']>highs[-2]['price']
    ll=lows[-1]['price']<lows[-2]['price']; lh=highs[-1]['price']<highs[-2]['price']
    if hl and hh: return 'bull_structure'
    if ll and lh: return 'bear_structure'
    return 'range_transition'

def discount_pos(ks, liq_bar, dbar, entry):
    lo=min(f(ks[i].get('l')) for i in range(max(0,liq_bar-5),dbar+1))
    hi=max(f(ks[i].get('h')) for i in range(max(0,liq_bar-5),dbar+1))
    if hi<=lo: return 999
    return round((entry-lo)/(hi-lo)*100,2)  # lower is deeper discount

def bsl_target_rr(ks, entry_idx, entry, sl):
    _, highs=swings_until(ks,entry_idx,3,3)
    highs=[h for h in highs if h['bar']<entry_idx and h['price']>entry]
    if not highs or entry<=sl: return 0
    target=min(highs, key=lambda h: h['price'])['price']
    return round((target-entry)/(entry-sl),2)

def pinbar_strength(ks, i):
    op,cl,lo,hi=f(ks[i].get('o')),f(ks[i].get('c')),f(ks[i].get('l')),f(ks[i].get('h'))
    rng=max(hi-lo,1e-9); body=abs(cl-op)
    lower=min(op,cl)-lo; upper=hi-max(op,cl)
    if lower>body*2.5 and lower/rng>0.6 and upper/rng<0.25 and cl>(op+lo)/2: return 'strict_pinbar'
    if cl>op: return 'weak_green'
    return 'no_bull_confirm'

def bucket(ts,fn):
    g=defaultdict(list)
    for t in ts: g[fn(t)].append(t)
    return {str(k):metrics(v) for k,v in sorted(g.items(),key=lambda x:str(x[0]))}

def main():
    files=sorted(KLINE_DIR.glob('*_daily_750.json'))
    if N>0: files=files[:N]
    rows=[]
    for n,kf in enumerate(files,1):
        sym=kf.stem.replace('_daily_750','').replace('_SH','.SH').replace('_SZ','.SZ').replace('_BJ','.BJ')
        ks=loadks(sym)
        if len(ks)<180: continue
        for t in replay_file(kf):
            if t.get('rr_target')!=0.8 or t.get('zone_type')!='FVG_Demand': continue
            e=t['entry_idx']; zb=t['zone_bar']; db=t['confirm_bar']; lb=t['liq_bar']
            zl,zh=t['zone_low'],t['zone_high']; ep=t['entry_price']; sl=t['sl']
            wait=e-db; pre_touch=touch_count(ks,zb+1,e-1,zl,zh)
            invalid_pre=close_below(ks,zb+1,e-1,zl)
            fill=(zh-f(ks[e].get('l')))/max(zh-zl,1e-9)*100
            row=dict(t)
            row.update({
              'won':t['pnl_pct']>0,
              'wait_bin':'0_2' if wait<=2 else ('3_6' if wait<=6 else '7_12'),
              'pre_touch_bin':'0' if pre_touch==0 else ('1' if pre_touch==1 else '2plus'),
              'invalid_pre':invalid_pre,
              'fill_bin':'shallow_<50' if fill<50 else ('deep_50_100' if fill<=100 else 'overfill_>100'),
              'entry_close_pos':'above_zone' if f(ks[e].get('c'))>zh else 'inside_zone',
              'pinbar':pinbar_strength(ks,e),
              'pre_structure':struct_ctx(ks,lb),
              'discount_bin': (lambda x:'discount_0_40' if x<=40 else ('equilibrium_40_60' if x<=60 else 'premium_60p'))(discount_pos(ks,lb,db,ep)),
              'bsl_rr_bin': (lambda x:'no_target_or_<0.8' if x<0.8 else ('0.8_1.2' if x<1.2 else '>=1.2'))(bsl_target_rr(ks,e,ep,sl)),
              'disp_bin':'weak_<0.8' if t['disp_atr']<0.8 else ('mid_0.8_1.5' if t['disp_atr']<1.5 else 'strong_1.5p'),
              'pierce_bin':'weak_<0.2' if t['pierce_atr']<0.2 else ('mid_0.2_0.6' if t['pierce_atr']<0.6 else 'strong_0.6p')
            })
            rows.append(row)
        if n%500==0: print(n,len(rows),flush=True)
    report={'n_stocks':len(files),'base':metrics(rows),'buckets':{}}
    for k in ['pre_structure','pierce_bin','disp_bin','wait_bin','pre_touch_bin','invalid_pre','fill_bin','entry_close_pos','pinbar','discount_bin','bsl_rr_bin']:
        report['buckets'][k]=bucket(rows,lambda t,k=k:t[k])
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2)[:12000])
    print('Saved:',OUT)
if __name__=='__main__': main()
