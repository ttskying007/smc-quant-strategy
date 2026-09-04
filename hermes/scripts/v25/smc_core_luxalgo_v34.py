#!/usr/bin/env python3
"""V34 LuxAlgo-leg SMC core — transparent signal correctness core.

Implements LuxAlgo/Pine market-structure semantics with a leg(size)
currentLevel model instead of generic two-sided fractal pivots.

Pine reference:
  leg(size):
      newLegHigh = high[size] > ta.highest(size)
      newLegLow  = low[size]  < ta.lowest(size)
      if newLegHigh => BEARISH_LEG
      else if newLegLow => BULLISH_LEG
  getCurrentStructure(size): on leg change update swingHigh/swingLow pivot
  displayStructure(): ta.crossover(close,pivot.currentLevel) => BOS/CHoCH

The module keeps a wave/fractal reference layer for diagnostics, but active
BOS/CHOCH, sweeps, OBs and MSS use the LuxAlgo leg/currentLevel pivots.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional
from smc_signal_schema import attach_raw_display_fields

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
    """Replicate LuxAlgo leg(size) state.

    At current bar i, candidate pivot is k=i-size. The candidate becomes a new
    high/low leg only after the right-side `size` bars confirm it. This matches
    the Pine idea: store a pivot from history, then walk left->right and wait for
    close crossover/crossunder of that currentLevel.
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


def wave_fractal_pivots(klines: List[Dict], size: int, level='wave_ref') -> Dict:
    """Wave/Waves Ultimate style diagnostic pivots: left+right confirmed.

    This is no longer the active structure engine. It is retained as a reference
    layer to compare against wave-theory style swing points and catch cases where
    Lux leg currentLevel selects a visually weak point.
    """
    highs=[]; lows=[]; last_high=None; last_low=None
    n=len(klines)
    if n < size*2 + 1:
        return {'highs':highs,'lows':lows,'n':0,'size':size,'source_level':level,'pivot_rule':'wave_two_sided_fractal_reference'}
    for k in range(size, n-size):
        h=klines[k]['h']; l=klines[k]['l']
        left=range(k-size, k); right=range(k+1, k+size+1)
        is_high = h > max(klines[j]['h'] for j in left) and h > max(klines[j]['h'] for j in right)
        is_low  = l < min(klines[j]['l'] for j in left) and l < min(klines[j]['l'] for j in right)
        confirm_idx=k+size
        if is_high:
            label='HH' if last_high is not None and h > last_high else ('LH' if last_high is not None else 'H')
            highs.append({'idx':k,'confirm_idx':confirm_idx,'price':h,'date':_date(klines[k]),'confirm_date':_date(klines[confirm_idx]),'label':label,'size':size,'source_level':level,'pivot_rule':'wave_two_sided_fractal_reference','pine_rule':'wave/fractal ref: high[k] > left(size) and right(size); confirmed at k+size'})
            last_high=h
        if is_low:
            label='LL' if last_low is not None and l < last_low else ('HL' if last_low is not None else 'L')
            lows.append({'idx':k,'confirm_idx':confirm_idx,'price':l,'date':_date(klines[k]),'confirm_date':_date(klines[confirm_idx]),'label':label,'size':size,'source_level':level,'pivot_rule':'wave_two_sided_fractal_reference','pine_rule':'wave/fractal ref: low[k] < left(size) and right(size); confirmed at k+size'})
            last_low=l
    return {'highs':highs,'lows':lows,'n':len(highs)+len(lows),'size':size,'source_level':level,'pivot_rule':'wave_two_sided_fractal_reference'}


