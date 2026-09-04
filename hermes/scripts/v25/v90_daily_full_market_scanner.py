#!/usr/bin/env python3
"""V90 daily full-market scanner for V88 production contract.

Purpose:
- Generate current/recent active picks from cached daily A-share klines.
- Reuse the V85/V86 signal layer and V88 production contract fields.
- Do NOT inherit V86 future-bar liquidity_target semantics.
- Emit frontend-ready pick fields: pick_date, join_date, zone, cost_line, volatility.

This script is scanner-only. It does not replace the V88 backtest baseline.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Tuple

from v81_full_market_scan import ENV_PATH, KLINE_DIR, load_json, normalize_env, symbol_from_path
from v81_contextual_smc_generator import locate_entry
from v122_shadow_parallel_poi_generator_audit import fvg_near_event, enrich_poi_geometry, overlap_poi
from v85_mixed_accumulation_generator import generate_v85_candidates, zone_width_pct

OUT = Path('/root/.hermes/smc_opt_v90_daily_full_market_scanner')
OUT.mkdir(parents=True, exist_ok=True)

ENGINE = 'V90_DAILY_SCANNER_V88_CONTRACT'
SIGNAL_LAYER = 'V85_V86_SIGNAL_LAYER'
CONTRACT_SOURCE = 'V88_PRODUCTION_CONTRACT_DAILY_SCANNER_FIXED_KNOWN_TARGET'
RECENT_BARS = 45
MAX_ACTIVE_BARS = 3


def num(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == '':
            return default
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def date_key(v: Any) -> str:
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def bar_date(b: Dict[str, Any]) -> str:
    return date_key(b.get('t') or b.get('date'))


def v(b: Dict[str, Any], key: str) -> float:
    return num(b.get(key))


def atr(ks: List[Dict[str, Any]], idx: int, n: int = 14) -> float:
    start = max(1, idx - n + 1)
    trs = []
    for i in range(start, min(idx + 1, len(ks))):
        hi, lo, prev = v(ks[i], 'h'), v(ks[i], 'l'), v(ks[i - 1], 'c')
        trs.append(max(hi - lo, abs(hi - prev), abs(lo - prev)))
    return sum(trs) / len(trs) if trs else 0.0


def infer_family(row: Dict[str, Any]) -> str:
    text = '|'.join(str(row.get(k) or '') for k in ('family', 'story', 'source_event', 'event_type', 'trend_regime', 'v85_path'))
    if 'REVERSAL' in text or 'SSL_SWEEP_CHOCH' in text:
        return 'REVERSAL'
    if 'CONTINUATION' in text or 'BOS_CONTINUATION' in text:
        return 'CONTINUATION'
    return str(row.get('family') or '')


def fvg_source_label(row: Dict[str, Any]) -> str:
    full_retrace = num(row.get('retrace_pct')) >= 95.0
    strong_mid = num(row.get('fvg_mid_body_atr')) >= 0.65
    demand_retest = (not full_retrace) and num(row.get('fvg_mid_body_atr')) >= 0.35
    if demand_retest:
        return 'TRUE_DEMAND_RETEST_CANDIDATE'
    if full_retrace and strong_mid:
        return 'STRONG_IMBALANCE_FULL_RETRACE'
    if full_retrace and not strong_mid and row.get('family') == 'CONTINUATION':
        return 'WEAK_CONTINUATION_FULL_RETRACE_FVG'
    return 'WEAK_DISPLACEMENT_OTHER'


def v116_gate_reason(row: Dict[str, Any]) -> str:
    if (
        row.get('family') == 'CONTINUATION'
        and num(row.get('retrace_pct')) >= 95.0
        and num(row.get('fvg_mid_body_atr')) < 0.65
    ):
        return 'WEAK_CONTINUATION_FULL_RETRACE_FVG_SHADOW_DOWNGRADE'
    return ''


def source_quality_fields(c: Dict[str, Any], ks: List[Dict[str, Any]]) -> Dict[str, Any]:
    zl, zh = num(c.get('zone_low')), num(c.get('zone_high'))
    touch_idx = int(num(c.get('touch_idx'), -1))
    zone_idx = int(num(c.get('zone_idx'), -1))
    touch_low = v(ks[touch_idx], 'l') if 0 <= touch_idx < len(ks) else 0.0
    source_atr = atr(ks, min(max(zone_idx + 1, 1), len(ks) - 1)) if ks and zone_idx >= 0 else 0.0
    mid = ks[zone_idx] if 0 <= zone_idx < len(ks) else {}
    row = {
        'family': infer_family(c),
        'retrace_pct': round(max(0.0, min(100.0, (zh - touch_low) / max(zh - zl, 1e-9) * 100)), 2) if zl and zh and touch_low else 0.0,
        'fvg_mid_body_atr': round((v(mid, 'c') - v(mid, 'o')) / source_atr, 4) if source_atr else 0.0,
        'fvg_mid_range_atr': round((v(mid, 'h') - v(mid, 'l')) / source_atr, 4) if source_atr else 0.0,
        'fvg_mid_bull': v(mid, 'c') > v(mid, 'o') if mid else False,
        'v116_shadow_mode': True,
    }
    row['source_label'] = fvg_source_label(row)
    row['v116_gate_reason'] = v116_gate_reason(row)
    row['v116_shadow_action'] = 'DOWNGRADE_ONLY' if row['v116_gate_reason'] else 'KEEP'
    return row



def v127_reclaim_geometry_fields(poi: Dict[str, Any], entry: Dict[str, Any], ks: List[Dict[str, Any]]) -> Dict[str, Any]:
    zl, zh = num(poi.get('zone_low')), num(poi.get('zone_high'))
    ti = int(num(entry.get('touch_idx'), -1))
    ri = int(num(entry.get('reclaim_idx'), -1))
    ei = int(num(entry.get('entry_idx'), -1))
    width = max(zh - zl, 1e-9)
    out: Dict[str, Any] = {}
    if 0 <= ti < len(ks):
        touch_low = v(ks[ti], 'l')
        out['v127_shadow_touch_depth_zone_pct'] = round(max(0.0, zh - touch_low) / width * 100, 4)
    else:
        out['v127_shadow_touch_depth_zone_pct'] = 0.0
    if 0 <= ri < len(ks):
        rb = ks[ri]
        rng = max(v(rb, 'h') - v(rb, 'l'), 1e-9)
        out['v127_shadow_reclaim_close'] = round(v(rb, 'c'), 6)
        out['v127_shadow_reclaim_close_above_zone_pct'] = round((v(rb, 'c') / zh - 1) * 100, 4) if zh else 0.0
        out['v127_shadow_reclaim_close_pos'] = round((v(rb, 'c') - v(rb, 'l')) / rng, 4)
    else:
        out['v127_shadow_reclaim_close'] = ''
        out['v127_shadow_reclaim_close_above_zone_pct'] = 0.0
        out['v127_shadow_reclaim_close_pos'] = 0.0
    out['v127_shadow_touch_to_reclaim_bars'] = max(0, ri - ti) if ti >= 0 and ri >= 0 else 0
    out['v127_shadow_entry_chase_above_zone_pct'] = round((num(entry.get('entry_price')) / zh - 1) * 100, 4) if zh else 0.0
    out['v127_shadow_bars_since_entry'] = len(ks) - 1 - ei if ei >= 0 else 9999
    return out



def v127_true_fvg_shadow_fields(c: Dict[str, Any], ks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Attach true FVG_Demand shadow metadata without changing scanner identity."""
    empty = {
        'v127_shadow_mode': True,
        'v127_shadow_poi_source': '',
        'v127_shadow_combo_family': '',
        'v127_shadow_contract_pass': False,
        'v127_shadow_no_ob_relabel': True,
    }
    event_idx = int(num(c.get('event_idx'), -1))
    if event_idx < 0:
        return empty
    env = {'market_state': c.get('market_state')}
    candidates: List[Dict[str, Any]] = []
    for raw in fvg_near_event(ks, c):
        poi = enrich_poi_geometry(ks, c, raw, env)
        if not poi.get('valid'):
            continue
        entry = locate_entry(ks, poi, event_idx, max_wait=8)
        if not entry.get('entry_valid'):
            continue
        zl, zh = num(poi.get('zone_low')), num(poi.get('zone_high'))
        entry_price = num(entry.get('entry_price'))
        risk = (entry_price / zl - 1) * 100 if entry_price and zl else 0.0
        width_pct = (zh / zl - 1) * 100 if zl and zh else 0.0
        row = {
            **empty,
            'v127_shadow_poi_source': 'FVG_Demand',
            'v127_shadow_combo_family': 'CONTINUATION' if c.get('event_type') == 'BOS_CONTINUATION' else 'REVERSAL',
            'v127_shadow_source_mid_body_atr': raw.get('source_mid_body_atr'),
            'v127_shadow_source_gap_atr': raw.get('source_gap_atr'),
            'v127_shadow_risk_pct': round(risk, 4),
            'v127_shadow_v85_zone_width_pct': round(width_pct, 4),
            'v127_shadow_market_state': c.get('market_state'),
            'v127_shadow_zone_low': round(zl, 6),
            'v127_shadow_zone_high': round(zh, 6),
            'v127_shadow_touch_idx': int(num(entry.get('touch_idx'), -1)),
            'v127_shadow_reclaim_idx': int(num(entry.get('reclaim_idx'), -1)),
            'v127_shadow_entry_idx': int(num(entry.get('entry_idx'), -1)),
            'v127_shadow_entry_date': date_key(entry.get('entry_date')),
            'v127_shadow_entry_price': round(entry_price, 6),
        }
        row.update(v127_reclaim_geometry_fields(poi, entry, ks))
        row['v127_shadow_contract_pass'] = (
            row['v127_shadow_combo_family'] == 'REVERSAL'
            and num(row.get('v127_shadow_source_mid_body_atr')) >= 0.65
            and num(row.get('v127_shadow_source_gap_atr')) >= 0.8
            and 1.0 <= num(row.get('v127_shadow_risk_pct')) <= 3.0
            and 1.2 <= num(row.get('v127_shadow_v85_zone_width_pct')) <= 2.2
            and num(row.get('v127_shadow_reclaim_close_above_zone_pct')) >= 0.5
            and 1 <= num(row.get('v127_shadow_touch_to_reclaim_bars')) <= 3
            and row.get('v127_shadow_market_state') in {'MIXED', 'BEAR_RISK'}
        )
        candidates.append(row)
    if not candidates:
        return empty
    return min(candidates, key=lambda r: (num(r.get('v127_shadow_bars_since_entry'), 9999), num(r.get('v127_shadow_risk_pct'), 999), -num(r.get('v127_shadow_source_gap_atr'))))


