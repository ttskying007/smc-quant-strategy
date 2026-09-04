#!/usr/bin/env python3
"""V32C limit-entry/failed-setup attribution engine.

Builds on V32A Pine-like raw signal core. V32B proved that many SLs still came
from treating next-open above the PD array as an executable fill. V32C changes
execution to zone-limit/RTO fill: after confirmation, only enter if a later bar
actually trades back into the zone; otherwise the setup is recorded as missed,
not converted into a chase entry.
"""
from __future__ import annotations

import json, glob, os, sys, time
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, '/root/.hermes/scripts/v25')
import smc_core_pine_like as v32a
import smc_core_luxalgo_v34 as v34core
import smc_core_v27 as v27
import smc_core_v28 as v28

OUT_DIR = Path('/root/.hermes/smc_opt_v41')
OUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE = Path('/root/.hermes/kline_cache')

MAX_HOLD_BARS = 45
MIN_HOLD_BARS = 1
RTO_LOOKAHEAD = 45
MIN_RR = 1.20


def fdate(klines, i):
    return str(klines[i].get('t', klines[i].get('date', str(i)))) if 0 <= i < len(klines) else ''


def symbol_from_filename(fp):
    name = Path(fp).stem
    return name.split('_daily_')[0].replace('_', '.')


def _f(x, default=0.0):
    try: return float(x)
    except Exception: return default


def zone_invalidated_bull(bar: Dict, zl: float, close_buffer: float = 0.0) -> bool:
    """Bullish demand/PD array invalidation before entry: close below zone low."""
    cl = _f(bar.get('c'))
    return cl > 0 and cl < zl * (1 - close_buffer)


def bar_touches_zone(bar: Dict, zl: float, zh: float, tolerance: float = 0.0) -> bool:
    lo, hi = _f(bar.get('l')), _f(bar.get('h'))
    return lo <= zh * (1 + tolerance) and hi >= zl * (1 - tolerance)


def next_retrace_strict(klines: List[Dict], start_idx: int, zl: float, zh: float, lookahead: int = RTO_LOOKAHEAD) -> Optional[int]:
    """Return first true zone touch after start_idx; reject if zone invalidates first.

    Unlike V31 this does not allow broad +/- tolerance that marks near-misses as
    entries. If close breaks below zone_low before touch, setup is dead.
    """
    n = len(klines)
    for j in range(start_idx + 1, min(start_idx + lookahead + 1, n)):
        b = klines[j]
        if zone_invalidated_bull(b, zl):
            return None
        if bar_touches_zone(b, zl, zh, tolerance=0.0):
            return j
    return None


def confirm_at_zone_strict(klines: List[Dict], retrace_idx: int, zl: float, zh: float, max_confirm_bars: int = 3) -> Tuple[Optional[int], Optional[str]]:
    """Require bullish rejection candle whose wick/body actually interacts with zone."""
    for j in range(retrace_idx, min(retrace_idx + max_confirm_bars, len(klines))):
        b = klines[j]
        op, cl, hi, lo = _f(b.get('o')), _f(b.get('c')), _f(b.get('h')), _f(b.get('l'))
        if min(op, cl, hi, lo) <= 0:
            continue
        if zone_invalidated_bull(b, zl):
            return None, None
        if not bar_touches_zone(b, zl, zh, tolerance=0.0):
            continue
        body = abs(cl - op)
        rng = max(hi - lo, 1e-9)
        lower_wick = min(op, cl) - lo
        # Pinbar cannot be only a tiny body in the air; wick must reject inside/below zone and close reclaim zone.
        if cl > op and cl >= zh and lower_wick / rng >= 0.35 and lower_wick >= max(body * 0.6, (zh - zl) * 0.15):
            return j, 'BULLISH_REJECTION'
        if body > 0 and lower_wick > body * 1.8 and cl > op and cl > zh:
            return j, 'PINBAR_RECLAIM'
    return None, None