def lux_pivots(klines: List[Dict], size: int, level='swing') -> Dict:
    """Active LuxAlgo leg(size) currentLevel pivots.

    On a leg transition, LuxAlgo stores the historical highest/lowest bar over
    the leg window as the current pivot. Later displayStructure draws from that
    pivot bar to the first break bar. This function records those pivot updates
    exactly as currentLevel events, not generic two-sided fractals.
    """
    highs=[]; lows=[]; last_high=None; last_low=None
    n=len(klines)
    if n <= size:
        return {'highs':highs,'lows':lows,'n':0,'size':size,'source_level':level,'pivot_rule':'luxalgo_leg_currentLevel'}
    leg=lux_leg_series(klines,size)
    prev=leg[0]
    for i in range(1,n):
        cur=leg[i]
        if cur == prev:
            continue
        start=max(0, i-size)
        # Pine code uses highest/lowest over `size` and then locates the bar.
        window=list(range(start, i+1))
        if cur == BEARISH_LEG:
            k=max(window, key=lambda j: (klines[j]['h'], -j))
            h=klines[k]['h']
            label='HH' if last_high is not None and h > last_high else ('LH' if last_high is not None else 'H')
            highs.append({'idx':k,'confirm_idx':i,'price':h,'date':_date(klines[k]),'confirm_date':_date(klines[i]),'label':label,'size':size,'source_level':level,'leg_from':prev,'leg_to':cur,'pivot_rule':'luxalgo_leg_currentLevel','pine_rule':'LuxAlgo leg(size): newLegHigh -> store trailing/current swingHigh; line later from pivot.barTime to break bar'})
            last_high=h
        elif cur == BULLISH_LEG:
            k=min(window, key=lambda j: (klines[j]['l'], j))
            l=klines[k]['l']
            label='LL' if last_low is not None and l < last_low else ('HL' if last_low is not None else 'L')
            lows.append({'idx':k,'confirm_idx':i,'price':l,'date':_date(klines[k]),'confirm_date':_date(klines[i]),'label':label,'size':size,'source_level':level,'leg_from':prev,'leg_to':cur,'pivot_rule':'luxalgo_leg_currentLevel','pine_rule':'LuxAlgo leg(size): newLegLow -> store trailing/current swingLow; line later from pivot.barTime to break bar'})
            last_low=l
        prev=cur
    return {'highs':highs,'lows':lows,'n':len(highs)+len(lows),'size':size,'source_level':level,'pivot_rule':'luxalgo_leg_currentLevel'}


@dataclass
class PivotState:
    currentLevel: Optional[float]=None
    lastLevel: Optional[float]=None
    crossed: bool=True
    barIndex: Optional[int]=None
    barTime: str=''
    label: str=''
    confirmIndex: Optional[int]=None
    confirmTime: str=''
    pivotRule: str=''


