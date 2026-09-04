#!/usr/bin/env python3
"""
V28 SMC Unifed Engine — 纯血SMC质量分层 + 自适应出场 + 多周期共振
Built on V27 strict event-based signal detection.

A. SIGNAL QUALITY: OB(STRONG/MEDIUM/WEAK) OTE(STRONG/MEDIUM/WEAK)
   BPR(HIGH_TRUST/LOW_TRUST/PENNY) Structure(COMPLETE/PARTIAL/BROKEN)
   MSS(PRESENT/NONE) Sweep(PRESENT/NONE) Cost(INSIDE/NEAR/FAR)

B. ADAPTIVE EXITS: Structural SL + Cost-line SL + Breakeven
   TP1(40%)/TP2(30%)/TRAIL(30%) — market-state adaptive trailing

C. MTF RESONANCE: Weekly trend + Daily structure + Market state → ALIGNED/PARTIAL/CONFLICT
"""

import json, sys, math
from pathlib import Path
from collections import defaultdict, Counter
from typing import List, Dict, Optional, Tuple
sys.path.insert(0, '/root/.hermes/scripts/v25')
import smc_core_v27 as v27

MIN_QUALITY = 5.5; MIN_RR = 1.2; MAX_HOLD_BARS = 60; MIN_HOLD_BARS = 2
ZONE_BASE = {'OB': 3.0, 'OTE': 2.2, 'BPR': 0.6}
CONF_BASE = {'PINBAR': 1.8}


def smart_money_cost_line(zone, klines, entry_idx):
    zl = float(zone.get('zone_low', 0) or zone.get('invalidation', 0) or 0)
    zh = float(zone.get('zone_high', 0) or 0)
    zi = int(zone.get('index', entry_idx))
    if zl <= 0 or zh <= 0: return 0.0
    try:
        b = klines[min(zi, len(klines)-1)]
        o, h, l, c = [float(b.get(k, 0)) for k in ('o', 'h', 'l', 'c')]
        if min(o, h, l, c) > 0:
            typical = (h + l + 2 * c) / 4
            return round(max(zl, min(zh, typical)), 4)
    except: pass
    return round((zl + zh) / 2, 4)


def market_state(klines, idx):
    if idx < 60: return 'UNKNOWN'
    closes = [float(b.get('c', 0)) for b in klines]
    c = closes[idx]; ma20 = sum(closes[idx-19:idx+1]) / 20
    ma60 = sum(closes[idx-59:idx+1]) / 60
    atr = v27.compute_atr_pct(klines, idx) * 100
    h60 = max(float(b.get('h', 0)) for b in klines[idx-59:idx+1])
    l60 = min(float(b.get('l', 0)) for b in klines[idx-59:idx+1])
    rng = (h60 - l60) / max(l60, 0.01) * 100
    if atr < 1.8 or rng < 8: return 'RANGE'
    if c > ma20 > ma60: return 'TREND_UP'
    if c < ma20 < ma60: return 'TREND_DOWN'
    if atr > 5.5: return 'HIGH_VOL'
    return 'TRANSITION'


# ─── Quality Grades ───

def ob_grade(st, klines):
    zone_idx = st.get('zone_idx', st.get('zone', {}).get('index', 0))
    entry_idx = st.get('entry_index', 0)
    ev_idx = st.get('event_index', entry_idx - 1)
    atr = float(st.get('atr_pct', 0) or 0)
    score = 0.0
    age = max(0, entry_idx - zone_idx)
    if age <= 5: score += 2.0
    elif age <= 15: score += 1.0
    elif age <= 30: score -= 0.5
    else: score -= 1.5
    if atr > 0 and ev_idx > 0 and ev_idx < len(klines):
        ev_body = abs(float(klines[ev_idx].get('c', 0)) - float(klines[ev_idx].get('o', 0)))
        ev_range = float(klines[ev_idx].get('h', 0)) - float(klines[ev_idx].get('l', 0))
        if ev_range > 0:
            body_ratio = ev_body / ev_range
            if body_ratio >= 0.7: score += 2.0
            elif body_ratio >= 0.4: score += 1.0
            else: score -= 0.5
    entry = float(st.get('entry_price', 0))
    zh = float(st.get('zone_high', st.get('zone', {}).get('zone_high', 0)))
    if entry and zh:
        dist = (entry - zh) / entry * 100
        if dist <= 0.3: score += 1.5
        elif dist <= 1.0: score += 0.5
        elif dist <= 2.0: score -= 0.5
        else: score -= 1.5
    if score >= 3.5: return 'STRONG', score
    elif score >= 1.5: return 'MEDIUM', score
    return 'WEAK', score


