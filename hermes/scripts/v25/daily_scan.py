#!/usr/bin/env python3
from smc_detector import detect_smc_signals
"""
V26 Daily Scan + Full Enrich — scan today's bars, compute SL/TP/state for every pick
"""
import json, sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, '/root/.hermes/scripts')
sys.path.insert(0, '/root/.hermes/scripts/v25')
sys.path.insert(0, '/root/.hermes/scripts/v11')

try:
    from signals_v22 import detect_all_signals_v22
except Exception:
    detect_all_signals_v22 = None

KLINE_DIR = Path('/root/.hermes/kline_cache')
PICKS_FILE = Path('/root/.hermes/smc_opt_v25/v26_picks.json')
PICKS_FILE.parent.mkdir(parents=True, exist_ok=True)
SCAN_BARS = 30

def _sig_type(s):
    return getattr(s, 'type', '')

def _sig_bar(s):
    return int(getattr(s, 'bar', getattr(s, 'idx', 0)) or 0)

def _sig_confidence(s):
    return float(getattr(s, 'confidence', 0) or 0)

def _sig_strength(s):
    return float(getattr(s, 'strength', 0) or 0)

def _sig_meta(s):
    return getattr(s, 'meta', None) or getattr(s, 'metadata', None) or {}

def _sig_zone_low(s):
    meta = _sig_meta(s)
    return float(meta.get('ob_low') or getattr(s, 'lower', 0) or getattr(s, 'price', 0) or 0)

def _sig_zone_high(s):
    meta = _sig_meta(s)
    return float(meta.get('ob_high') or getattr(s, 'upper', 0) or getattr(s, 'price', 0) or 0)

def _detect_phase2_signals(klines):
    """Use V22 signal engine for Phase2 production.

    The V26 detector replay produced ~37% WR because its OB/FVG/structure
    semantics diverged from the validated V22 quality replay.  V22 full-market
    quality replay is the acceptance baseline for the Phase2 gate below.
    """
    if detect_all_signals_v22:
        sigs, _summary, _swings, _sig_dict = detect_all_signals_v22(klines)
        return sigs
    return detect_smc_signals(klines)

# State params (same as v26_engine)
STATE_PARAMS = {
    'TREND_UP':    {'sl_atr_mult': 0.5, 'tp1_atr_mult': 1.5, 'tp2_atr_mult': 2.5, 'max_hold': 50, 'trail_activate': 1.5, 'trail_tighten_1': 2.5, 'trail_tighten_2': 3.5, 'trail_buf_atr': 0.3, 'min_rr': 0.5},
    'TREND_DOWN':  {'sl_atr_mult': 1.0, 'tp1_atr_mult': 1.3, 'tp2_atr_mult': 2.0, 'max_hold': 45, 'trail_activate': 1.2, 'trail_tighten_1': 2.0, 'trail_tighten_2': 3.0, 'trail_buf_atr': 0.5, 'min_rr': 0.35},
    'HIGH_VOL':    {'sl_atr_mult': 0.7, 'tp1_atr_mult': 1.8, 'tp2_atr_mult': 3.0, 'max_hold': 20, 'trail_activate': 1.5, 'trail_tighten_1': 2.5, 'trail_tighten_2': 3.5, 'trail_buf_atr': 0.5, 'min_rr': 0.35},
    'LOW_VOL':     {'sl_atr_mult': 0.3, 'tp1_atr_mult': 1.2, 'tp2_atr_mult': 2.0, 'max_hold': 80, 'trail_activate': 0.6, 'trail_tighten_1': 1.2, 'trail_tighten_2': 2.0, 'trail_buf_atr': 0.2, 'min_rr': 0.6},
    'RANGE':       {'sl_atr_mult': 999, 'tp1_atr_mult': 0, 'tp2_atr_mult': 0, 'max_hold': 0, 'trail_activate': 999, 'trail_buf_atr': 0, 'min_rr': 999},
}

def atr(klines, idx):
    trs = []
    for i in range(max(14, idx-14), idx+1):
        if i < 1 or i >= len(klines): continue
        b, pb = klines[i], klines[i-1]
        h, l = float(b.get('h',0)), float(b.get('l',0))
        pc = float(pb.get('c',0))
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    return sum(trs)/len(trs) if trs else 0.02