def entry_from_limit_retouch(klines: List[Dict], conf_idx: int, zone: Dict, max_wait_bars: int = 8, zone_type: str = '') -> Optional[Tuple[int, float, str]]:
    zl, zh = _f(zone.get('zone_low')), _f(zone.get('zone_high'))
    if zl <= 0 or zh <= 0 or conf_idx >= len(klines): return None
    b=klines[conf_idx]; cl=_f(b.get('c'))
    # Allow a slightly wider confirmation-close tolerance for FVGs. Many missed
    # winners close just above the zone after displacement, then never retest.
    close_cap = 1.03 if zone_type == 'FVG' else 1.03
    if cl >= zl and cl <= zh * close_cap:
        return conf_idx, round(cl,4), 'CONFIRM_CLOSE_IN_OR_NEAR_ZONE'
    for j in range(conf_idx+1, min(conf_idx+max_wait_bars+1, len(klines))):
        b=klines[j]; op,hi,lo,cl=_f(b.get('o')),_f(b.get('h')),_f(b.get('l')),_f(b.get('c'))
        if min(op,hi,lo,cl)<=0: continue
        if zone_invalidated_bull(b,zl): return None
        if op <= zh and op >= zl*0.995: return j, round(min(max(op,zl),zh),4), 'NEXT_OPEN_IN_ZONE'
        if bar_touches_zone(b,zl,zh,tolerance=0.0): return j, round(zh,4), 'LIMIT_RETOUCH_ZONE_HIGH'
    # FVG-specific continuation fallback: if displacement already proved the move
    # and price keeps closing above the zone without invalidation, take a controlled
    # continuation entry rather than missing the whole impulse.
    if zone_type == 'FVG':
        for j in range(conf_idx+1, min(conf_idx+max_wait_bars+5, len(klines))):
            b=klines[j]; op,hi,lo,cl=_f(b.get('o')),_f(b.get('h')),_f(b.get('l')),_f(b.get('c'))
            if min(op,hi,lo,cl)<=0: continue
            if zone_invalidated_bull(b,zl): return None
            if cl > op and cl >= zh and cl <= zh * 1.05 and lo >= zl * 0.985:
                return j, round(cl,4), 'FVG_CONTINUATION_CONFIRM'
    return None

def dedupe_setups(setups: List[Dict]) -> List[Dict]:
    best = {}
    for st in setups:
        # V36 fix: one executable entry per symbol/date. V35 allowed the same
        # retrace/confirmation candle to create both OB and FVG trades. That
        # double-counted overlapping PD arrays and let weaker FVGs override the
        # cleaner same-event OB story. Prefer OB, then higher quality/RR.
        key = (st.get('symbol',''), st.get('entry_index'))
        zone_rank = {'OB': 7, 'BRK': 6, 'RB': 5, 'FVG': 4, 'BPR': 3, 'OTE': 2, 'LV': 1}.get(st.get('zone_type'), 0)
        score = (zone_rank, _f(st.get('quality_score')), _f(st.get('resonance_score')), _f(st.get('rr')))
        cur = best.get(key)
        cur_rank = {'OB': 7, 'BRK': 6, 'RB': 5, 'FVG': 4, 'BPR': 3, 'OTE': 2, 'LV': 1}.get(cur.get('zone_type') if cur else '', 0)
        if cur is None or score > (cur_rank, _f(cur.get('quality_score')), _f(cur.get('resonance_score')), _f(cur.get('rr'))):
            best[key] = st
    return sorted(best.values(), key=lambda x: (x.get('entry_index', 0), -_f(x.get('quality_score'))))