def display_structure_lux(klines: List[Dict], pivots: Dict, level='swing', wave_pivots: Optional[Dict]=None, max_wave_distance: int=3) -> List[Dict]:
    wave_refs=[]
    if isinstance(wave_pivots, dict):
        wave_refs=list(wave_pivots.get('highs', [])) + list(wave_pivots.get('lows', []))
    def nearest_wave(pidx, direction):
        if pidx is None or not wave_refs:
            return None
        labels = ('HH','LH','H') if direction == 'bull' else ('LL','HL','L')
        cands=[w for w in wave_refs if w.get('label') in labels and abs(int(w.get('idx', -999))-int(pidx)) <= max_wave_distance]
        return min(cands, key=lambda w: abs(int(w.get('idx'))-int(pidx))) if cands else None
    by_confirm={}
    for h in pivots.get('highs',[]): by_confirm.setdefault(h['confirm_idx'],[]).append(('high',h))
    for l in pivots.get('lows',[]): by_confirm.setdefault(l['confirm_idx'],[]).append(('low',l))
    high=PivotState(); low=PivotState(); trend=0; events=[]
    for i,b in enumerate(klines):
        for kind,p in by_confirm.get(i,[]):
            st = high if kind=='high' else low
            st.lastLevel = st.currentLevel
            st.currentLevel = p['price']
            st.crossed = False
            st.barIndex = p['idx']
            st.barTime = p['date']
            st.label = p.get('label','')
            st.confirmIndex = p.get('confirm_idx')
            st.confirmTime = p.get('confirm_date','')
            st.pivotRule = p.get('pivot_rule','')
        c=b['c']; pc=klines[i-1]['c'] if i>0 else c
        if high.currentLevel is not None and not high.crossed and pc <= high.currentLevel and c > high.currentLevel:
            wref = nearest_wave(high.barIndex, 'bull')
            if level == 'swing' and wref is None:
                continue
            tag='CHOCH' if trend==BEARISH else 'BOS'
            old=trend; trend=BULLISH; high.crossed=True
            direction_text = 'bearish_to_bullish' if old==BEARISH else ('bullish_continuation' if old==BULLISH else 'initial_bullish_break')
            events.append({'type':tag,'direction':'bull','index':i,'date':_date(b),'price':high.currentLevel,'break_price':c,'swing_idx':high.barIndex,'swing_price':high.currentLevel,'swing_label':high.label,'source_level':level,'old_trend':'bearish' if old==BEARISH else ('bullish' if old==BULLISH else 'unknown'),'new_trend':'bullish','is_mss':False,'pine_rule':'LuxAlgo displayStructure: ta.crossover(close,pivot.currentLevel) and not pivot.crossed; tag = trend.bias == BEARISH ? CHOCH : BOS','trigger':{'prev_close':pc,'close':c,'pivot':high.currentLevel},'pivot_bar_index':high.barIndex,'pivot_bar_time':high.barTime,'pivot_confirm_index':high.confirmIndex,'pivot_confirm_time':high.confirmTime,'pivot_rule':high.pivotRule,
                           'line_start_idx':high.barIndex,'line_start_date':high.barTime,'line_start_price':high.currentLevel,
                           'line_end_idx':i,'line_end_date':_date(b),'line_end_price':high.currentLevel,
                           'line_semantics':'luxalgo_currentLevel_break_between_previous_high_and_break_bar','line_direction':direction_text,
                           'from_left':'LuxAlgo current swingHigh/currentLevel pivot','to_right':'first close making new high above currentLevel','crossed_after_break':True})
        if low.currentLevel is not None and not low.crossed and pc >= low.currentLevel and c < low.currentLevel:
            wref = nearest_wave(low.barIndex, 'bear')
            if level == 'swing' and wref is None:
                continue
            tag='CHOCH' if trend==BULLISH else 'BOS'
            old=trend; trend=BEARISH; low.crossed=True
            direction_text = 'bullish_to_bearish' if old==BULLISH else ('bearish_continuation' if old==BEARISH else 'initial_bearish_break')
            events.append({'type':tag,'direction':'bear','index':i,'date':_date(b),'price':low.currentLevel,'break_price':c,'swing_idx':low.barIndex,'swing_price':low.currentLevel,'swing_label':low.label,'source_level':level,'old_trend':'bullish' if old==BULLISH else ('bearish' if old==BEARISH else 'unknown'),'new_trend':'bearish','is_mss':False,'pine_rule':'LuxAlgo displayStructure: ta.crossunder(close,pivot.currentLevel) and not pivot.crossed; tag = trend.bias == BULLISH ? CHOCH : BOS','trigger':{'prev_close':pc,'close':c,'pivot':low.currentLevel},'pivot_bar_index':low.barIndex,'pivot_bar_time':low.barTime,'pivot_confirm_index':low.confirmIndex,'pivot_confirm_time':low.confirmTime,'pivot_rule':low.pivotRule,
                           'line_start_idx':low.barIndex,'line_start_date':low.barTime,'line_start_price':low.currentLevel,
                           'line_end_idx':i,'line_end_date':_date(b),'line_end_price':low.currentLevel,
                           'line_semantics':'luxalgo_currentLevel_break_between_previous_low_and_break_bar','line_direction':direction_text,
                           'from_left':'LuxAlgo current swingLow/currentLevel pivot','to_right':'first close making new low below currentLevel','crossed_after_break':True})
    return events


def qualify_mss(events: List[Dict], sweeps: List[Dict], klines: List[Dict], atr: List[float], lookback=12):
    for e in events:
        e['is_mss']=False
        e['is_mss_confirmed']=False
        e['mss_reason']='deprecated_choch_attached_mss_disabled'
    return events