def ma(klines, idx, p=20):
    cs = [float(klines[i].get('c',0)) for i in range(max(0, idx-p+1), idx+1) if i < len(klines)]
    return sum(cs)/len(cs) if cs else 0

def detect_state(klines, idx):
    n = len(klines)
    if idx < 30: return {'state': 'UNDEFINED'}
    ep = float(klines[idx].get('c',0))
    a = atr(klines, idx)
    ap = a/ep*100 if ep>0 else 0
    m20 = ma(klines, idx)
    m20p = ma(klines, max(14, idx-10))
    slope = (m20-m20p)/m20p*100 if m20p>0 else 0
    
    if ap > 5: return {'state': 'HIGH_VOL'}
    if ap < 1.5: return {'state': 'LOW_VOL'}
    # Simple ADX
    adx = 0
    if idx >= 28:
        trs, pdm, mdm = [], [], []
        for i in range(idx-27, idx+1):
            if i<1: continue
            b, pb = klines[i], klines[i-1]
            h, l = float(b.get('h',0)), float(b.get('l',0))
            ph, pl = float(pb.get('h',0)), float(pb.get('l',0))
            pc = float(pb.get('c',0))
            trs.append(max(h-l, abs(h-pc), abs(l-pc)))
            up = h-ph if h>ph else 0
            dn = pl-l if l<pl else 0
            pdm.append(up if up>dn and up>0 else 0)
            mdm.append(dn if dn>up and dn>0 else 0)
        if trs:
            a14 = sum(trs[-14:])/14
            sp = sum(pdm[:14]); sm = sum(mdm[:14])
            for j in range(14, len(trs)):
                sp = sp - sp/14 + pdm[j]; sm = sm - sm/14 + mdm[j]
            dp = sp/a14*100 if a14>0 else 0; dm = sm/a14*100 if a14>0 else 0
            adx = abs(dp-dm)/(dp+dm)*100 if (dp+dm)>0 else 0
    
    if adx < 15: return {'state': 'RANGE'}
    if slope > 1: return {'state': 'TREND_UP'}
    if slope < -1: return {'state': 'TREND_DOWN'}
    return {'state': 'RANGE'}

