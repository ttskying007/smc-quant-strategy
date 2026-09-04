#!/usr/bin/env python3
"""V34 LuxAlgo-leg SMC core — transparent signal correctness core.

Implements the actual LuxAlgo structure semantics instead of generic
pivothigh(left,right):

Pine reference:
  leg(size):
      newLegHigh = high[size] > ta.highest(size)
      newLegLow  = low[size]  < ta.lowest(size)
      if newLegHigh => BEARISH_LEG
      else if newLegLow => BULLISH_LEG
  getCurrentStructure(size): on leg change update swingHigh/swingLow pivot
  displayStructure(): ta.crossover(close,pivot.currentLevel) => BOS/CHoCH

This module is deliberately verbose/auditable: every pivot and structure event
carries evidence fields (pine_rule, trigger, labels, crossed state).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional

BULLISH_LEG = 1
BEARISH_LEG = 0
BULLISH = 1
BEARISH = -1


def _f(x, default=0.0):
    try: return float(x)
    except Exception: return default


def _date(b):
    return str(b.get('t', b.get('date', '')))


def normalize(klines: List[Dict]) -> List[Dict]:
    out=[]
    for b in klines:
        nb=dict(b)
        for k in ('o','h','l','c','v'):
            nb[k]=_f(nb.get(k,0))
        nb['t']=_date(nb)
        out.append(nb)
    return out


def true_ranges(klines):
    out=[]; pc=None
    for b in klines:
        h,l,c=b['h'],b['l'],b['c']
        tr=h-l if pc is None else max(h-l, abs(h-pc), abs(l-pc))
        out.append(max(tr,0)); pc=c
    return out


def rolling_atr(klines, period=14):
    trs=true_ranges(klines); out=[]; s=0.0
    for i,tr in enumerate(trs):
        s+=tr
        if i>=period: s-=trs[i-period]
        out.append(s/min(i+1,period))
    return out


def lux_leg_series(klines: List[Dict], size: int) -> List[int]:
    """Replicate LuxAlgo leg(size) state using high[size] > ta.highest(size).

    In Pine at current bar i, high[size] is bar k=i-size, ta.highest(size)
    covers recent `size` bars before current bar (i-size+1..i). Thus pivot at k
    is confirmed at i when k's high exceeds all following size highs.
    """
    n=len(klines); leg=0; out=[]
    for i in range(n):
        if i < size:
            out.append(leg); continue
        k=i-size
        new_high = klines[k]['h'] > max(klines[j]['h'] for j in range(k+1, i+1))
        new_low  = klines[k]['l'] < min(klines[j]['l'] for j in range(k+1, i+1))
        if new_high:
            leg = BEARISH_LEG
        elif new_low:
            leg = BULLISH_LEG
        out.append(leg)
    return out


def lux_pivots(klines: List[Dict], size: int, level='swing') -> Dict:
    legs=lux_leg_series(klines,size)
    highs=[]; lows=[]; last_high=None; last_low=None
    prev=legs[0] if legs else 0
    for i in range(1,len(klines)):
        cur=legs[i]
        if cur==prev: continue
        k=i-size
        # Ignore bootstrap pivots that arise from uninitialized leg state at chart start.
        # LuxAlgo can draw first swing labels, but trading structure should start only after
        # both a real high and a real low have been established away from the first bars.
        bootstrap_cutoff = size * 2
        if k < bootstrap_cutoff:
            prev = cur
            continue
        if cur == BULLISH_LEG and prev == BEARISH_LEG:
            # startOfBullishLeg -> pivotLow at low[size]
            price=klines[k]['l']; label='LL' if last_low is not None and price < last_low else ('HL' if last_low is not None else 'L')
            lows.append({'idx':k,'confirm_idx':i,'price':price,'date':_date(klines[k]),'confirm_date':_date(klines[i]),'label':label,'size':size,'source_level':level,'pine_rule':'startOfBullishLeg: low[size] < ta.lowest(size)'})
            last_low=price
        elif cur == BEARISH_LEG and prev == BULLISH_LEG:
            # startOfBearishLeg -> pivotHigh at high[size]
            price=klines[k]['h']; label='HH' if last_high is not None and price > last_high else ('LH' if last_high is not None else 'H')
            highs.append({'idx':k,'confirm_idx':i,'price':price,'date':_date(klines[k]),'confirm_date':_date(klines[i]),'label':label,'size':size,'source_level':level,'pine_rule':'startOfBearishLeg: high[size] > ta.highest(size)'})
            last_high=price
        prev=cur
    return {'highs':highs,'lows':lows,'n':len(highs)+len(lows),'size':size,'source_level':level}


@dataclass
class PivotState:
    currentLevel: Optional[float]=None
    lastLevel: Optional[float]=None
    crossed: bool=True
    barIndex: Optional[int]=None
    barTime: str=''
    label: str=''


def display_structure_lux(klines: List[Dict], pivots: Dict, level='swing') -> List[Dict]:
    by_confirm={}
    for h in pivots.get('highs',[]): by_confirm.setdefault(h['confirm_idx'],[]).append(('high',h))
    for l in pivots.get('lows',[]): by_confirm.setdefault(l['confirm_idx'],[]).append(('low',l))
    high=PivotState(); low=PivotState(); trend=0; events=[]
    for i,b in enumerate(klines):
        # getCurrentStructure(): update current pivot when new leg starts
        for kind,p in by_confirm.get(i,[]):
            st = high if kind=='high' else low
            st.lastLevel = st.currentLevel
            st.currentLevel = p['price']
            st.crossed = False
            st.barIndex = p['idx']
            st.barTime = p['date']
            st.label = p.get('label','')
        c=b['c']; pc=klines[i-1]['c'] if i>0 else c
        # displayStructure bullish crossover
        if high.currentLevel is not None and not high.crossed and pc <= high.currentLevel and c > high.currentLevel:
            tag='CHOCH' if trend==BEARISH else 'BOS'
            old=trend; trend=BULLISH; high.crossed=True
            events.append({'type':tag,'direction':'bull','index':i,'date':_date(b),'price':high.currentLevel,'break_price':c,'swing_idx':high.barIndex,'swing_price':high.currentLevel,'swing_label':high.label,'source_level':level,'old_trend':'bearish' if old==BEARISH else ('bullish' if old==BULLISH else 'unknown'),'new_trend':'bullish','is_mss':False,'pine_rule':'ta.crossover(close,pivot.currentLevel) and not pivot.crossed; tag = trend.bias == BEARISH ? CHOCH : BOS','trigger':{'prev_close':pc,'close':c,'pivot':high.currentLevel},'pivot_bar_index':high.barIndex,'pivot_bar_time':high.barTime})
        # displayStructure bearish crossunder
        if low.currentLevel is not None and not low.crossed and pc >= low.currentLevel and c < low.currentLevel:
            tag='CHOCH' if trend==BULLISH else 'BOS'
            old=trend; trend=BEARISH; low.crossed=True
            events.append({'type':tag,'direction':'bear','index':i,'date':_date(b),'price':low.currentLevel,'break_price':c,'swing_idx':low.barIndex,'swing_price':low.currentLevel,'swing_label':low.label,'source_level':level,'old_trend':'bullish' if old==BULLISH else ('bearish' if old==BEARISH else 'unknown'),'new_trend':'bearish','is_mss':False,'pine_rule':'ta.crossunder(close,pivot.currentLevel) and not pivot.crossed; tag = trend.bias == BULLISH ? CHOCH : BOS','trigger':{'prev_close':pc,'close':c,'pivot':low.currentLevel},'pivot_bar_index':low.barIndex,'pivot_bar_time':low.barTime})
    return events


def qualify_mss(events: List[Dict], sweeps: List[Dict], klines: List[Dict], atr: List[float], lookback=12):
    for e in events:
        if e['type'] != 'CHOCH':
            e['is_mss']=False; e['mss_reason']=''; continue
        recent=[s for s in sweeps if s.get('direction')==e['direction'] and 0 < e['index']-s.get('index',-999) <= lookback]
        if not recent:
            e['is_mss']=False; e['mss_reason']=''; continue
        b=klines[e['index']]; rng=max(b['h']-b['l'],1e-9); body=abs(b['c']-b['o'])
        disp_ok = rng >= atr[e['index']]*0.9 or body/rng >= 0.55
        e['is_mss']=bool(disp_ok)
        e['mss_reason']=f"recent_{recent[-1].get('subtype','SWEEP')}_displacement" if disp_ok else ''
    return events


def sweep_from_pivots(klines,pivots,atr,lookback=80,reclaim_atr=0.05,min_wick_ratio=0.35):
    levels=[]
    for h in pivots.get('highs',[]): levels.append({'id':f"H{h['idx']}",'idx':h['idx'],'confirm_idx':h['confirm_idx'],'price':h['price'],'side':'high','swept':False,'pool':'SWING','label':h.get('label')})
    for l in pivots.get('lows',[]): levels.append({'id':f"L{l['idx']}",'idx':l['idx'],'confirm_idx':l['confirm_idx'],'price':l['price'],'side':'low','swept':False,'pool':'SWING','label':l.get('label')})
    out=[]
    for i,b in enumerate(klines):
        emitted=set()
        cands=[lv for lv in levels if not lv['swept'] and lv['confirm_idx']<i and i-lv['idx']<=lookback]
        cands.sort(key=lambda x:x['idx'],reverse=True)
        for lv in cands:
            rng=max(b['h']-b['l'],1e-9); buf=max(atr[i]*reclaim_atr, lv['price']*0.0005)
            if lv['side']=='low':
                if 'bull' in emitted: continue
                lw=min(b['o'],b['c'])-b['l']
                if b['l'] < lv['price']-buf and b['c'] > lv['price'] and lw/rng >= min_wick_ratio:
                    out.append({'type':'SWEEP','subtype':'SSL','direction':'bull','index':i,'date':_date(b),'price':lv['price'],'wick_low':b['l'],'close':b['c'],'swept_idx':lv['idx'],'swept_label':lv.get('label'),'pool':lv['pool'],'pine_rule':'liquidity sweep: wick below pivot low + close reclaim'})
                    lv['swept']=True; emitted.add('bull')
            else:
                if 'bear' in emitted: continue
                uw=b['h']-max(b['o'],b['c'])
                if b['h'] > lv['price']+buf and b['c'] < lv['price'] and uw/rng >= min_wick_ratio:
                    out.append({'type':'SWEEP','subtype':'BSL','direction':'bear','index':i,'date':_date(b),'price':lv['price'],'wick_high':b['h'],'close':b['c'],'swept_idx':lv['idx'],'swept_label':lv.get('label'),'pool':lv['pool'],'pine_rule':'liquidity sweep: wick above pivot high + close reclaim'})
                    lv['swept']=True; emitted.add('bear')
    return out


def order_blocks_from_structure(klines: List[Dict], events: List[Dict], atr: List[float]) -> List[Dict]:
    """LuxAlgo-style order blocks created at structure break time.

    storeOrderBlock(pivot,current,bias) semantics: scan from crossed pivot bar
    to break bar and store the most extreme parsed low/high as the OB anchor.
    This prevents V34 structure from being paired with stale V32 zones.
    """
    obs=[]
    n=len(klines)
    for e in events:
        pi=e.get('pivot_bar_index')
        bi=e.get('index')
        if pi is None or bi is None or pi < 0 or bi <= pi or bi >= n:
            continue
        lo=max(0, int(pi)); hi=min(n-1, int(bi))
        window=list(range(lo, hi+1))
        if e.get('direction') == 'bull':
            k=min(window, key=lambda j: klines[j]['l'])
            zl=klines[k]['l']; zh=max(klines[k]['o'], klines[k]['c'])
            direction='bull'
            pine_rule='LuxAlgo storeOrderBlock: min(parsedLows) between crossed pivot and break for bullish OB'
        else:
            k=max(window, key=lambda j: klines[j]['h'])
            zl=min(klines[k]['o'], klines[k]['c']); zh=klines[k]['h']
            direction='bear'
            pine_rule='LuxAlgo storeOrderBlock: max(parsedHighs) between crossed pivot and break for bearish OB'
        if zl <= 0 or zh <= 0 or zh <= zl:
            continue
        obs.append({
            'type':'OB', 'direction':direction, 'index':k, 'date':_date(klines[k]),
            'zone_low':zl, 'zone_high':zh, 'width_pct':round((zh-zl)/max(zl,1e-9)*100,3),
            'created_by_event_index':bi, 'created_by_event_date':e.get('date',''),
            'created_by_event_type':e.get('type'), 'created_by_source_level':e.get('source_level'),
            'pivot_bar_index':pi, 'pivot_bar_time':e.get('pivot_bar_time',''),
            'pine_rule':pine_rule,
            'src_event': {'index':bi,'date':e.get('date',''),'type':e.get('type'),'direction':e.get('direction'),'pivot':e.get('price')}
        })
    return obs


def detect_all_signals_lux_v34(klines: List[Dict], swing_len=20, internal_len=5) -> Dict:
    klines=normalize(klines); atr=rolling_atr(klines,14)
    swing=lux_pivots(klines,swing_len,'swing')
    internal=lux_pivots(klines,internal_len,'internal')
    sweeps=sweep_from_pivots(klines,swing,atr)
    swing_struct=display_structure_lux(klines,swing,'swing')
    internal_struct=display_structure_lux(klines,internal,'internal')
    qualify_mss(swing_struct,sweeps,klines,atr)
    qualify_mss(internal_struct,sweeps,klines,atr)
    structure=sorted(swing_struct + [e for e in internal_struct if e.get('is_mss')], key=lambda x:x['index'])
    obs=order_blocks_from_structure(klines, structure, atr)
    return {'signals':{'swings':swing,'internal_swings':internal,'sweeps':sweeps,'swing_structure':swing_struct,'internal_structure':internal_struct,'structure':structure,'obs':obs}, 'summary':{'n_bars':len(klines),'profile':{'swing_len':swing_len,'internal_len':internal_len,'core':'luxalgo_leg_v34'},'n_swing_structure':len(swing_struct),'n_internal_structure':len(internal_struct),'n_structure':len(structure),'n_sweeps':len(sweeps),'n_obs':len(obs),'definition_version':'smc_core_luxalgo_v34'}}

if __name__=='__main__':
    import json, sys
    ks=json.loads(open(sys.argv[1]).read())
    print(json.dumps(detect_all_signals_lux_v34(ks)['summary'],ensure_ascii=False,indent=2))