def detect_independent_mss(internal_events: List[Dict], sweeps: List[Dict], klines: List[Dict], atr: List[float], lookback=14) -> List[Dict]:
    out=[]; seen=set()
    for e in internal_events:
        recent=[s for s in sweeps if s.get('direction')==e.get('direction') and 0 < e.get('index',0)-s.get('index',-999) <= lookback]
        if not recent:
            continue
        b=klines[e['index']]
        rng=max(b['h']-b['l'],1e-9); body=abs(b['c']-b['o'])
        disp_ratio=rng/max(atr[e['index']],1e-9)
        body_ratio=body/rng
        if disp_ratio < 1.0 or body_ratio < 0.55:
            continue
        sw=recent[-1]
        pidx=e.get('pivot_bar_index')
        wave_refs=[]
        # internal MSS is still only display/confirmation; require it to share the
        # visible swing/wave neighborhood instead of floating mid-leg.
        # The internal event already carries a pivot label/index from Lux currentLevel.
        if pidx is None:
            continue
        key=(e['index'],e.get('direction'),e.get('pivot_bar_index'))
        if key in seen:
            continue
        seen.add(key)
        m=dict(e)
        m['type']='MSS'
        m['is_mss']=True
        m['is_mss_confirmed']=bool(disp_ratio >= 0.9 or body_ratio >= 0.55)
        m['is_internal_mss']=True
        m['source_level']='internal'
        m['mss_reason']='independent_micro_shift_after_'+sw.get('subtype','SWEEP')
        m['sweep_index']=sw.get('index')
        m['sweep_date']=sw.get('date')
        m['sweep_price']=sw.get('price')
        m['displacement_ratio']=round(disp_ratio,3)
        m['body_ratio']=round(body_ratio,3)
        m['pine_rule']='MSS independent: recent liquidity sweep + internal Lux currentLevel break in same direction + displacement/body evidence'
        out.append(m)
    return out


def sweep_from_pivots(klines,pivots,atr,lookback=80,reclaim_atr=0.05,min_wick_ratio=0.35):
    levels=[]
    for h in pivots.get('highs',[]): levels.append({'id':f"H{h['idx']}",'idx':h['idx'],'confirm_idx':h['confirm_idx'],'price':h['price'],'side':'high','swept':False,'pool':'SWING','label':h.get('label'),'pivot_rule':h.get('pivot_rule')})
    for l in pivots.get('lows',[]): levels.append({'id':f"L{l['idx']}",'idx':l['idx'],'confirm_idx':l['confirm_idx'],'price':l['price'],'side':'low','swept':False,'pool':'SWING','label':l.get('label'),'pivot_rule':l.get('pivot_rule')})
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
                    out.append({'type':'SWEEP','subtype':'SSL','direction':'bull','index':i,'date':_date(b),'price':lv['price'],'wick_low':b['l'],'close':b['c'],'swept_idx':lv['idx'],'swept_label':lv.get('label'),'pool':lv['pool'],'pivot_rule':lv.get('pivot_rule'),'pine_rule':'liquidity sweep: wick below Lux currentLevel low + close reclaim'})
                    lv['swept']=True; emitted.add('bull')
            else:
                if 'bear' in emitted: continue
                uw=b['h']-max(b['o'],b['c'])
                if b['h'] > lv['price']+buf and b['c'] < lv['price'] and uw/rng >= min_wick_ratio:
                    out.append({'type':'SWEEP','subtype':'BSL','direction':'bear','index':i,'date':_date(b),'price':lv['price'],'wick_high':b['h'],'close':b['c'],'swept_idx':lv['idx'],'swept_label':lv.get('label'),'pool':lv['pool'],'pivot_rule':lv.get('pivot_rule'),'pine_rule':'liquidity sweep: wick above Lux currentLevel high + close reclaim'})
                    lv['swept']=True; emitted.add('bear')
    return out