def v125_fvg_contract(row: Dict[str, Any]) -> bool:
    return (
        row.get('combo_family') == 'REVERSAL'
        and row.get('poi_source') == 'FVG_Demand'
        and num(row.get('source_mid_body_atr')) >= 0.65
        and num(row.get('source_gap_atr')) >= 0.8
        and 1.0 <= num(row.get('risk_pct')) <= 3.0
        and 1.2 <= num(row.get('v85_zone_width_pct')) <= 2.2
        and num(row.get('reclaim_close_above_zone_pct')) >= 0.5
        and 1 <= num(row.get('touch_to_reclaim_bars')) <= 3
        and row.get('market_state') in {'MIXED', 'BEAR_RISK'}
    )


def v128_row_from_poi(c: Dict[str, Any], poi: Dict[str, Any], entry: Dict[str, Any], ks: List[Dict[str, Any]], source: str) -> Dict[str, Any]:
    zl, zh = num(poi.get('zone_low')), num(poi.get('zone_high'))
    entry_price = num(entry.get('entry_price'))
    risk = (entry_price / zl - 1) * 100 if entry_price and zl else 0.0
    width_pct = (zh / zl - 1) * 100 if zl and zh else 0.0
    row = {
        'v128_shadow_mode': True,
        'symbol': c.get('symbol'),
        'poi_source': source,
        'combo_family': 'CONTINUATION' if c.get('event_type') == 'BOS_CONTINUATION' else 'REVERSAL',
        'event_type': c.get('event_type'),
        'event_idx': int(num(c.get('event_idx'), -1)),
        'event_date': date_key(c.get('event_date')),
        'pick_date': date_key(c.get('event_date')),
        'entry_date': date_key(entry.get('entry_date')),
        'join_date': date_key(entry.get('entry_date')),
        'zone_date': date_key(poi.get('zone_date')),
        'zone_low': round(zl, 6),
        'zone_high': round(zh, 6),
        'entry_price': round(entry_price, 6),
        'risk_pct': round(risk, 4),
        'v85_zone_width_pct': round(width_pct, 4),
        'source_mid_body_atr': poi.get('source_mid_body_atr', ''),
        'source_gap_atr': poi.get('source_gap_atr', ''),
        'market_state': c.get('market_state'),
        'touch_idx': int(num(entry.get('touch_idx'), -1)),
        'reclaim_idx': int(num(entry.get('reclaim_idx'), -1)),
        'entry_idx': int(num(entry.get('entry_idx'), -1)),
        'bars_since_entry': len(ks) - 1 - int(num(entry.get('entry_idx'), -1)),
        'ob_fvg_overlap_pct': poi.get('ob_fvg_overlap_pct', ''),
        'source_is_independent_parallel_candidate': True,
    }
    row.update({k.replace('v127_shadow_', ''): v for k, v in v127_reclaim_geometry_fields(poi, entry, ks).items()})
    row['v125_contract_shadow_pass'] = v125_fvg_contract(row)
    return row