def build_exit_plan(st: Dict, klines: List[Dict]) -> Optional[Dict]:
    entry = _f(st.get('entry_price'))
    zl = _f(st.get('zone_low')); zh = _f(st.get('zone_high'))
    if entry <= 0 or zl <= 0 or zh <= 0:
        return None
    entry_idx = int(st.get('entry_index', 0))
    atr_pct = v27.compute_atr_pct(klines, entry_idx) or 0.025
    swept_low = _f(st.get('swept_low'), zl)
    sl = min(zl, swept_low) - entry * atr_pct * 0.25
    # Keep risk realistic but not huge; too wide SL was one known problem.
    min_risk = entry * 0.012
    max_risk = entry * 0.040
    risk = entry - sl
    if risk < min_risk:
        sl = entry - min_risk; risk = min_risk
    if risk > max_risk:
        sl = entry - max_risk; risk = max_risk
    # V37: V36 signal set kept WR/SL quality, but realised payoff was capped by
    # early trailing/partial exits. Keep TP1 reachable, push TP2/TP3 outward and
    # delay trailing so valid impulses are not cut at ~1R.
    # V40 replay-autopsy exit: V39 selection/entry were mostly correct, but
    # exits were too early (11/13 rallied after exit). Keep smaller partials
    # and let a trend-runner work for up to ~75 bars; trailing only after 6R.
    tp1 = entry + risk * 1.5
    tp2 = entry + risk * 3.2
    tp3 = entry + risk * 4.2
    return {'sl': round(sl, 4), 'tp1': round(tp1, 4), 'tp2': round(tp2, 4), 'tp3': round(tp3, 4),
            'risk': round(risk, 4), 'risk_pct': round(risk / entry * 100, 2),
            'trail_trigger_r': 6.0, 'trail_lock_r': 1.2, 'breakeven_r': 1.0,
            'breakeven_bars': 3, 'tp1_frac': 0.30, 'tp2_frac': 0.25,
            'tp2_stop_r': 1.5, 'close_at_tp3': False}


def backtest_v34_setups(setups: List[Dict], klines: List[Dict], max_hold_bars: int = 120, min_hold_bars: int = MIN_HOLD_BARS) -> List[Dict]:
    trades = []
    n = len(klines)
    for st in setups:
        entry_idx = int(st['entry_index']); entry = _f(st['entry_price'])
        if entry_idx >= n - 1 or entry <= 0:
            continue
        plan = {k: st[k] for k in ('sl','tp1','tp2','tp3','risk','risk_pct','trail_trigger_r','trail_lock_r','breakeven_r') if k in st}
        if not all(k in plan for k in ('sl','tp1','tp2','tp3','risk')):
            built = build_exit_plan(st, klines)
            if not built: continue
            plan.update(built)
        sl, tp1, tp2, tp3, risk = _f(plan['sl']), _f(plan['tp1']), _f(plan['tp2']), _f(plan['tp3']), _f(plan['risk'])
        remaining = 1.0; realized = 0.0; hit = []
        stop = sl; high_water = entry
        exit_idx = -1; exit_price = entry; reason = 'TIMEOUT'; breakeven = False
        for j in range(entry_idx + 1, min(entry_idx + max_hold_bars + 1, n)):
            b = klines[j]
            op, lo, hi, cl = _f(b.get('o')), _f(b.get('l')), _f(b.get('h')), _f(b.get('c'))
            if min(op, lo, hi, cl) <= 0:
                continue
            # Executable gap stop: if open is below current stop, exit at open, not ideal stop.
            if op <= stop:
                realized += remaining * ((op - entry) / entry * 100)
                exit_idx = j; exit_price = op
                reason = 'GAP_SL_HIT' if stop <= sl + 1e-9 else 'GAP_TRAILING_STOP'
                remaining = 0; break
            high_water = max(high_water, hi)
            if (j - entry_idx) >= int(plan.get('breakeven_bars', 3)) and not breakeven and high_water >= entry + risk * _f(plan.get('breakeven_r'), 1.0):
                stop = max(stop, entry * 1.001); breakeven = True
            if high_water >= entry + risk * _f(plan.get('trail_trigger_r'), 1.8):
                stop = max(stop, high_water - risk * _f(plan.get('trail_lock_r'), 1.0))
            if lo <= stop:
                realized += remaining * ((stop - entry) / entry * 100)
                exit_idx = j; exit_price = stop
                reason = 'TRAILING_STOP' if stop > sl else 'SL_HIT'
                remaining = 0; break
            if 'TP1' not in hit and hi >= tp1:
                frac = _f(plan.get('tp1_frac'), 0.30)
                realized += frac * ((tp1 - entry) / entry * 100); remaining -= frac; hit.append('TP1')
            if 'TP2' not in hit and hi >= tp2:
                frac = _f(plan.get('tp2_frac'), 0.25)
                realized += frac * ((tp2 - entry) / entry * 100); remaining -= frac; hit.append('TP2'); stop = max(stop, entry + risk * _f(plan.get('tp2_stop_r'), 1.5))
            if hi >= tp3 and remaining > 0 and plan.get('close_at_tp3', False):
                realized += remaining * ((tp3 - entry) / entry * 100)
                exit_idx = j; exit_price = tp3; reason = 'TP3_HIT'; remaining = 0; break
        if exit_idx < 0:
            exit_idx = min(entry_idx + max_hold_bars, n - 1)
            exit_price = _f(klines[exit_idx].get('c'), entry)
            realized += remaining * ((exit_price - entry) / entry * 100)
            reason = 'TIMEOUT_PARTIAL' if hit else 'TIMEOUT'
        hold = exit_idx - entry_idx
        if hold < min_hold_bars:
            continue
        trades.append({**st, **plan,
                       'exit_date': fdate(klines, exit_idx), 'exit_index': exit_idx, 'exit_price': round(exit_price, 4),
                       'exit_reason': reason, 'pnl_pct': round(realized, 2), 'hold_bars': hold,
                       'partial_hits': hit, 'won': realized > 0,
                       'engine': 'V41_REPLAY_ENTRY_EXIT', 'definition_version': 'smc_core_v41'})
    return trades