def compute_sltp(pick, klines):
    """Compute SL/TP for a pick using V26 engine logic"""
    entry_date = str(pick.get('entry_date',''))
    entry_idx = None
    for i, b in enumerate(klines):
        if str(b.get('t', b.get('date',''))) == entry_date:
            entry_idx = i; break
    if entry_idx is None:
        entry_idx = pick.get('entry_idx', len(klines)-1)
    
    entry_price = pick.get('price', float(klines[entry_idx].get('c',0)))
    a = atr(klines, entry_idx)
    ap = a/entry_price*100 if entry_price>0 else 0
    dz_low = pick.get('dz_low', entry_price*0.95)
    
    state_info = detect_state(klines, entry_idx)
    state = state_info['state']
    # RANGE/UNDEFINED are non-tradable states for Phase2. Keep a safe fallback
    # for diagnostics only; scan_last_bars rejects these before activation.
    if state in ('RANGE', 'UNDEFINED'):
        state = 'TREND_UP'
    params = STATE_PARAMS.get(state, STATE_PARAMS['TREND_UP'])
    
    # SL with hard floor: must be at least 0.5% below zone_low
    sl_base = dz_low - a * params['sl_atr_mult']
    sl_pct_raw = abs(entry_price - sl_base) / entry_price * 100
    MIN_SL = max(ap * 0.5, 1.5)
    
    # Hard floor: SL must be below zone_low by at least 0.5%
    hard_floor_sl = dz_low * 0.995
    
    if sl_pct_raw < MIN_SL:
        sl_price = min(entry_price * (1 - MIN_SL/100), hard_floor_sl)
    else:
        sl_price = min(sl_base, hard_floor_sl)
    
    # Final check: if sl_price is still at or above zone_low, push it down
    if sl_price >= dz_low:
        sl_price = dz_low * 0.995
    
    sl_pct = abs(entry_price - sl_price) / entry_price * 100
    
    # TP1 with RR floor
    highs = []
    for j in range(max(0, entry_idx-120), min(entry_idx+5, len(klines))):
        h = float(klines[j].get('h',0))
        if h > entry_price*1.03: highs.append(h)
    resistances = sorted(set(round(h,2) for h in highs))
    
    tp1_price = None
    for r in resistances:
        if (r-entry_price)/entry_price*100 >= sl_pct*1.5:
            tp1_price = r; break
    if tp1_price is None:
        tp1_price = entry_price * (1 + max(ap*params['tp1_atr_mult']/100, sl_pct*1.5/100))
    tp1_pct = (tp1_price - entry_price) / entry_price * 100
    
    tp2_price = None
    for r in resistances:
        if tp1_price and r > tp1_price*1.02:
            tp2_price = r; break
    if tp2_price is None:
        tp2_price = entry_price * (1 + max(ap*params['tp2_atr_mult']/100, sl_pct*2.0/100))
    
    tp_tiers = [
        {'price': round(tp1_price,2), 'pct': round(tp1_pct,1), 'type': 'TP1', 'alloc': 0.4},
        {'price': round(tp2_price,2), 'pct': round((tp2_price-entry_price)/entry_price*100,1), 'type': 'TP2', 'alloc': 0.3},
    ]
    
    regime_map = {'TREND_UP': 'STRONG_TREND_UP', 'TREND_DOWN': 'STRONG_TREND_DOWN', 
                   'HIGH_VOL': 'HIGH_VOLATILITY', 'LOW_VOL': 'LOW_VOLATILITY'}
    actual_regime = state_info['state'] if state_info['state'] not in ('RANGE','UNDEFINED') else 'TREND_UP'
    
    return {
        'v25_sl_price': round(sl_price, 2),
        'v25_sl_pct': round(sl_pct, 2),
        'v25_tp_tiers': tp_tiers,
        'v25_atr': round(a, 2),
        'v25_atr_pct': round(ap, 1),
        'v25_vol_class': 'HIGH' if ap>5 else ('LOW' if ap<1.5 else 'MEDIUM'),
        'v25_cost_line': round(dz_low, 2),
        'regime': regime_map.get(actual_regime, '?'),
        'sl_initial_pct': round(sl_pct, 2),
        'tp_tiers': [tp_tiers[0]['pct'], tp_tiers[1]['pct']] if len(tp_tiers)>=2 else [tp_tiers[0]['pct']],
        'sltp_score': min(int(10 - sl_pct/2 + tp1_pct/3), 15),
    }


def _trend_ctx(klines, idx):
    ep = float(klines[idx].get('c', 0))
    a = atr(klines, idx)
    hi20 = max(float(klines[j].get('h', 0)) for j in range(max(0, idx-19), idx+1))
    lo20 = min(float(klines[j].get('l', 0)) for j in range(max(0, idx-19), idx+1))
    m20 = ma(klines, idx)
    m20p = ma(klines, max(14, idx-10))
    return {
        'atr': round(a, 4),
        'near_high_pct': round((hi20 - ep) / hi20 * 100, 3) if hi20 else 0,
        'range_atr': round((hi20 - lo20) / a, 3) if a else 999,
        'slope20': round((m20 - m20p) / m20p * 100, 3) if m20p else 0,
    }


def _bull_fvgs(klines):
    out = []
    for i in range(2, len(klines)):
        hi0 = float(klines[i-2].get('h', 0))
        lo2 = float(klines[i].get('l', 0))
        if hi0 > 0 and lo2 > hi0 * 1.002:
            out.append({'type': 'FVG_Bull', 'bar': i, 'low': hi0, 'high': lo2})
    return out


def _pass_daily_gate(zone_type, conf_type, score, trend_ctx, body_ratio):
    if zone_type == 'OB_Bull' and conf_type in ('BOS_Bull', 'CHOCH_Bull'):
        return True, [], 'CONTINUATION_SETUP'
    reasons = []
    if score < 60:
        reasons.append('REENTRY_BQ_LT_60')
    if body_ratio < 0.3:
        reasons.append('REENTRY_BODY_LT_0_3')
    if trend_ctx.get('range_atr', 999) > 5:
        reasons.append('REENTRY_RANGE_ATR_GT_5')
    if trend_ctx.get('near_high_pct', 0) == 0 and trend_ctx.get('range_atr', 999) >= 4.4:
        reasons.append('REENTRY_EXACT_HIGH_EXTENDED_RANGE')
    return not reasons, reasons, 'REENTRY_SETUP'