def ote_grade(st, klines):
    entry = float(st.get('entry_price', 0))
    zl = float(st.get('zone_low', st.get('zone', {}).get('zone_low', 0)))
    zh = float(st.get('zone_high', st.get('zone', {}).get('zone_high', 0)))
    rr = float(st.get('rr', 0) or 0)
    atr = float(st.get('atr_pct', 0) or 0)
    score = 0.0
    if zl and zh and entry:
        retrace_pos = (entry - zl) / max(zh - zl, 0.0001)
        if 0.3 <= retrace_pos <= 0.7: score += 2.0
        elif 0.15 <= retrace_pos <= 0.85: score += 1.0
        else: score -= 1.0
    if rr >= 2.5: score += 1.5
    elif rr >= 1.8: score += 0.8
    elif rr < 1.2: score -= 1.0
    if 2.0 <= atr * 100 <= 6.0: score += 0.5
    if score >= 3.0: return 'STRONG', score
    elif score >= 1.2: return 'MEDIUM', score
    return 'WEAK', score


def bpr_grade(st):
    zl = float(st.get('zone_low', st.get('zone', {}).get('zone_low', 0)))
    zh = float(st.get('zone_high', st.get('zone', {}).get('zone_high', 0)))
    score = 0.0
    if zl and zh and zh > zl:
        width = (zh - zl) / zl * 100
        if width >= 1.0: score += 2.0
        elif width >= 0.5: score += 0.5
        else: score -= 2.0
    score -= 0.5
    if st.get('conf_type') == 'PINBAR': score += 1.0
    if score >= 1.0: return 'HIGH_TRUST', score
    elif score >= -1.0: return 'LOW_TRUST', score
    return 'PENNY', score


def event_chain_grade(st):
    et = st.get('source_event', '')
    has_sweep = st.get('has_sweep_precursor', False)
    zt = st.get('zone_type', '')
    conf = st.get('conf_type', '')
    score = 0.0
    if et == 'MSS' and has_sweep: score += 3.0
    elif et == 'MSS': score += 2.0
    elif et == 'CHOCH': score += 1.5
    elif et == 'BOS': score += 1.0
    else: score -= 1.0
    if zt in ('OB', 'OTE'): score += 1.0
    elif zt == 'BPR': score -= 0.3
    if conf: score += 1.0
    else: score -= 1.5
    if score >= 3.5: return 'COMPLETE', score
    elif score >= 1.5: return 'PARTIAL', score
    return 'BROKEN', score


def cost_proximity_grade(st, klines):
    entry = float(st.get('entry_price', 0))
    cost = float(st.get('smart_money_cost', 0))
    if not entry or not cost: return 'UNKNOWN', 0
    dist_pct = abs(entry - cost) / entry * 100
    if dist_pct <= 0.5: return 'INSIDE_COST_ZONE', 2.0
    elif dist_pct <= 1.0: return 'INSIDE_COST_ZONE', 1.5
    elif dist_pct <= 2.0: return 'NEAR_COST', 0.5
    elif dist_pct <= 3.0: return 'NEAR_COST', 0.0
    return 'FAR', -1.5