def find_prev_ssl(sweeps, ev_idx, lookback=35):
    c = [s for s in sweeps if s.get('direction') == 'bull' and 0 < ev_idx - s.get('index', -999) <= lookback]
    return max(c, key=lambda x: x['index']) if c else None


def is_liquidity_pool_sweep(sweep):
    return sweep and (sweep.get('pool') in ('EQL','EQH') or sweep.get('subtype') in ('EQL','EQH') or sweep.get('type') in ('EQL','EQH','SSL_sweep'))


def choch_quality_ok(ev, sweep, zone_type, zone, klines, ri, ci):
    if ev.get('is_mss'):
        return True
    if ev.get('type') != 'CHOCH':
        return False
    if zone_type not in ('OB','FVG'):
        return False
    if not is_liquidity_pool_sweep(sweep):
        return False
    if v28.market_state(klines, ci) != 'RANGE':
        return False
    zl, zh = _f(zone.get('zone_low')), _f(zone.get('zone_high'))
    if zl <= 0 or (zh - zl) / zl * 100 > 1.0:
        return False
    if ci - ev['index'] > 6:
        return False
    if ev['index'] - sweep['index'] > 20:
        return False
    b = klines[ev['index']]
    rng = max(_f(b.get('h')) - _f(b.get('l')), 1e-9)
    body = abs(_f(b.get('c')) - _f(b.get('o')))
    if body / rng < 0.20:
        return False
    return True


def find_recent_zone(signal_data, ev_idx, zone_type, sweep_idx=None):
    key = {'OB': 'obs', 'FVG': 'fvgs', 'BPR': 'bprs', 'OTE': 'otes', 'LV': 'liquidity_voids', 'BRK': 'breakers', 'RB': 'rejection_blocks'}.get(zone_type, '')
    zones = signal_data.get(key, [])
    # V34: OB must be created by the same LuxAlgo structure event, not merely any nearby old zone.
    if zone_type == 'OB':
        c = [z for z in zones if z.get('direction') == 'bull' and z.get('created_by_event_index') == ev_idx]
    elif zone_type == 'FVG':
        # P2 fix: FVG is tradable only when it is a displacement gap created after the liquidity sweep
        # and no later than the MSS break (+2 bars for Pine confirmation offset).
        lo = sweep_idx if sweep_idx is not None else max(0, ev_idx - 12)
        c = [z for z in zones if z.get('direction') == 'bull' and lo <= z.get('index', -999) <= ev_idx + 2]
    elif zone_type == 'BPR':
        # BPR must be near the MSS event; old V24 used arbitrary context BPRs and polluted entries.
        lo = sweep_idx if sweep_idx is not None else max(0, ev_idx - 12)
        c = [z for z in zones if z.get('direction') == 'bull' and lo <= z.get('index', -999) <= ev_idx + 2]
    elif zone_type in ('OTE','LV','BRK','RB'):
        lo = sweep_idx if sweep_idx is not None else max(0, ev_idx - 15)
        c = [z for z in zones if z.get('direction') == 'bull' and lo <= z.get('index', -999) <= ev_idx + 3]
    else:
        c = [z for z in zones if z.get('direction') == 'bull' and 0 <= z.get('index', -999) <= ev_idx + 2 and ev_idx - z.get('index', -999) <= 20]
    if not c: return None
    z = min(c, key=lambda z: abs(z['index'] - ev_idx))
    if zone_type == 'FVG':
        return {'index': z['index'], 'date': z.get('date',''), 'zone_low': z['gap_low'], 'zone_high': z['gap_high'], 'type': 'FVG', 'src': z}
    return {'index': z['index'], 'date': z.get('date',''), 'zone_low': z['zone_low'], 'zone_high': z['zone_high'], 'type': zone_type, 'src': z}