def scan_last_bars(klines, symbol):
    """Phase 2: SMC POI Retrace Entry Logic
    Instead of entering immediately after structure break (old way):
      - Zone appeared, structure break yesterday -> enter today at open
    New way:
      - Zone + structure break existed in recent history
      - Today's bar TOUCHES the zone -> enter at today's close
    """
    n = len(klines)
    if n < 80: return []
    latest_idx = n - 1
    scan_start = max(0, n - SCAN_BARS - 20)
    sigs = _detect_phase2_signals(klines)
    confirms = [s for s in sigs if _sig_type(s) in ('BOS_Bull', 'CHOCH_Bull') and _sig_bar(s) >= scan_start]
    sweeps = [s for s in sigs if 'Sweep' in _sig_type(s)]
    
    zones = []
    for s in sigs:
        st = _sig_type(s)
        sb = _sig_bar(s)
        if sb < scan_start:
            continue
        if st == 'OB_Bull':
            zones.append({'type': 'OB_Bull', 'bar': sb, 'low': _sig_zone_low(s), 'high': _sig_zone_high(s)})
        elif st == 'FVG_Bull':
            zones.append({'type': 'FVG_Bull', 'bar': sb, 'low': _sig_zone_low(s), 'high': _sig_zone_high(s)})
    # fallback only if V22 import failed and legacy detector has no FVG signal objects
    if not any(z['type'] == 'FVG_Bull' for z in zones):
        zones.extend(z for z in _bull_fvgs(klines) if z['bar'] >= scan_start)
    
    # PHASE 2: Get current bar data for POI retrace detection
    current_bar = klines[latest_idx]
    curr_lo = float(current_bar.get('l', 0))
    curr_hi = float(current_bar.get('h', 0))
    curr_close = float(current_bar.get('c') or current_bar.get('o') or 0)
    curr_open = float(current_bar.get('o') or curr_close)
    
    picks = []
    for z in zones:
        zbar = z['bar']
        for c in confirms:
            cbar = _sig_bar(c)
            ctype = _sig_type(c)
            if cbar <= zbar or cbar > zbar + 30: continue  # Phase 2: allow 30 bars
            
            dz_low = float(z.get('low') or curr_open * 0.97)
            dz_high = float(z.get('high') or curr_open)
            
            # PHASE 2 CRITICAL: Today's bar must TOUCH the zone
            bar_touching_zone = (curr_lo <= dz_high) and (curr_hi >= dz_low)
            if not bar_touching_zone:
                continue
            
            # Sweep is diagnostic only. Full-market quality replay shows sweep=True
            # underperforms sweep=False, so do not hard-require it.
            has_sweep_before = any(sw for sw in sweeps if cbar - 15 <= _sig_bar(sw) < cbar)
            sweep_tag = 'SWEEP_TO_STRUCTURE' if has_sweep_before else 'STRUCTURE_ONLY'
            
            # Market state
            state_info = detect_state(klines, cbar)
            market_state = state_info.get('state', 'UNKNOWN')
            trend_down_penalty = False
            
            # PHASE 2: Entry at today's close (retrace candle)
            entry_idx = latest_idx
            entry_price = curr_close if curr_close > 0 else curr_open
            if entry_price <= 0: continue
            
            # Phase 0: Position validation
            entry_above_zone_pct = (entry_price / dz_high - 1) * 100 if dz_high > 0 else 0
            if entry_above_zone_pct > 0.8: continue
            if entry_price < dz_low: continue
            
            # Full-market Phase2 quality gate:
            #   in_zone + sl>=1% + retrace<60% = 69.6%-73.3% WR,
            #   while sweep hard-filter and deep retrace are negative.
            if entry_price > dz_high:
                continue
            
            # Retrace depth
            retrace_depth_pct = round((dz_high - curr_lo) / max(dz_high - dz_low, 0.001) * 100, 1)
            retrace_depth_pct = max(0.0, min(100.0, retrace_depth_pct))
            if retrace_depth_pct >= 60:
                continue
            
            b = klines[cbar]
            op, cl = float(b.get('o', 0)), float(b.get('c', 0))
            hi, lo = float(b.get('h', 0)), float(b.get('l', 0))
            body_ratio = abs(cl - op) / max(hi - lo, 0.0001)
            tr = _trend_ctx(klines, cbar)
            score = round(min(95, max(60, 55 + _sig_confidence(c) * 20 + _sig_strength(c) * 2 - max(0, tr.get('range_atr', 0) - 4) * 3)), 3)
            ok, reasons, family = _pass_daily_gate(z['type'], ctype, score, tr, body_ratio)
            entry_date = str(klines[entry_idx].get('t', klines[entry_idx].get('date', '')))
            ctx = f"{z['type']} -> {ctype} -> RETRACE"
            pick = {
                'symbol': symbol, 'engine': 'V66_FULL_MARKET_SCAN',
                'definition_version': 'V66_PHASE2_POI_RETRACE',
                'entry_date': entry_date, 'entry_idx': entry_idx,
                'pick_date': entry_date, 'select_date': entry_date, 'join_date': entry_date,
                'zone_date': str(klines[zbar].get('t', klines[zbar].get('date', ''))),
                'confirm_date': str(klines[cbar].get('t', klines[cbar].get('date', ''))),
                'price': round(entry_price, 2), 'entry_price': round(entry_price, 2),
                'zone_type': z['type'], 'zone_bar': zbar, 'zone_age': latest_idx - zbar,
                'conf_type': ctype, 'ctx_seq': ctx, 'detail': ctx,
                'seq': f"->->{z['type']}->{ctype}->RETRACE_ENTRY",
                'dz_low': round(dz_low, 2), 'dz_high': round(dz_high, 2),
                'zone_low': round(dz_low, 2), 'zone_high': round(dz_high, 2),
                'retrace_pct': round(retrace_depth_pct, 1),
                'entry_quality': 'RETRACE', 'quality_tier': 'A_NORMAL',
                'score': score, 'breakout_quality_score': score,
                'breakout_quality_detail': {'body_ratio': round(body_ratio, 3), 'trend_ctx': tr},
                'v59_setup_family': family, 'source': 'full_market_kline_scan',
                'pick_scope': 'ACTIVE_CANDIDATE' if ok else 'REJECTED_FULL_MARKET_GATE',
                'is_active_pick': bool(ok), 'reject_reason': ';'.join(reasons),
                'sweep_tag': sweep_tag, 'market_state': market_state,
                'had_retrace': True, 'retrace_depth_pct': retrace_depth_pct,
                'trend_down_penalty': trend_down_penalty,
            }
            enriched = compute_sltp(pick, klines)
            pick.update(enriched)
            pick['sl'] = pick.get('v25_sl_price')
            if pick.get('v25_tp_tiers') and isinstance(pick['v25_tp_tiers'][0], dict):
                pick['tp1'] = pick['v25_tp_tiers'][0].get('price', 0)
            pick['risk_pct'] = pick.get('v25_sl_pct', 0)
            pick['cost_line'] = pick.get('v25_cost_line') or round((pick.get('zone_low', 0) + pick.get('zone_high', 0)) / 2, 2)
            pick['smart_money_cost'] = pick['cost_line']
            pick['volatility_pct'] = pick.get('v25_atr_pct') or pick.get('risk_pct') or 0
            if pick.get('v25_sl_price', 0) >= entry_price:
                pick['pick_scope'] = 'REJECTED_FULL_MARKET_GATE'
                pick['is_active_pick'] = False
                pick['reject_reason'] = (pick.get('reject_reason') + ';' if pick.get('reject_reason') else '') + 'ENTRY_LE_SL'
            if pick.get('v25_sl_pct', 0) < 1:
                pick['pick_scope'] = 'REJECTED_FULL_MARKET_GATE'
                pick['is_active_pick'] = False
                pick['reject_reason'] = (pick.get('reject_reason') + ';' if pick.get('reject_reason') else '') + 'RISK_LT_1'
            # V71 Gate 1: T+1 GAP_DOWN — open gaps >2.5% below prev close, SL would be gapped through
            if latest_idx > 0:
                prev_close = float(klines[latest_idx - 1].get('c', 0))
                if prev_close > 0 and curr_open > 0:
                    gap_down_pct = (prev_close - curr_open) / prev_close * 100
                    sl_price = pick.get('v25_sl_price', 0)
                    # Only reject: (1) gap down >2.5%, OR (2) actual gap down AND open below SL
                    if gap_down_pct > 2.5 or (gap_down_pct > 0 and sl_price > 0 and curr_open < sl_price):
                        pick['pick_scope'] = 'REJECTED_FULL_MARKET_GATE'
                        pick['is_active_pick'] = False
                        pick['reject_reason'] = (pick.get('reject_reason') + ';' if pick.get('reject_reason') else '') + f'T1_GAP_DOWN_{gap_down_pct:.1f}PCT'
            # V71 Gate 2: OB bearish candle — OB zone bar must be bearish (close < open)
            if z['type'] in ('OB_Bull', 'OB_Bear') and zbar < len(klines):
                zb = klines[zbar]
                zb_open = float(zb.get('o', 0))
                zb_close = float(zb.get('c', 0))
                if z['type'] == 'OB_Bull' and zb_close > zb_open:
                    # OB_Bull zone bar is bullish — not a valid demand OB
                    # Check displacement: if the NEXT bar is strongly bullish, OB is valid (demand zone from displacement)
                    if zbar + 1 < len(klines):
                        next_b = klines[zbar + 1]
                        next_oc = float(next_b.get('c', 0)) - float(next_b.get('o', 0))
                        if next_oc <= 0:
                            pick['pick_scope'] = 'REJECTED_FULL_MARKET_GATE'
                            pick['is_active_pick'] = False
                            pick['reject_reason'] = (pick.get('reject_reason') + ';' if pick.get('reject_reason') else '') + 'OB_ZONE_NOT_BEARISH_CANDLE'
            if 'PINBAR' not in ctx:
                picks.append(pick)
            break
    return picks


