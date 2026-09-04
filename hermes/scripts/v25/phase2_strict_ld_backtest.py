#!/usr/bin/env python3
"""Phase2 strict L→D setup generator/backtest.

L→D = sell-side Liquidity grab -> bullish Displacement/structure shift ->
validated Demand POI -> reclaim entry. This is intentionally isolated from
front-end/production wiring until full-market metrics are acceptable.

No generic indicator gates are used for entry decisions. The generator only uses
SMC structure, liquidity pools, displacement, POI validity, and reclaim bars.
"""
import json, sys, math
from dataclasses import dataclass, asdict
from pathlib import Path
from collections import defaultdict
from datetime import datetime

KLINE_DIR = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v25/phase2_strict_ld_backtest.json')
N = int(sys.argv[1]) if len(sys.argv) > 1 else 0
MAX_HOLD = 60


def f(x):
    try: return float(x or 0)
    except Exception: return 0.0


def d(b): return str(b.get('t') or b.get('date') or '')[:8]


def atr(ks, idx, n=14):
    trs=[]
    for i in range(max(1, idx-n+1), idx+1):
        h,l,pc=f(ks[i].get('h')),f(ks[i].get('l')),f(ks[i-1].get('c'))
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    return sum(trs)/len(trs) if trs else 0.0


def is_swing_low(ks, i, left=3, right=3):
    lo=f(ks[i].get('l'))
    return all(f(ks[j].get('l')) > lo for j in range(i-left, i)) and all(f(ks[j].get('l')) >= lo for j in range(i+1, i+right+1))


def is_swing_high(ks, i, left=3, right=3):
    hi=f(ks[i].get('h'))
    return all(f(ks[j].get('h')) < hi for j in range(i-left, i)) and all(f(ks[j].get('h')) <= hi for j in range(i+1, i+right+1))


def swings_until(ks, upto, left=3, right=3):
    lows=[]; highs=[]
    end=max(left, upto-right)
    for i in range(left, end+1):
        if is_swing_low(ks,i,left,right): lows.append({'bar':i,'price':f(ks[i].get('l'))})
        if is_swing_high(ks,i,left,right): highs.append({'bar':i,'price':f(ks[i].get('h'))})
    return lows, highs


def find_ssl_sweeps(ks):
    """Bullish L event: wick below prior swing low/liquidity pool, close reclaimed."""
    out=[]
    lows=[]
    for i in range(8, len(ks)-1):
        # add confirmed swing low only after right bars exist; no future beyond i.
        cand=i-3
        if cand>=3 and is_swing_low(ks,cand,3,3): lows.append({'bar':cand,'price':f(ks[cand].get('l'))})
        if not lows: continue
        lo=f(ks[i].get('l')); cl=f(ks[i].get('c')); op=f(ks[i].get('o'))
        a=atr(ks,i)
        recent=[x for x in lows if 3 <= i-x['bar'] <= 60]
        if not recent: continue
        # nearest/most recent liquidity below/around current price.
        target=min(recent, key=lambda x: (abs(lo-x['price'])/max(x['price'],1e-9), i-x['bar']))
        pierce=target['price']-lo
        reclaim=cl>target['price'] and cl>op
        if pierce >= max(a*0.05, target['price']*0.0015) and reclaim:
            wick=(min(op,cl)-lo)/max(f(ks[i].get('h'))-lo,1e-9)
            out.append({'bar':i,'liq_bar':target['bar'],'liq_price':target['price'],'pierce_atr':pierce/max(a,1e-9),'wick_ratio':wick})
    return out


def find_displacement_after(ks, lbar, max_wait=12):
    """D event: bullish close through latest pre-sweep swing high with ATR body."""
    _, highs = swings_until(ks, lbar, 3, 3)
    highs=[h for h in highs if 3 <= lbar-h['bar'] <= 80]
    if not highs: return None
    # use last lower-high area as structure threshold; taking most recent high avoids loose future confirmation.
    sh=highs[-1]
    for j in range(lbar+1, min(len(ks)-MAX_HOLD-1, lbar+max_wait+1)):
        op,cl,hi,lo=f(ks[j].get('o')),f(ks[j].get('c')),f(ks[j].get('h')),f(ks[j].get('l'))
        body=cl-op
        if cl > sh['price'] and body > 0 and body >= atr(ks,j)*0.35:
            return {'bar':j,'swing_high_bar':sh['bar'],'swing_high':sh['price'],'disp_atr':body/max(atr(ks,j),1e-9)}
    return None