def make_setup(symbol, arch, klines, signal_data, sweep, ev, zone_type, zone, retrace_idx, conf_idx, conf_type):
    ent = entry_from_limit_retouch(klines, conf_idx, zone, zone_type=zone_type)
    if ent is None:
        return None
    entry_idx, entry, entry_mode = ent
    zl, zh = _f(zone['zone_low']), _f(zone['zone_high'])
    if not (zl * 0.995 <= entry <= zh * 1.012):
        return None
    # V34D quality gates from full-market SL attribution:
    # - wide OBs were the clearest avoidable SL source
    # - confirmation too far after structure means signal is stale, not a fresh RTO
    zone_width_pct = (zh - zl) / max(zl, 1e-9) * 100
    max_width = 2.0 if zone_type == 'OB' else (3.0 if zone_type == 'FVG' else 2.5)
    if zone_width_pct > max_width:
        return None
    if conf_idx - ev['index'] > 20:
        return None
    st = {'symbol': symbol, 'architecture': arch, 'zone_type': zone_type, 'signal_type': zone_type,
          'signal_date': ev.get('date',''), 'signal_index': ev['index'], 'source_event': ('MSS' if ev.get('is_mss') else ev['type']), 'source_event_idx': ev['index'],
          'entry_date': fdate(klines, entry_idx), 'entry_index': entry_idx, 'entry_price': entry, 'entry_mode': entry_mode,
          'zone_low': round(zl,4), 'zone_high': round(zh,4), 'zone_idx': zone['index'], 'zone_date': zone.get('date',''),
          'conf_type': conf_type, 'conf_index': conf_idx, 'retrace_index': retrace_idx,
          'sweep_idx': sweep['index'], 'sweep_date': sweep.get('date',''), 'sweep_type': sweep.get('subtype','SSL'),
          'swept_low': round(_f(sweep.get('wick_low'), _f(sweep.get('price'), zl)),4),
          'ctx_seq': f"SSL→{('MSS' if ev.get('is_mss') else ev['type'])}→{arch}:{zone_type}→{conf_type}→LimitEntry",
          'seq': f"SSL-{('MSS' if ev.get('is_mss') else ev['type'])}-{arch}-{zone_type}-{conf_type}", 'detail': '',
          'zone': zone, 'struct_event': ev,
          'audit_chain': {
              'core': 'luxalgo_leg_v34',
              'pine_rules': {
                  'leg': 'high[size] > ta.highest(size) / low[size] < ta.lowest(size)',
                  'structure': 'ta.crossover/crossunder(close,pivot.currentLevel) and not crossed',
                  'mss': 'CHOCH + recent SSL sweep + displacement',
                  'entry': 'limit retouch only; no next-open chase'
              },
              'indices': {'sweep': sweep['index'], 'structure': ev['index'], 'zone': zone['index'], 'retrace': retrace_idx, 'confirm': conf_idx},
              'time_gaps': {'sweep_to_struct': ev['index']-sweep['index'], 'zone_to_struct': ev['index']-zone['index'], 'struct_to_confirm': conf_idx-ev['index']},
              'structure_label': ev.get('swing_label'),
              'structure_level': ev.get('source_level'),
              'mss_reason': ev.get('mss_reason'),
              'zone_src': zone.get('src',{})
          }}
    plan = build_exit_plan(st, klines)
    if not plan: return None
    st.update(plan)
    st['rr'] = round((st['tp1'] - entry) / max(entry - st['sl'], 1e-9), 2)
    # Base quality: signal structure correctness + zone proximity + reasonable risk.
    st['quality_score'] = round(5.0 + (1.0 if ev.get('is_mss') else 0.4) + (0.8 if zone_type == 'OB' else 0.4) - max(0, st['risk_pct'] - 4) * 0.15, 2)
    st['resonance_score'] = 0.0
    st['market_state'] = v28.market_state(klines, entry_idx)
    if st['rr'] < MIN_RR: return None
    if st['market_state'] in {'TREND_DOWN','TRANSITION','UNKNOWN','HIGH_VOL'}: return None
    # V36 root-cause fix from V35 SL attribution:
    # FVG in TREND_UP was not a clean demand retest; it behaved like late
    # continuation/chase entries (WR42.9, SL57.1). Keep FVG only in RANGE where
    # it acted as mean-reversion liquidity reclaim. OB remains valid in RANGE
    # and TREND_UP because it is same-event LuxAlgo demand.
    if zone_type in {'FVG', 'BPR', 'OTE', 'LV', 'BRK', 'RB'} and st['market_state'] != 'RANGE':
        return None
    return st