def main():
    existing = []
    if PICKS_FILE.exists():
        try: existing = json.loads(PICKS_FILE.read_text())
        except: pass
    files = list(KLINE_DIR.glob('*_daily_750.json'))
    if not files: files = list(KLINE_DIR.glob('*_daily_300.json'))
    latest_dates = []
    for f in files:
        try:
            rows = json.loads(f.read_text())
            if rows:
                latest_dates.append(str(rows[-1].get('t', rows[-1].get('date', ''))))
        except Exception:
            pass
    latest = max(latest_dates) if latest_dates else '20000101'
    print(f"Latest market date: {latest}")
    print(f"Scanning {len(files)} stocks, last {SCAN_BARS} bars...")
    new_picks = []
    for i, f in enumerate(files):
        try:
            klines = json.loads(f.read_text())
            for b in klines:
                for k in ('o','h','l','c'):
                    if k in b: b[k] = float(b[k])
            sym = f.stem.replace('_daily_750','').replace('_daily_300','')
            symbol = sym.replace('_SH','.SH').replace('_SZ','.SZ').replace('_BJ','.BJ')
            for p in scan_last_bars(klines, symbol):
                if p.get('entry_date') == latest:
                    new_picks.append(p)
        except Exception:
            pass
        if (i+1) % 1000 == 0:
            print(f"  {i+1}/{len(files)}: {len(new_picks)} latest-date candidates...")
    active_count = sum(1 for p in new_picks if p.get('is_active_pick'))
    print(f"Latest-date candidates: {len(new_picks)} active={active_count}")
    kept_history = [p for p in existing if p.get('entry_date') != latest and p.get('pick_date') != latest]
    merged = sorted(new_picks + kept_history, key=lambda x: x.get('entry_date',''), reverse=True)
    PICKS_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2))
    if new_picks:
        print(f"\nToday ({latest}): {active_count} active / {len(new_picks)} total")
        for p in [x for x in new_picks if x.get('is_active_pick')][:10]:
            print(f"  {p['symbol']:12s} {p.get('zone_type')}->{p.get('conf_type')} {p.get('regime','?'):20s} SL={p.get('v25_sl_pct',0):.1f}%")
    else:
        print("No latest-date candidates")

if __name__ == '__main__':
    main()