def demand_pois(ks, lbar, dbar):
    """Demand created between liquidity sweep and displacement: OB first, FVG overlap optional."""
    pois=[]
    # bullish OB: last down candle between L and D; must not be fully violated before entry.
    for j in range(dbar-1, max(lbar-1, dbar-8), -1):
        op,cl=f(ks[j].get('o')),f(ks[j].get('c'))
        if cl < op:
            pois.append({'type':'OB_Demand','bar':j,'low':f(ks[j].get('l')),'high':max(op,cl),'origin':'last_down_before_displacement'})
            break
    # bullish FVG created by displacement; only if it overlaps OB or starts after L.
    for i in range(max(lbar+2, dbar-2), min(dbar+3, len(ks))):
        h0=f(ks[i-2].get('h')); l2=f(ks[i].get('l'))
        if h0>0 and l2>h0 and (l2-h0) >= atr(ks,i)*0.20:
            pois.append({'type':'FVG_Demand','bar':i-1,'low':h0,'high':l2,'origin':'displacement_imbalance'})
    # prefer confluence if OB and FVG overlap.
    if len(pois)>=2:
        ob=next((p for p in pois if p['type']=='OB_Demand'),None)
        fvg=next((p for p in pois if p['type']=='FVG_Demand'),None)
        if ob and fvg and max(ob['low'],fvg['low']) < min(ob['high'],fvg['high']):
            return [{'type':'OB_FVG_Demand','bar':max(ob['bar'],fvg['bar']),'low':max(ob['low'],fvg['low']),'high':min(ob['high'],fvg['high']),'origin':'ob_fvg_overlap'}, ob, fvg]
    return pois


def find_reclaim_entry(ks, poi, dbar, max_wait=12):
    """Wait for price to tap demand and reclaim it; enter on reclaim close."""
    zl,zh=poi['low'],poi['high']
    for e in range(max(dbar+1, poi.get('bar', dbar) + 1), min(len(ks)-MAX_HOLD-1, dbar+max_wait+1)):
        op,cl,hi,lo=f(ks[e].get('o')),f(ks[e].get('c')),f(ks[e].get('h')),f(ks[e].get('l'))
        touches = lo <= zh and hi >= zl
        if not touches: continue
        # hard invalidation: decisive close below demand.
        if cl < zl: return None
        reclaim = cl >= max(zl, (zl+zh)/2) and cl > op
        pin = (min(op,cl)-lo) >= abs(cl-op)*1.3 and cl >= zl
        if reclaim or pin:
            return e
    return None


def simulate(ks, entry_idx, ep, sl, tp1, max_hold=MAX_HOLD):
    if not (ep and sl and tp1) or ep <= sl or tp1 <= ep: return None
    for j in range(entry_idx+1, min(len(ks), entry_idx+max_hold+1)):  # T+1
        lo,hi=f(ks[j].get('l')),f(ks[j].get('h'))
        if lo <= sl:
            return {'exit_date':d(ks[j]),'exit_reason':'SL_HIT','exit_price':round(sl,4),'hold_bars':j-entry_idx,'pnl_pct':round((sl/ep-1)*100,4)}
        if hi >= tp1:
            return {'exit_date':d(ks[j]),'exit_reason':'TP1_HIT','exit_price':round(tp1,4),'hold_bars':j-entry_idx,'pnl_pct':round((tp1/ep-1)*100,4)}
    if entry_idx+max_hold < len(ks):
        px=f(ks[entry_idx+max_hold].get('c'))
        return {'exit_date':d(ks[entry_idx+max_hold]),'exit_reason':'TIME_STOP','exit_price':round(px,4),'hold_bars':max_hold,'pnl_pct':round((px/ep-1)*100,4)}
    return None