def quality_score(st, klines):
    score = 0.0
    zt = st.get('zone_type', '')
    score += ZONE_BASE.get(zt, 0.5)
    score += CONF_BASE.get(st.get('conf_type', ''), 0.0)
    rr = float(st.get('rr', 0) or 0)
    score += min(rr, 3.0) * 0.7
    atr = float(st.get('atr_pct', 0) or 0) * 100
    if 2.0 <= atr <= 6.0: score += 1.0
    elif atr < 2.0: score -= 1.5
    elif atr > 8.0: score -= 1.0
    entry = float(st.get('entry_price', 0))
    zh = float(st.get('zone_high', st.get('zone', {}).get('zone_high', 0)))
    if entry and zh:
        dist = (entry - zh) / entry * 100
        if dist <= 0.5: score += 1.5
        elif dist <= 1.5: score += 0.5
        else: score -= 1.5
    if st.get('source_event') == 'MSS': score += 0.5
    if st.get('has_sweep_precursor'): score += 0.8
    if zt == 'BPR': score -= 1.2
    if zt == 'BPR' and st.get('conf_type') == 'PINBAR': score += 0.6
    ms = market_state(klines, st.get('entry_index', 0))
    if ms == 'TREND_UP': score += 1.5
    elif ms == 'RANGE': score -= 2.0
    elif ms == 'TREND_DOWN': score -= 1.0
    elif ms == 'HIGH_VOL': score -= 0.3
    return round(score, 2)


def classify_signal(st, klines):
    zt = st.get('zone_type', ''); grades = {}
    if zt == 'OB':
        g, s = ob_grade(st, klines); grades['ob_grade'] = g; grades['ob_score'] = round(s, 2)
    elif zt == 'OTE':
        g, s = ote_grade(st, klines); grades['ote_grade'] = g; grades['ote_score'] = round(s, 2)
    elif zt == 'BPR':
        g, s = bpr_grade(st); grades['bpr_grade'] = g; grades['bpr_score'] = round(s, 2)
    g2, s2 = event_chain_grade(st)
    grades['structure'] = g2; grades['structure_score'] = round(s2, 2)
    g3, s3 = cost_proximity_grade(st, klines)
    grades['cost_proximity'] = g3; grades['cost_proximity_score'] = round(s3, 2)
    grades['mss'] = 'PRESENT' if st.get('source_event') == 'MSS' else 'NONE'
    grades['sweep'] = 'PRESENT' if st.get('has_sweep_precursor') else 'NONE'
    return grades


def enhance_setups(setups, klines):
    out = []
    for st in setups:
        entry_idx = st.get('entry_index', 0)
        zone = st.get('zone', {}) or {'zone_low': st.get('zone_low'), 'zone_high': st.get('zone_high'), 'index': st.get('zone_idx')}
        cost = smart_money_cost_line(zone, klines, entry_idx)
        st['smart_money_cost'] = cost
        st['market_state'] = market_state(klines, entry_idx)
        ms = st['market_state']
        if ms in ('TREND_DOWN', 'TRANSITION'): continue
        q = quality_score(st, klines)
        if q < MIN_QUALITY: continue
        if float(st.get('rr', 0) or 0) < MIN_RR: continue
        if st.get('zone_type') == 'BPR' and q < 7.0: continue
        grades = classify_signal(st, klines)
        st.update(grades); st['quality_score'] = q; st['engine'] = 'V28_PURE_SMC'
        out.append(st)
    return out


# ─── B. ADAPTIVE EXITS ───

TRAIL_PARAMS = {
    'TREND_UP':     (1.8, 0.60, 0.25, 0.8),
    'TREND_DOWN':   (1.2, 0.50, 0.20, 0.6),
    'HIGH_VOL':     (2.0, 0.65, 0.35, 1.0),
    'RANGE':        (1.0, 0.35, 0.15, 0.5),
    'TRANSITION':   (1.3, 0.45, 0.20, 0.7),
    'UNKNOWN':      (1.3, 0.45, 0.20, 0.7),
}