def _wave_turn_ob_anchor(klines: List[Dict], wave_pivots: Dict, window: List[int], direction: str, max_dist=3) -> Optional[Dict]:
    """Return an OB candle anchored to a Waves-style HH/HL/LH/LL turn.

    User-facing correctness rule: an OB must form at a pullback/reversal turning
    point, not in the middle of a trend leg.  Bullish demand OBs must sit near a
    confirmed wave low (HL/LL/L); bearish supply OBs must sit near a confirmed
    wave high (HH/LH/H).  The candle itself still follows SMC/Pine convention:
    last opposite-colour candle around the turn before the structure break.
    """
    if not window:
        return None
    wset=set(window)
    if direction == 'bull':
        turns=[p for p in wave_pivots.get('lows', []) if p.get('idx') in wset and p.get('label') in ('HL','LL','L')]
        opposite=lambda j: klines[j]['c'] < klines[j]['o']
        extreme=lambda js: min(js, key=lambda j: (abs(j-turn['idx']), klines[j]['l']))
    else:
        turns=[p for p in wave_pivots.get('highs', []) if p.get('idx') in wset and p.get('label') in ('HH','LH','H')]
        opposite=lambda j: klines[j]['c'] > klines[j]['o']
        extreme=lambda js: min(js, key=lambda j: (abs(j-turn['idx']), -klines[j]['h']))
    turns.sort(key=lambda p: p.get('idx', -1), reverse=True)
    for turn in turns:
        lo=max(window[0], int(turn['idx'])-max_dist)
        hi=min(window[-1], int(turn['idx'])+max_dist)
        js=[j for j in range(hi, lo-1, -1) if j in wset and opposite(j)]
        if not js:
            continue
        k=extreme(js)
        return {'anchor_idx':k, 'wave_turn':turn, 'distance':abs(k-int(turn['idx']))}
    return None


def order_blocks_from_structure(klines: List[Dict], events: List[Dict], atr: List[float], wave_pivots: Optional[Dict]=None) -> List[Dict]:
    obs=[]; n=len(klines)
    wave_pivots = wave_pivots or wave_fractal_pivots(klines, 2, 'wave_ref')
    for e in events:
        pi=e.get('pivot_bar_index'); bi=e.get('index')
        if pi is None or bi is None or pi < 0 or bi <= pi or bi >= n:
            continue
        lo=max(0, int(pi)); hi=min(n-1, int(bi)-1)
        window=list(range(lo, hi+1))
        if not window:
            continue
        break_bar=klines[bi]
        break_rng=max(break_bar['h']-break_bar['l'],1e-9)
        break_disp=break_rng/max(atr[bi],1e-9)
        if break_disp < 1.5:
            continue
        direction = e.get('direction')
        anchor = _wave_turn_ob_anchor(klines, wave_pivots, window, direction)
        if not anchor:
            continue
        k=anchor['anchor_idx']
        turn=anchor['wave_turn']
        if direction == 'bull':
            pine_rule='Wave-aligned SMC OB: bearish candle within ±3 bars of confirmed HL/LL wave low before bullish currentLevel break'
        else:
            pine_rule='Wave-aligned SMC OB: bullish candle within ±3 bars of confirmed HH/LH wave high before bearish currentLevel break'
        zl=klines[k]['l']; zh=klines[k]['h']
        if zl <= 0 or zh <= 0 or zh <= zl:
            continue
        next_i=min(k+1,n-1)
        rng=max(klines[k]['h']-klines[k]['l'],1e-9)
        next_move=abs(klines[next_i]['c']-klines[k]['c']) if next_i!=k else 0
        disp_ratio=next_move/max(atr[k],1e-9)
        body_ratio=abs(klines[k]['c']-klines[k]['o'])/rng
        strength = 0
        if break_disp >= 1.5: strength += 2
        if e.get('type') == 'CHOCH' or e.get('is_mss'): strength += 1
        if (zh - zl) <= max(atr[k]*0.75, ((zl+zh)/2)*0.003): strength += 1
        if bi-k <= 5: strength += 1
        ob = {
            'type':'OB', 'direction':direction, 'index':k, 'date':_date(klines[k]),
            'zone_low':zl, 'zone_high':zh, 'raw_zone_low': zl, 'raw_zone_high': zh,
            'raw_bottom': zl, 'raw_top': zh,
            'width_pct':round((zh-zl)/max(zl,1e-9)*100,3),
            'created_by_event_index':bi, 'created_by_event_date':e.get('date',''),
            'created_by_event_type':e.get('type'), 'created_by_source_level':e.get('source_level'),
            'created_by_pivot_label': e.get('swing_label'), 'created_by_pivot_price': e.get('price'),
            'level_type': e.get('source_level'), 'structure_type': e.get('type'),
            'pivot_bar_index':pi, 'pivot_bar_time':e.get('pivot_bar_time',''),
            'pivot_confirm_index':e.get('pivot_confirm_index'), 'pivot_rule':e.get('pivot_rule'),
            'wave_turn_idx': turn.get('idx'), 'wave_turn_date': turn.get('date'),
            'wave_turn_label': turn.get('label'), 'wave_turn_price': turn.get('price'),
            'wave_turn_confirm_idx': turn.get('confirm_idx'), 'wave_turn_confirm_date': turn.get('confirm_date'),
            'wave_turn_distance': anchor.get('distance'),
            'bars_before_break': bi-k,
            'anchor_method': 'wave_turn_opposite_candle_near_HH_HL_LH_LL',
            'displacement_ratio': round(disp_ratio,3), 'body_ratio': round(body_ratio,3),
            'break_displacement_mult': round(break_disp,3), 'displacement_pass': True,
            'strength': strength, 'min_strength_pass': strength >= 3,
            'pine_rule':pine_rule,
            'src_event': {'index':bi,'date':e.get('date',''),'type':e.get('type'),'direction':e.get('direction'),'pivot':e.get('price')}
        }
        ob.update(attach_raw_display_fields(ob, atr=atr[k], price=(zl+zh)/2))
        obs.append(ob)
    return obs