def v128_parallel_shadow_candidates(c: Dict[str, Any], ks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Emit standalone shadow candidates per POI source; never changes production rows."""
    event_idx = int(num(c.get('event_idx'), -1))
    if event_idx < 0:
        return []
    rows: List[Dict[str, Any]] = []
    ob = {
        'valid': True,
        'poi_type': 'DEMAND_OB',
        'zone_idx': c.get('zone_idx'),
        'zone_date': c.get('zone_date'),
        'zone_low': c.get('zone_low'),
        'zone_high': c.get('zone_high'),
    }
    ob_entry = {
        'entry_valid': True,
        'touch_idx': c.get('touch_idx'),
        'reclaim_idx': c.get('reclaim_idx'),
        'entry_idx': c.get('entry_idx'),
        'entry_date': c.get('entry_date'),
        'entry_price': c.get('entry_price'),
    }
    rows.append(v128_row_from_poi(c, ob, ob_entry, ks, 'DEMAND_OB'))
    env = {'market_state': c.get('market_state')}
    fvgs = [enrich_poi_geometry(ks, c, raw, env) for raw in fvg_near_event(ks, c)]
    for fvg in [x for x in fvgs if x.get('valid')][:2]:
        entry = locate_entry(ks, fvg, event_idx, max_wait=8)
        if entry.get('entry_valid'):
            rows.append(v128_row_from_poi(c, fvg, entry, ks, 'FVG_Demand'))
        combo = overlap_poi(ob, fvg)
        if combo:
            combo = enrich_poi_geometry(ks, c, combo, env)
            entry2 = locate_entry(ks, combo, event_idx, max_wait=8)
            if entry2.get('entry_valid'):
                rows.append(v128_row_from_poi(c, combo, entry2, ks, 'OB+FVG'))
    return rows


def dedupe_v128(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for r in rows:
        key = (str(r.get('symbol')), date_key(r.get('entry_date')), str(r.get('poi_source')))
        score = (num(r.get('bars_since_entry'), 9999), num(r.get('risk_pct'), 999), num(r.get('v85_zone_width_pct'), 999), date_key(r.get('event_date')))
        if key not in best or score < best[key]['_v128_dedupe_score']:
            nr = dict(r)
            nr['_v128_dedupe_score'] = score
            best[key] = nr
    return list(best.values())



def known_bsl_target(ks: List[Dict[str, Any]], entry_idx: int, entry_price: float, lookback: int = 60) -> Dict[str, Any]:
    """Find a pre-entry buy-side liquidity target: nearest prior swing/high above entry.

    Only bars strictly before entry_idx are inspected, so the target is known before
    trade entry. If no prior high is above entry, fall back to fixed 1.5R semantics
    later in contract construction.
    """
    start = max(0, entry_idx - lookback)
    prior = ks[start:entry_idx]
    highs: List[Tuple[int, float, str, str]] = []
    for local_i, b in enumerate(prior, start):
        h = v(b, 'h')
        if h <= entry_price:
            continue
        # Swing-high preference, but keep normal prior highs as fallback.
        left = ks[max(0, local_i - 2):local_i]
        right = ks[local_i + 1:min(entry_idx, local_i + 3)]
        is_swing = bool(left and right and h >= max(v(x, 'h') for x in left) and h >= max(v(x, 'h') for x in right))
        highs.append((local_i, h, bar_date(b), 'PRIOR_SWING_HIGH_BSL' if is_swing else 'PRIOR_HIGH_BSL'))
    if not highs:
        return {'known_bsl_target': 0.0, 'known_bsl_idx': -1, 'known_bsl_date': '', 'known_bsl_type': 'NO_PRIOR_BSL_ABOVE_ENTRY'}
    # Nearest reachable liquidity above entry, not the highest far-away target.
    idx, target, d, typ = min(highs, key=lambda x: (x[1] - entry_price, entry_idx - x[0]))
    return {'known_bsl_target': round(target, 4), 'known_bsl_idx': idx, 'known_bsl_date': d, 'known_bsl_type': typ}


def passes_v86_gate(row: Dict[str, Any]) -> bool:
    risk = num(row.get('risk_pct'), 0.0)
    if risk <= 0:
        entry = num(row.get('entry_price'))
        zl = num(row.get('zone_low'))
        risk = (entry / zl - 1) * 100 if entry and zl else 999.0
    return (
        1.0 < num(row.get('v85_zone_width_pct'), 999.0) <= 1.6
        and 1.0 < risk <= 1.5
        and num(row.get('hold_bars'), 0.0) <= 2
        and row.get('v83_takeover_type') == 'HOLD_ABOVE_POI'
        and str(row.get('entry_date')) != str(row.get('exit_date'))
    )


def recovery_substate(row: Dict[str, Any], ks: List[Dict[str, Any]]) -> str:
    if row.get('market_state') != 'RECOVERY':
        return str(row.get('market_state') or '')
    entry_idx = int(num(row.get('entry_idx'), -1))
    if entry_idx < 5 or entry_idx >= len(ks):
        return 'RECOVERY_UNKNOWN'
    win = ks[max(0, entry_idx - 8):entry_idx + 1]
    closes = [v(b, 'c') for b in win]
    lows = [v(b, 'l') for b in win]
    highs = [v(b, 'h') for b in win]
    entry = num(row.get('entry_price'))
    zh = num(row.get('zone_high'))
    reclaim_idx = int(num(row.get('reclaim_idx'), -1))
    touch_idx = int(num(row.get('touch_idx'), -1))
    reclaim_lag = reclaim_idx - touch_idx if reclaim_idx >= 0 and touch_idx >= 0 else 999
    if closes[-1] > closes[0] and lows[-1] >= min(lows[:-1]) and entry >= zh and reclaim_lag <= 2:
        return 'RECOVERY_CONFIRMED_FAST_RECLAIM'
    if closes[-1] > closes[0] and lows[-1] >= min(lows[:-1]):
        return 'RECOVERY_STABLE_HIGHER_LOW'
    if lows[-1] < min(lows[:-1]) or highs[-1] < max(highs[:-1]) * 0.98:
        return 'RECOVERY_WEAK_LOWER_LOW_OR_FAILED_HIGH'
    return 'RECOVERY_TRANSITION_UNCONFIRMED'


def v88_contract_from_candidate(c: Dict[str, Any], ks: List[Dict[str, Any]]) -> Dict[str, Any]:
    entry = num(c.get('entry_price'))
    zl = num(c.get('zone_low'))
    zh = num(c.get('zone_high'))
    width = zone_width_pct(c)
    risk_pct = (entry / zl - 1) * 100 if entry and zl else num(c.get('risk_pct'))
    # V88 production contract approximation for scanner rows: hybrid tight SL + fixed RR ladder.
    sl_pct = max(1.0, min(2.5, risk_pct + 0.5))
    sl = entry * (1 - sl_pct / 100) if entry else 0.0
    risk_abs = max(entry - sl, 0.000001)
    bsl = known_bsl_target(ks, int(num(c.get('entry_idx'), -1)), entry)
    bsl_target = num(bsl.get('known_bsl_target'))
    tp1_rr = 1.5
    if bsl_target and bsl_target > entry:
        bsl_rr = (bsl_target - entry) / risk_abs
        tp1_rr = max(1.5, min(3.0, bsl_rr))
    tp1 = entry + risk_abs * tp1_rr
    tp2 = entry + risk_abs * max(2.0, tp1_rr * 1.4)
    tp3 = entry + risk_abs * max(3.0, tp1_rr * 2.0)
    pick_date = date_key(c.get('pick_date') or c.get('select_date') or c.get('event_date'))
    join_date = date_key(c.get('join_date') or c.get('entry_date'))
    substate = recovery_substate(c, ks)
    source_fields = source_quality_fields(c, ks)
    v127_shadow_fields = v127_true_fvg_shadow_fields(c, ks)
    row = dict(c)
    row.update(bsl)
    row.update(source_fields)
    row.update(v127_shadow_fields)
    row.update({
        'engine': ENGINE,
        'signal_engine': SIGNAL_LAYER,
        'contract_source': CONTRACT_SOURCE,
        'v90_scanner': True,
        'v90_recovery_substate': substate,
        'v90_target_semantics': 'PRE_ENTRY_KNOWN_BSL_OR_FIXED_RR_NO_FUTURE_LIQUIDITY_TARGET',
        'liquidity_target_original_future_v86': c.get('liquidity_target'),
        'liquidity_target': round(bsl_target, 4) if bsl_target else '',
        'entry_mode': 'zone_limit_daily_scanner',
        'sl_mode': 'hybrid_tight_v88_scanner',
        'tp_mode': 'known_bsl_or_fixed_rr_ladder',
        'pick_date': pick_date,
        'select_date': pick_date,
        'join_date': join_date,
        'price': round(entry, 4),
        'entry_price': round(entry, 4),
        'sl': round(sl, 4),
        'sl_price': round(sl, 4),
        'tp1': round(tp1, 4),
        'tp2': round(tp2, 4),
        'tp3': round(tp3, 4),
        'tp': round(tp1, 4),
        'tp1_price': round(tp1, 4),
        'rr': round((tp1 - entry) / risk_abs, 4) if risk_abs else 0,
        'risk_pct': round(sl_pct, 4),
        'risk_pct_signal': round(risk_pct, 4),
        'zone_type': c.get('zone_type') or c.get('poi_type') or 'DEMAND_OB',
        'signal_type': c.get('signal_type') or c.get('event_type') or c.get('poi_type') or 'DEMAND_OB',
        'zone_low': round(zl, 4),
        'zone_high': round(zh, 4),
        'smart_money_cost': round(num(c.get('smart_money_cost')) or (zl + zh) / 2 or entry, 4),
        'cost_line': round(num(c.get('smart_money_cost')) or (zl + zh) / 2 or entry, 4),
        'volatility_pct': round(num(c.get('volatility_pct')) or width or risk_pct, 4),
        'vol_class': substate or c.get('market_state') or '-',
        'volatility': round(num(c.get('volatility_pct')) or width or risk_pct, 4),
        'zone': f"{round(zl, 4):.4f}~{round(zh, 4):.4f}",
        'pickDate': pick_date,
        'joinDate': join_date,
        'selectDate': pick_date,
        '选股日期': pick_date,
        '加入日期': join_date,
        'pick_scope': 'ACTIVE_CANDIDATE',
        'is_active_pick': True,
        'setup_status': 'ACTIVE_CANDIDATE',
        'state': 'ACTIVE_CANDIDATE',
        'sample_class': 'DAILY_SCANNER_CANDIDATE',
        'planned_exit_signal': 'V90_SCANNER_PLAN_NOT_BACKTEST_EXIT',
        'planned_exit_legs': [
            {'name': 'TP1_KNOWN_BSL_OR_1_5R', 'price': round(tp1, 4), 'weight': 0.35},
            {'name': 'TP2_EXTENSION', 'price': round(tp2, 4), 'weight': 0.35},
            {'name': 'TP3_RUNNER', 'price': round(tp3, 4), 'weight': 0.30},
        ],
    })
    return row


def field_audit(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    required = ['engine','pick_date','join_date','zone_type','zone_low','zone_high','zone','cost_line','volatility_pct','volatility','entry_price','sl','tp1','tp2','tp3','rr','v90_target_semantics','family','retrace_pct','fvg_mid_body_atr','source_label','v116_shadow_action']
    present_only = {'v116_gate_reason'}
    numeric_positive = {'zone_low','zone_high','cost_line','entry_price','sl','tp1','tp2','tp3','rr','volatility_pct','volatility'}
    out = {
        k: sum(1 for r in rows if r.get(k) in (None, '') or (k in numeric_positive and num(r.get(k)) <= 0))
        for k in required
    }
    out.update({k: sum(1 for r in rows if k not in r or r.get(k) is None) for k in present_only})
    return out



def v127_shadow_audit(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    shadow = [r for r in rows if r.get('v127_shadow_poi_source') == 'FVG_Demand']
    contract = [r for r in shadow if r.get('v127_shadow_contract_pass')]
    required = [
        'v127_shadow_poi_source','v127_shadow_combo_family','v127_shadow_source_mid_body_atr','v127_shadow_source_gap_atr',
        'v127_shadow_risk_pct','v127_shadow_v85_zone_width_pct','v127_shadow_reclaim_close_above_zone_pct',
        'v127_shadow_touch_to_reclaim_bars','v127_shadow_market_state','v127_shadow_zone_low','v127_shadow_zone_high',
        'v127_shadow_touch_idx','v127_shadow_reclaim_idx','v127_shadow_entry_idx',
    ]
    def missing(rs: List[Dict[str, Any]]) -> Dict[str, int]:
        return {k: sum(1 for r in rs if r.get(k) in (None, '')) for k in required}
    def window(n: int) -> int:
        return sum(1 for r in contract if 0 <= num(r.get('v127_shadow_bars_since_entry'), 9999) <= n)
    return {
        'shadow_rows_with_true_fvg': len(shadow),
        'contract_pass_rows': len(contract),
        'contract_recent_10_bars': window(10),
        'contract_recent_20_bars': window(20),
        'contract_recent_45_bars': window(45),
        'field_missing_on_true_fvg_rows': missing(shadow),
        'field_missing_on_contract_rows': missing(contract),
        'non_fvg_shadow_source_count': sum(1 for r in rows if r.get('v127_shadow_poi_source') not in ('', 'FVG_Demand')),
        'ob_relabel_violations': sum(1 for r in shadow if r.get('v127_shadow_no_ob_relabel') is not True),
        't1_entry_guard_violations': sum(1 for r in shadow if date_key(r.get('pick_date')) == date_key(r.get('v127_shadow_entry_date'))),
    }



def bucket(rows: Iterable[Dict[str, Any]], key: Callable[[Dict[str, Any]], Any]) -> Dict[str, Dict[str, Any]]:
    g: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        g[str(key(r))].append(r)
    return {k: {'n': len(v), 'known_bsl_rate': round(sum(1 for r in v if num(r.get('known_bsl_target')) > 0) / len(v) * 100, 2) if v else 0} for k, v in sorted(g.items())}


def main() -> None:
    env_raw = load_json(ENV_PATH)
    env_by_date = {str(k)[:8]: normalize_env(v) for k, v in env_raw.items()}
    scanned = 0
    all_contracts: List[Dict[str, Any]] = []
    v128_parallel_raw: List[Dict[str, Any]] = []
    latest_date = ''
    latest_candidates_by_symbol: Dict[str, Dict[str, Any]] = {}
    reject_counts: Counter[str] = Counter()

    for path in sorted(KLINE_DIR.glob('*_daily_750.json')):
        ks = load_json(path)
        if len(ks) < 80:
            continue
        scanned += 1
        sym = symbol_from_path(path)
        latest_date = max(latest_date, bar_date(ks[-1]))
        try:
            cands = generate_v85_candidates(sym, ks, env_by_date)
        except Exception as exc:
            reject_counts[f'GENERATOR_ERROR:{type(exc).__name__}'] += 1
            continue
        for c in cands:
            # Historical V86 production gate is adapted for active picks. hold_bars
            # is absent before simulation, so entry/takeover proximity is checked
            # by entry_idx-v83_takeover_idx instead.
            c = dict(c)
            c['v85_zone_width_pct'] = round(zone_width_pct(c), 4)
            v128_parallel_raw.extend(v128_parallel_shadow_candidates(c, ks))
            entry_idx = int(num(c.get('entry_idx'), -1))
            takeover_idx = int(num(c.get('v83_takeover_idx'), c.get('reclaim_idx') or -1))
            c['hold_bars'] = max(0, entry_idx - takeover_idx) if entry_idx >= 0 and takeover_idx >= 0 else 999
            if not passes_v86_gate({**c, 'exit_date': '20991231'}):
                reject_counts['V86_GATE_FAIL'] += 1
                continue
            row = v88_contract_from_candidate(c, ks)
            if row.get('market_state') == 'RECOVERY' and row.get('v90_recovery_substate') not in {'RECOVERY_CONFIRMED_FAST_RECLAIM', 'RECOVERY_STABLE_HIGHER_LOW'}:
                reject_counts['RECOVERY_WEAK_SUBSTATE_FAIL'] += 1
                continue
            all_contracts.append(row)
            old = latest_candidates_by_symbol.get(sym)
            if old is None or date_key(row.get('entry_date')) > date_key(old.get('entry_date')):
                latest_candidates_by_symbol[sym] = row

    if latest_date:
        latest_idx_by_symbol: Dict[str, int] = {}
        recent_contracts: List[Dict[str, Any]] = []
        for r in latest_candidates_by_symbol.values():
            # Approximate recency by entry_idx distance to the end of its 750-bar cache.
            p = KLINE_DIR / f"{str(r.get('symbol')).replace('.', '_')}_daily_750.json"
            ks = load_json(p) if p.exists() else []
            last_idx = len(ks) - 1
            dist = last_idx - int(num(r.get('entry_idx'), -9999))
            r['bars_since_entry'] = dist
            r['market_latest_date'] = latest_date
            if 0 <= dist <= RECENT_BARS:
                if dist <= MAX_ACTIVE_BARS:
                    r['pick_scope'] = 'ACTIVE_CANDIDATE'
                    r['is_active_pick'] = True
                    r['setup_status'] = 'ACTIVE_CANDIDATE'
                    r['state'] = 'ACTIVE_CANDIDATE'
                else:
                    r['pick_scope'] = 'WATCH_ONLY'
                    r['is_active_pick'] = False
                    r['setup_status'] = 'WATCH_ONLY_EXPIRED_ENTRY_WINDOW'
                    r['state'] = 'WATCH_ONLY'
                    r['watch_layer'] = 'RECENT_EXPIRED_ENTRY_WINDOW'
                    r['watch_reason'] = f'BARS_SINCE_ENTRY_{dist}_GT_{MAX_ACTIVE_BARS}'
                    r['reject_reason'] = r['watch_reason']
                recent_contracts.append(r)
    else:
        recent_contracts = []

    recent_contracts.sort(key=lambda r: (int(num(r.get('bars_since_entry'), 999)), date_key(r.get('entry_date'))), reverse=False)
    all_contracts.sort(key=lambda r: date_key(r.get('entry_date')), reverse=True)
    v128_parallel = dedupe_v128(v128_parallel_raw)
    v128_recent = [r for r in v128_parallel if 0 <= num(r.get('bars_since_entry'), 9999) <= RECENT_BARS]
    v128_parallel.sort(key=lambda r: date_key(r.get('entry_date')), reverse=True)
    v128_recent.sort(key=lambda r: (int(num(r.get('bars_since_entry'), 999)), date_key(r.get('entry_date'))))
    report = {
        'engine': ENGINE,
        'run_at': datetime.now().isoformat(timespec='seconds'),
        'scanned_symbols': scanned,
        'latest_market_date': latest_date,
        'all_contract_candidates': len(all_contracts),
        'recent_active_candidates': len(recent_contracts),
        'active_entry_window_candidates': sum(1 for r in recent_contracts if r.get('is_active_pick')),
        'watch_only_expired_entry_window': sum(1 for r in recent_contracts if r.get('pick_scope') == 'WATCH_ONLY'),
        'recent_window_bars': RECENT_BARS,
        'max_active_bars': MAX_ACTIVE_BARS,
        'target_semantics': 'known BSL/prior high strictly before entry; original future liquidity_target preserved only as liquidity_target_original_future_v86',
        'field_audit_recent': field_audit(recent_contracts),
        'field_audit_all': field_audit(all_contracts),
        'v127_shadow_audit_all': v127_shadow_audit(all_contracts),
        'v127_shadow_audit_recent': v127_shadow_audit(recent_contracts),
        'v128_parallel_shadow': {
            'raw_rows_before_dedupe': len(v128_parallel_raw),
            'dedupe_key': 'symbol+entry_date+poi_source',
            'dedup_rows': len(v128_parallel),
            'recent45_rows': len(v128_recent),
            'by_source_all': dict(Counter(str(r.get('poi_source')) for r in v128_parallel)),
            'by_source_recent45': dict(Counter(str(r.get('poi_source')) for r in v128_recent)),
            'v125_contract_pass_all': sum(1 for r in v128_parallel if r.get('v125_contract_shadow_pass')),
            'v125_contract_pass_recent45': sum(1 for r in v128_recent if r.get('v125_contract_shadow_pass')),
            't1_entry_guard_violations': sum(1 for r in v128_parallel if date_key(r.get('pick_date')) == date_key(r.get('entry_date'))),
            'production_identity_unchanged': True,
        },
        't1_entry_guard_violations_recent': sum(1 for r in recent_contracts if date_key(r.get('pick_date')) == date_key(r.get('join_date'))),
        'by_market_state_recent': bucket(recent_contracts, lambda r: r.get('market_state')),
        'by_recovery_substate_recent': bucket(recent_contracts, lambda r: r.get('v90_recovery_substate')),
        'known_bsl_rate_recent': round(sum(1 for r in recent_contracts if num(r.get('known_bsl_target')) > 0) / len(recent_contracts) * 100, 2) if recent_contracts else 0,
        'reject_counts': dict(reject_counts),
    }
    (OUT / 'v90_all_contract_candidates.json').write_text(json.dumps(all_contracts, ensure_ascii=False, indent=2))
    (OUT / 'v90_active_picks.json').write_text(json.dumps(recent_contracts, ensure_ascii=False, indent=2))
    (OUT / 'v128_parallel_shadow_candidates.json').write_text(json.dumps(v128_parallel, ensure_ascii=False, indent=2))
    (OUT / 'v128_parallel_shadow_recent45.json').write_text(json.dumps(v128_recent, ensure_ascii=False, indent=2))
    (OUT / 'v90_daily_scan_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    with (OUT / 'v90_active_picks.csv').open('w', newline='') as fp:
        fields = sorted({k for r in recent_contracts for k in r.keys()}) if recent_contracts else []
        w = csv.DictWriter(fp, fieldnames=fields, extrasaction='ignore')
        if fields:
            w.writeheader(); w.writerows(recent_contracts)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