def structural_sl(klines, st):
    entry_idx = st.get('entry_index', 0)
    entry = float(st.get('entry_price', 0))
    if entry_idx < 10 or entry <= 0: return None
    best_px = None; best_dist = 999
    for i in range(entry_idx - 3, max(0, entry_idx - 60), -1):
        b = klines[i]; lo = float(b.get('l', 0))
        if lo <= 0 or lo >= entry: continue
        left_ok = i < 1 or float(klines[i-1].get('l', 0)) > lo
        right_ok = i + 1 >= entry_idx or float(klines[i+1].get('l', 0)) > lo
        if left_ok and right_ok:
            dist = entry_idx - i
            if dist < best_dist: best_px = lo; best_dist = dist
    return best_px


def adaptive_exit_plan(st, klines):
    entry = float(st['entry_price']); idx = st['entry_index']
    atr = v27.compute_atr_pct(klines, idx)
    zl = float(st.get('zone_low', st.get('zone', {}).get('zone_low', 0)))
    zh = float(st.get('zone_high', st.get('zone', {}).get('zone_high', 0)))
    cost = float(st.get('smart_money_cost', 0) or (zl + zh) / 2)
    ms = st.get('market_state', 'UNKNOWN')
    q = float(st.get('quality_score', 5.0))
    trigger_r, lock_r, sl_expand, breakeven_r = TRAIL_PARAMS.get(ms, TRAIL_PARAMS['UNKNOWN'])

    swing_sl = structural_sl(klines, st)
    if cost and zl: cost_sl = max(zl * 0.995, cost * 0.998)
    elif cost: cost_sl = cost * 0.998
    else: cost_sl = entry * (1 - max(0.018, atr * 0.7))
    atr_sl = entry * (1 - max(0.015, atr * sl_expand * 3))
    candidates = [s for s in [swing_sl, cost_sl, atr_sl] if s is not None and s < entry]
    base_sl = max(candidates) if candidates else atr_sl
    if ms == 'HIGH_VOL': sl = min(base_sl, entry * (1 - atr * 1.2))
    elif ms == 'RANGE': sl = max(base_sl, entry * 0.975)
    else: sl = base_sl
    if q >= 8.5 and zl: sl = max(sl, zl * 0.998)
    if sl >= entry: sl = entry * (1 - max(0.018, atr * 0.7))
    risk = entry - sl
    if risk <= 0: risk = entry * 0.015
    tp1 = max(entry + risk * 1.3, entry * 1.025)
    tp2 = max(entry + risk * 2.5, tp1 * 1.015, entry * 1.05)
    tp3 = max(entry + risk * 3.5, tp2 * 1.01, entry * 1.07)

    if swing_sl and abs(sl - swing_sl) < entry * 0.002: sl_type = 'swing'
    elif abs(sl - cost_sl) < entry * 0.002: sl_type = 'cost'
    else: sl_type = 'atr'

    return {'sl': round(sl, 2), 'sl_type': sl_type,
            'tp1': round(tp1, 2), 'tp2': round(tp2, 2), 'tp3': round(tp3, 2),
            'risk': round(risk, 4), 'risk_pct': round(risk / entry * 100, 2),
            'trail_trigger_r': trigger_r, 'trail_lock_r': lock_r,
            'breakeven_r': breakeven_r,
            'tiers': [{'name': 'TP1', 'alloc': 0.4, 'price': round(tp1, 2)},
                       {'name': 'TP2', 'alloc': 0.3, 'price': round(tp2, 2)},
                       {'name': 'TRAIL', 'alloc': 0.3, 'price': round(tp3, 2)}],
            'quality_adjusted': q >= 8.5}