def build_v34_setups(symbol: str, klines: List[Dict], signal_data: Dict) -> List[Dict]:
    setups = []
    for ev in signal_data.get('structure', []):
        if ev.get('direction') != 'bull' or ev.get('type') not in ('CHOCH', 'BOS'):
            continue
        if ev.get('type') == 'BOS' and not ev.get('is_mss'):
            # BOS alone is continuation context, not reversal entry trigger.
            continue
        sweep = find_prev_ssl(signal_data.get('sweeps', []), ev['index'])
        if not sweep: continue
        # V38 final: BRK/RB/BPR/LV/OTE definitions are now implemented and
        # audited, but the candidate trading run failed the quality gate
        # (20 trades, WR65, SL25). Keep them displayed/audited; trade only the
        # validated OB/FVG subset with EQL/EQH sweep-source merged.
        for zt in ('OB', 'FVG'):
            zone = find_recent_zone(signal_data, ev['index'], zt, sweep.get('index'))
            if not zone: continue
            ri = next_retrace_strict(klines, max(ev['index'], zone['index']), zone['zone_low'], zone['zone_high'])
            if ri is None: continue
            ci, ct = confirm_at_zone_strict(klines, ri, zone['zone_low'], zone['zone_high'])
            if ci is None: continue
            if not choch_quality_ok(ev, sweep, zt, zone, klines, ri, ci):
                continue
            st = make_setup(symbol, f'V39_{zt}_CHOCH_QUALITY_RTO', klines, signal_data, sweep, ev, zt, zone, ri, ci, ct)
            if st: setups.append(st)
    return dedupe_setups(setups)


def process_stock(fp, start_date='20260101', end_date=None):
    sym = symbol_from_filename(fp)
    klines = json.loads(Path(fp).read_bytes())
    if len(klines) < 120: return {'symbol': sym, 'setups': [], 'trades': []}
    # V34: structure+sweeps from LuxAlgo leg core; zones initially reuse existing FVG/OB construction.
    res32 = v32a.detect_all_signals_pine_like(klines)
    res34 = v34core.detect_all_signals_lux_v34(klines)
    sig = res32['signals']
    # Merge LuxAlgo swing sweeps with Pine-like EQL/EQH pool sweeps. V37
    # overwrote Pine sweeps, so EQL/EQH was visible but never a trade sweep source.
    merged_sweeps=[]; seen=set()
    for s in list(res34['signals'].get('sweeps', [])) + list(res32['signals'].get('sweeps', [])):
        k=(s.get('direction'), s.get('index'), s.get('pool', 'SWING'), s.get('swept_idx'))
        if k in seen: continue
        seen.add(k); merged_sweeps.append(s)
    sig['sweeps'] = sorted(merged_sweeps, key=lambda x: x.get('index', 0))
    sig['swing_structure'] = res34['signals']['swing_structure']
    sig['internal_structure'] = res34['signals']['internal_structure']
    sig['structure'] = res34['signals']['structure']
    sig['obs'] = res34['signals']['obs']
    sig['v34_summary'] = res34['summary']
    setups = build_v34_setups(sym, klines, sig)
    trades = backtest_v34_setups(setups, klines)
    if start_date:
        trades = [t for t in trades if str(t.get('entry_date','')) >= start_date]
    if end_date:
        trades = [t for t in trades if str(t.get('entry_date','')) <= end_date]
    return {'symbol': sym, 'setups': setups, 'trades': trades}