def detect_all_signals_lux_v34(klines: List[Dict], swing_len=5, internal_len=3) -> Dict:
    klines=normalize(klines); atr=rolling_atr(klines,14)
    swing=lux_pivots(klines,swing_len,'swing')
    internal=lux_pivots(klines,internal_len,'internal')
    # Waves Ultimate-style reference layer: right_bars=2 swing pivots are the
    # visual HH/HL/LH/LL turns used to reject OBs that occur mid-trend leg.
    wave_ref=wave_fractal_pivots(klines,2,'wave_ref')
    sweeps=sweep_from_pivots(klines,swing,atr)
    swing_struct=display_structure_lux(klines,swing,'swing',wave_ref,max_wave_distance=3)
    internal_struct=display_structure_lux(klines,internal,'internal',wave_ref,max_wave_distance=3)
    for e in swing_struct + internal_struct:
        e['is_mss']=False
        e['is_mss_confirmed']=False
        e['mss_reason']=''
    swing_keys={(e.get('index'), e.get('direction')) for e in swing_struct}
    internal_mss=[]
    for e in detect_independent_mss(internal_struct, sweeps, klines, atr):
        if (e.get('index'), e.get('direction')) in swing_keys:
            e['overlaps_swing_structure']=True
        internal_mss.append(e)
    structure=sorted(swing_struct + internal_mss, key=lambda x:x['index'])
    obs=order_blocks_from_structure(klines, swing_struct, atr, wave_ref)
    return {'signals':{'swings':swing,'internal_swings':internal,'wave_swings':wave_ref,'sweeps':sweeps,'swing_structure':swing_struct,'internal_structure':internal_struct,'structure':structure,'obs':obs}, 'summary':{'n_bars':len(klines),'profile':{'swing_len':swing_len,'internal_len':internal_len,'core':'luxalgo_leg_currentLevel_with_wave_reference'},'n_swings':swing.get('n',0),'n_wave_ref_swings':wave_ref.get('n',0),'n_swing_structure':len(swing_struct),'n_internal_structure':len(internal_struct),'n_internal_mss':len(internal_mss),'n_structure':len(structure),'n_sweeps':len(sweeps),'n_obs':len(obs),'definition_version':'smc_core_v46_2_luxalgo_leg_currentLevel'}}

if __name__=='__main__':
    import json, sys
    ks=json.loads(open(sys.argv[1]).read())
    print(json.dumps(detect_all_signals_lux_v34(ks)['summary'],ensure_ascii=False,indent=2))