def backtest_quality_setups(setups, klines):
    trades = []; n = len(klines)
    for st in setups:
        entry_idx = st['entry_index']; entry = float(st['entry_price'])
        if entry_idx >= n - 2 or entry <= 0: continue
        plan = adaptive_exit_plan(st, klines)
        sl, tp1, tp2, tp3 = plan['sl'], plan['tp1'], plan['tp2'], plan['tp3']
        risk = plan['risk']
        remaining = 1.0; realized = 0.0; hit = []
        stop = sl; high_water = entry
        exit_idx = -1; exit_price = entry; reason = 'TIMEOUT'
        breakeven_triggered = False

        for j in range(entry_idx + 1, min(entry_idx + MAX_HOLD_BARS, n)):
            b = klines[j]
            lo = float(b.get('l', 0)); hi = float(b.get('h', 0)); cl = float(b.get('c', 0))
            if cl <= 0: continue
            high_water = max(high_water, hi)
            if not breakeven_triggered and high_water >= entry + risk * plan['breakeven_r']:
                stop = max(stop, entry * 1.001); breakeven_triggered = True
            if high_water >= entry + risk * plan['trail_trigger_r']:
                lock_dist = risk * plan['trail_lock_r']
                progress = (high_water - entry) / max(risk, 0.0001)
                if progress > 4.0: lock_dist *= 0.7
                elif progress > 2.5: lock_dist *= 0.85
                stop = max(stop, high_water - lock_dist)
            if lo <= stop:
                realized += remaining * ((stop - entry) / entry * 100)
                exit_idx = j; exit_price = stop
                reason = 'TRAILING_STOP' if stop > sl else 'SL_HIT'
                remaining = 0; break
            if 'TP1' not in hit and hi >= tp1:
                realized += 0.4 * ((tp1 - entry) / entry * 100)
                remaining -= 0.4; hit.append('TP1')
                if not breakeven_triggered:
                    stop = max(stop, entry * 1.001); breakeven_triggered = True
            if 'TP2' not in hit and hi >= tp2:
                realized += 0.3 * ((tp2 - entry) / entry * 100)
                remaining -= 0.3; hit.append('TP2'); stop = max(stop, tp1)
            if hi >= tp3 and remaining > 0:
                realized += remaining * ((tp3 - entry) / entry * 100)
                exit_idx = j; exit_price = tp3; reason = 'TP3_HIT'; remaining = 0; break

        if exit_idx < 0:
            exit_idx = min(entry_idx + MAX_HOLD_BARS, n - 1)
            exit_price = float(klines[exit_idx].get('c', entry))
            realized += remaining * ((exit_price - entry) / entry * 100)
            reason = 'TIMEOUT_PARTIAL' if hit else 'TIMEOUT'
        hold_bars = exit_idx - entry_idx
        if hold_bars < MIN_HOLD_BARS: continue
        t = {**st, **plan,
             'exit_date': klines[exit_idx].get('t', klines[exit_idx].get('date', '')),
             'exit_index': exit_idx, 'exit_price': round(exit_price, 2),
             'exit_reason': reason, 'pnl_pct': round(realized, 2),
             'hold_bars': hold_bars, 'partial_hits': hit,
             'won': realized > 0, 'breakeven_active': breakeven_triggered,
             'engine': 'V28_PURE_SMC', 'definition_version': 'smc_core_v28'}
        trades.append(t)
    return trades


# ─── C. MTF RESONANCE ───

def resample_weekly(klines):
    if len(klines) < 20: return []
    weeks = []; i = 0
    while i < len(klines):
        week_end = min(i + 4, len(klines) - 1)
        b_start = klines[i]; b_end = klines[week_end]
        try:
            o = float(b_start.get('o', 0)); c = float(b_end.get('c', 0))
            h = max(float(klines[j].get('h', 0)) for j in range(i, week_end + 1))
            l = min(float(klines[j].get('l', 0)) for j in range(i, week_end + 1))
            if min(o, c, h, l) > 0: weeks.append({'o': o, 'c': c, 'h': h, 'l': l})
        except: pass
        i += 5
    return weeks