def build_setups(symbol, ks):
    candidates=[]
    sweeps=find_ssl_sweeps(ks)
    used_setup=set()
    for L in sweeps:
        D=find_displacement_after(ks,L['bar'])
        if not D: continue
        for poi in demand_pois(ks,L['bar'],D['bar']):
            e=find_reclaim_entry(ks,poi,D['bar'])
            if e is None: continue
            setup_key=(D['bar'], e, poi['type'], poi['bar'])
            if setup_key in used_setup: continue
            used_setup.add(setup_key)
            ep=f(ks[e].get('c'))
            a=atr(ks,e)
            sl=min(poi['low']*0.985, poi['low']-a*0.25)
            risk=(ep/sl-1)*100 if sl>0 else 999
            if risk < 1.0 or risk > 8.0: continue
            for rr in (0.5, 0.6, 0.7, 0.8, 1.0, 1.2, 1.5):
                tp1=ep+(ep-sl)*rr
                sim=simulate(ks,e,ep,sl,tp1)
                if not sim: continue
                retr=max(0,min(100,(poi['high']-f(ks[e].get('l')))/max(poi['high']-poi['low'],1e-9)*100))
                candidates.append({
                    'symbol':symbol,'engine':'PHASE2_STRICT_LD','definition_version':'Phase2_LD_v2_strict_dedup',
                    'sequence':'SSL_SWEEP -> BULL_DISPLACEMENT -> DEMAND_POI -> RECLAIM_ENTRY',
                    'rr_target':rr,
                    'liq_date':d(ks[L['bar']]),'confirm_date':d(ks[D['bar']]),'entry_date':d(ks[e]),
                    'liq_bar':L['bar'],'confirm_bar':D['bar'],'entry_idx':e,
                    'zone_type':poi['type'],'zone_date':d(ks[poi['bar']]),'zone_bar':poi['bar'],'zone_low':round(poi['low'],4),'zone_high':round(poi['high'],4),
                    'entry_price':round(ep,4),'sl':round(sl,4),'tp1':round(tp1,4),'risk_pct':round(risk,3),'retrace_pct':round(retr,2),
                    'pierce_atr':round(L['pierce_atr'],3),'disp_atr':round(D['disp_atr'],3),'entry_quality':'RECLAIM','pick_scope':'STRICT_LD_BACKTEST',
                    **sim
                })
    # Keep one setup per symbol/entry/rr. Priority is empirical and semantic:
    # FVG demand from displacement is cleaner than OB overlap in this strict L→D replay.
    priority={'FVG_Demand':0,'OB_Demand':1,'OB_FVG_Demand':2}
    best={}
    for t in candidates:
        k=(t['entry_idx'], t['rr_target'])
        old=best.get(k)
        if old is None or (priority.get(t['zone_type'],9), -t['disp_atr'], -t['pierce_atr']) < (priority.get(old['zone_type'],9), -old['disp_atr'], -old['pierce_atr']):
            best[k]=t
    return list(best.values())


def replay_file(kf):
    sym=kf.stem.replace('_daily_750','')
    symbol=sym.replace('_SH','.SH').replace('_SZ','.SZ').replace('_BJ','.BJ')
    try: ks=json.loads(kf.read_text())
    except Exception: return []
    if len(ks)<180: return []
    for b in ks:
        for k in ('o','h','l','c','v'):
            if k in b: b[k]=f(b[k])
    return build_setups(symbol,ks)


def metrics(ts):
    if not ts: return {'n':0}
    wins=[t for t in ts if t['pnl_pct']>0]; sl=[t for t in ts if t['exit_reason']=='SL_HIT']; tp=[t for t in ts if t['exit_reason']=='TP1_HIT']
    avg=sum(t['pnl_pct'] for t in ts)/len(ts)
    aw=sum(t['pnl_pct'] for t in wins)/len(wins) if wins else 0
    losses=[t for t in ts if t['pnl_pct']<=0]
    al=sum(t['pnl_pct'] for t in losses)/len(losses) if losses else 0
    return {'n':len(ts),'wr':round(len(wins)/len(ts)*100,2),'sl_rate':round(len(sl)/len(ts)*100,2),'tp_rate':round(len(tp)/len(ts)*100,2),'avg_pnl':round(avg,4),'cum':round(sum(t['pnl_pct'] for t in ts),2),'avg_win':round(aw,4),'avg_loss':round(al,4),'rr':round(aw/abs(al),3) if al else 0,'avg_hold':round(sum(t['hold_bars'] for t in ts)/len(ts),2)}


def bucket(ts, fn):
    g=defaultdict(list)
    for t in ts: g[fn(t)].append(t)
    return {str(k):metrics(v) for k,v in sorted(g.items(), key=lambda kv:str(kv[0]))}


def main():
    files=sorted(KLINE_DIR.glob('*_daily_750.json'))
    if N>0: files=files[:N]
    all_trades=[]
    print(f"Phase2 strict L→D replay {len(files)} stocks {datetime.now():%H:%M:%S}", flush=True)
    for i,kf in enumerate(files,1):
        all_trades.extend(replay_file(kf))
        if i%500==0: print(f"  {i}/{len(files)} trades={len(all_trades)}", flush=True)
    report={
        'generated_at':datetime.now().isoformat(timespec='seconds'),'n_stocks':len(files),'metrics':metrics(all_trades),
        'buckets':{
            'rr_target':bucket(all_trades,lambda t:t['rr_target']),
            'zone_type':bucket(all_trades,lambda t:t['zone_type']),
            'risk_bin':bucket(all_trades,lambda t:'a_<2' if t['risk_pct']<2 else ('b_2_4' if t['risk_pct']<4 else ('c_4_6' if t['risk_pct']<6 else 'd_6_8'))),
            'retrace_bin':bucket(all_trades,lambda t:'a_<30' if t['retrace_pct']<30 else ('b_30_60' if t['retrace_pct']<60 else ('c_60_90' if t['retrace_pct']<90 else 'd_90_100'))),
            'exit_reason':bucket(all_trades,lambda t:t['exit_reason']),
        },
        'samples':all_trades[:50]
    }
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2)[:8000])
    print('Saved:',OUT)

if __name__=='__main__': main()