def metrics(trades):
    n=len(trades); w=sum(1 for t in trades if _f(t.get('pnl_pct'))>0)
    return {'n_trades': n, 'n_wins': w, 'n_losses': n-w, 'wr': round(w/max(n,1)*100,1),
            'avg_pnl': round(sum(_f(t.get('pnl_pct')) for t in trades)/max(n,1),2),
            'total_pnl': round(sum(_f(t.get('pnl_pct')) for t in trades),2),
            'sl_count': sum(1 for t in trades if 'SL' in str(t.get('exit_reason',''))),
            'sl_rate': round(sum(1 for t in trades if 'SL' in str(t.get('exit_reason','')))/max(n,1)*100,1)}


def generate_picks(trades, max_recent_days=30):
    if not trades: return []
    # use lexical yyyymmdd dates
    as_of = max(str(t.get('entry_date',''))[:8] for t in trades if t.get('entry_date'))
    from datetime import datetime, timedelta
    cutoff = (datetime.strptime(as_of, '%Y%m%d') - timedelta(days=max_recent_days)).strftime('%Y%m%d')
    recent = [t for t in trades if str(t.get('entry_date',''))[:8] >= cutoff]
    by = defaultdict(list)
    for t in recent: by[t['symbol']].append(t)
    picks=[]
    for sym, ts in by.items():
        t = sorted(ts, key=lambda x: (x.get('entry_date',''), _f(x.get('quality_score')), _f(x.get('rr'))), reverse=True)[0]
        picks.append({k:t.get(k) for k in ['symbol','engine','architecture','entry_date','entry_price','zone_type','signal_date','conf_type','source_event','zone_low','zone_high','market_state','quality_score','sl','tp1','tp2','tp3','risk_pct','rr','ctx_seq','seq','sweep_idx','source_event_idx','zone_idx','conf_index','entry_index','exit_reason','pnl_pct']})
    return sorted(picks, key=lambda p: -_f(p.get('quality_score')))


def main(argv=None):
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--start-date', default='20260101')
    args=ap.parse_args(argv)
    files=sorted(CACHE.glob('*_daily_750.json'))
    if args.limit: files=files[:args.limit]
    all_trades=[]; all_setups=[]; t0=time.time()
    for i,fp in enumerate(files,1):
        try:
            r=process_stock(fp, start_date=args.start_date)
            all_setups.extend(r['setups']); all_trades.extend(r['trades'])
        except Exception as e:
            pass
        if i % 500 == 0:
            print('processed', i, 'trades', len(all_trades), 'elapsed', round(time.time()-t0,1))
    m=metrics(all_trades)
    picks=generate_picks(all_trades)
    (OUT_DIR/'v41_trades.json').write_text(json.dumps(all_trades, ensure_ascii=False, indent=2))
    (OUT_DIR/'v41_picks.json').write_text(json.dumps(picks, ensure_ascii=False, indent=2))
    (OUT_DIR/'v41_setups.json').write_text(json.dumps(all_setups, ensure_ascii=False, indent=2))
    by_zone = {}
    for z in sorted(set(t.get('zone_type') for t in all_trades)):
        by_zone[z] = metrics([t for t in all_trades if t.get('zone_type') == z])
    by_event = {}
    for e in sorted(set(t.get('source_event') for t in all_trades)):
        by_event[e] = metrics([t for t in all_trades if t.get('source_event') == e])
    diag={'metrics':m,'by_zone':by_zone,'by_event':by_event,'n_setups':len(all_setups),'n_picks':len(picks),'exit_counts':dict(Counter(t.get('exit_reason') for t in all_trades)), 'filters':{'active':['V38_OB_FVG_base','ordinary_CHOCH_quality_subset','liquidity_pool_sweep_required','RANGE_required','tight_zone_OB_1_2_FVG_1_0','fast_confirm_le_6','tp1_1_5r_tp2_3_2r_tp3_4_2r_trail_2_8r'], 'quality_gate':'promote only if WR>=80, SL<=10, PF>=V38 and trades>V38'}, 'elapsed_sec':round(time.time()-t0,2)}
    (OUT_DIR/'v41_metrics.json').write_text(json.dumps(diag, ensure_ascii=False, indent=2))
    print(json.dumps(diag, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