def computed_weekly_trend(klines, idx):
    weeks = resample_weekly(klines[:idx+1])
    if len(weeks) < 20: return 'UNKNOWN'
    closes = [w['c'] for w in weeks[-20:]]
    current = closes[-1]; ma20 = sum(closes) / 20
    ma40 = sum(closes[-40:]) / min(40, len(closes)) if len(closes) >= 40 else ma20
    if current > ma20 > ma40: return 'BULLISH'
    elif current < ma20 < ma40: return 'BEARISH'
    elif current > ma20: return 'BULLISH_WEAK'
    elif current < ma20: return 'BEARISH_WEAK'
    return 'NEUTRAL'


def daily_structure_alignment(signal_data, entry_idx):
    struct = signal_data.get('structure', [])
    recent = [e for e in struct if e['index'] <= entry_idx and e['index'] >= entry_idx - 60]
    if not recent: return 'NO_STRUCTURE'
    last = recent[-1]
    d = last.get('direction', ''); et = last.get('type', '')
    if d == 'bull':
        if et == 'MSS': return 'BULLISH_MSS'
        elif et == 'CHOCH': return 'BULLISH_CHOCH'
        elif et == 'BOS': return 'BULLISH_BOS'
        return 'BULLISH'
    elif d == 'bear': return 'BEARISH'
    return 'NEUTRAL'


def resonance_score(st, klines, signal_data):
    idx = st.get('entry_index', 0)
    weekly = computed_weekly_trend(klines, idx)
    daily = daily_structure_alignment(signal_data, idx)
    score = 0.0; matches = []
    if weekly == 'BULLISH': score += 3.0; matches.append('W_BULL')
    elif weekly == 'BULLISH_WEAK': score += 1.5; matches.append('W_BULL_WEAK')
    elif weekly == 'BEARISH': score -= 3.0; matches.append('W_BEAR')
    elif weekly == 'BEARISH_WEAK': score -= 1.0; matches.append('W_BEAR_WEAK')
    if daily.startswith('BULLISH'): score += 3.0; matches.append('D_BULL')
    elif daily == 'BEARISH': score -= 2.0; matches.append('D_BEAR')
    ms = st.get('market_state', '')
    if ms == 'TREND_UP': score += 1.5
    elif ms == 'TREND_DOWN': score -= 2.0
    elif ms == 'RANGE': score -= 3.0
    if score >= 5.0: label = 'ALIGNED'
    elif score >= 2.0: label = 'PARTIAL'
    elif score >= -2.0: label = 'WEAK'
    else: label = 'CONFLICT'
    return {'resonance': label, 'resonance_score': round(score, 2),
            'weekly': weekly, 'daily_structure': daily, 'matches': matches}


# ─── MAIN PIPELINE ───

def detect_build_backtest(klines, symbol=''):
    r = v27.detect_all_signals_v27(klines)
    setups = v27.build_bullish_setups(r['signals'], klines)
    enhanced = enhance_setups(setups, klines)
    for st in enhanced:
        res = resonance_score(st, klines, r['signals'])
        st.update(res)
    # Filter CONFLICT resonance — weekly/daily direction conflict, must skip
    enhanced = [st for st in enhanced if st.get('resonance') != 'CONFLICT']
    trades = backtest_quality_setups(enhanced, klines)
    for t in trades:
        if symbol: t['symbol'] = symbol
        t['ctx_seq'] = f"{t.get('zone_type','')}→{t.get('source_event','')}→{t.get('conf_type','')}"
        t['seq'] = f"{t.get('zone_type','')}-{t.get('source_event','')}-{t.get('conf_type','')}"
        t['detail'] = t['ctx_seq']
    return {'signals': r['signals'], 'summary': r['summary'],
            'setups': enhanced, 'trades': trades}
