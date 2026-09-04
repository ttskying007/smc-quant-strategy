#!/usr/bin/env python3
"""V101: enrich V100 production/audit rows with multi-timeframe state, per-symbol SMC DNA,
and explicit combo contracts.

This is intentionally a non-invasive contract layer:
- V100 signal/entry/exit math is unchanged.
- V100 A_PRODUCTION_CORE remains the only production whitelist seed.
- New combo contracts are classified and reported, but non-whitelisted combos stay candidate/watch only.
"""
from __future__ import annotations

import json
from pathlib import Path
from collections import Counter, defaultdict
from typing import Any, Dict, List, Tuple

ROOT = Path('/root/.hermes')
SRC_DIR = ROOT / 'smc_opt_v100_structural_net_gate'
OUT_DIR = ROOT / 'smc_opt_v101_mtf_dna_combo_contract'
KLINE_DAILY = ROOT / 'kline_cache'
KLINE_WEEKLY = ROOT / 'kline_cache'
KLINE_WEEKLY_ALT = ROOT / 'kline_cache_weekly'
KLINE_60 = ROOT / 'kline_cache_60min'
OUT_DIR.mkdir(parents=True, exist_ok=True)

ENGINE = 'V101_MTF_DNA_COMBO_CONTRACT'
FEE_PCT = 0.12
NET_SUCCESS_PCT = 0.8

PRODUCTION_COMBO_WHITELIST = {
    'REVERSAL_SSL_CHOCH_DEMAND_OB_STRUCTURAL_5R',
}

CANDIDATE_COMBO_WHITELIST = {
    'CONTINUATION_BOS_PULLBACK_STRUCTURAL',
}

COMBO_CONTRACTS: Dict[str, Dict[str, Any]] = {
    'REVERSAL_SSL_CHOCH_DEMAND_OB_STRUCTURAL_5R': {
        'family': 'REVERSAL',
        'entry_rule': 'SSL sweep -> CHOCH -> pullback into demand OB/POI -> zone-mid limit anticipation',
        'wait_rule': 'wait for confirmed sweep/CHOCH and first return into POI; do not chase after TP1 distance is consumed',
        'sl_rule': 'below POI low / SSL with 0.5% buffer; no same-day exit; reject if risk_pct > 1.0',
        'tp_rule': 'TP2 must be structural BSL/EQH/swing-high target with >=5R and expected net >=0.8%; TP3 runner >=8R',
        'production_gate': 'V100 A_PRODUCTION_CORE + MIXED + low volatility/risk + whitelist',
    },
    'CONTINUATION_BOS_PULLBACK_STRUCTURAL': {
        'family': 'CONTINUATION',
        'entry_rule': 'BOS continuation only after price holds above broken structure and retests demand/OB from above',
        'wait_rule': 'requires hold-above-POI confirmation; never share reversal entry timing',
        'sl_rule': 'below retest HL / demand POI invalidation; reject if retest closes below broken structure',
        'tp_rule': 'next BSL/EQH/swing-high ladder; separate RR gate to be calibrated before production',
        'production_gate': 'CANDIDATE_ONLY until full-market validation passes; must not mix into reversal production pool',
    },
    'PULLBACK_DISCOUNT_RECLAIM': {
        'family': 'PULLBACK',
        'entry_rule': 'discount-zone reclaim after demand touch and structure remains intact',
        'wait_rule': 'requires reclaim candle and no weak-environment downgrade',
        'sl_rule': 'below discount POI low or latest HL',
        'tp_rule': 'equilibrium -> BSL ladder; not eligible for reversal whitelist',
        'production_gate': 'WATCH_ONLY pending independent statistics',
    },
    'BREAKOUT_BOS_ACCEPTANCE': {
        'family': 'BREAKOUT',
        'entry_rule': 'BOS breakout acceptance above broken structure with retest support',
        'wait_rule': 'requires 1-3 bars acceptance, no immediate gap chase',
        'sl_rule': 'below breakout base / acceptance low',
        'tp_rule': 'next liquidity pool; separate trailing contract',
        'production_gate': 'CANDIDATE_ONLY pending independent statistics',
    },
    'FAILED_BREAK_REVERSAL_RECLAIM': {
        'family': 'FAILED_BREAK_REVERSAL',
        'entry_rule': 'failed breakdown/sweep reclaimed back into range; enter on reclaim hold',
        'wait_rule': 'requires failed-break evidence and range reclaim',
        'sl_rule': 'below failed-break extreme',
        'tp_rule': 'range EQ -> opposite liquidity',
        'production_gate': 'WATCH_ONLY pending independent statistics',
    },
}


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def fnum(x: Any, default: float = 0.0) -> float:
    try:
        if x in (None, ''):
            return default
        return float(x)
    except Exception:
        return default


def dkey(v: Any) -> str:
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def sym_file_key(symbol: str) -> str:
    s = str(symbol or '').replace('.', '_')
    if '_' in s:
        code, exch = s.split('_', 1)
        return f'{code}_{exch}'
    return s


def symbol_from_file_key(key: str) -> str:
    parts = key.split('_')
    if len(parts) >= 2 and parts[1] in ('SH', 'SZ', 'BJ'):
        return f'{parts[0]}.{parts[1]}'
    return key.replace('_', '.')


def all_cached_symbols() -> List[str]:
    symbols = set()
    for p in KLINE_DAILY.glob('*_daily_*.json'):
        symbols.add(symbol_from_file_key(p.name.split('_daily_')[0]))
    return sorted(symbols)


def kline_path(symbol: str, tf: str) -> Path | None:
    key = sym_file_key(symbol)
    candidates: List[Path]
    if tf == 'D':
        candidates = [KLINE_DAILY / f'{key}_daily_750.json', KLINE_DAILY / f'{key}_daily_300.json']
    elif tf == 'W':
        candidates = [KLINE_WEEKLY / f'{key}_weekly_200.json', KLINE_WEEKLY_ALT / f'{key}_weekly_100.json']
    else:
        candidates = [KLINE_60 / f'{key}_60min_500.json', KLINE_60 / f'{key}_60min_200.json']
    for p in candidates:
        if p.exists():
            return p
    return None


def load_klines(symbol: str, tf: str) -> List[Dict[str, Any]]:
    p = kline_path(symbol, tf)
    rows = load_json(p, []) if p else []
    if not isinstance(rows, list):
        return []
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        x = dict(r)
        for k in ('o', 'h', 'l', 'c', 'v'):
            if k in x:
                x[k] = fnum(x.get(k))
        x['date_key'] = dkey(x.get('t') or x.get('date') or x.get('day') or x.get('time'))
        out.append(x)
    return [r for r in out if r.get('date_key')]


def rows_until(rows: List[Dict[str, Any]], date_key: str, tf: str) -> List[Dict[str, Any]]:
    if not date_key:
        return rows
    if tf in ('D', 'W'):
        cut = [r for r in rows if r.get('date_key', '') <= date_key]
        return cut or rows
    # Tencent 60min date_key may include yyyymmddhhmm; first 8 chars are enough.
    cut = [r for r in rows if str(r.get('date_key', ''))[:8] <= date_key]
    return cut or rows


def ma(vals: List[float], n: int) -> float:
    if not vals:
        return 0.0
    xs = vals[-n:] if len(vals) >= n else vals
    return sum(xs) / len(xs)


def pivot_sequence(rows: List[Dict[str, Any]], lookback: int = 60) -> Tuple[str, str]:
    seg = rows[-lookback:] if len(rows) > lookback else rows
    if len(seg) < 8:
        return 'INSUFFICIENT', 'UNKNOWN'
    highs = [fnum(r.get('h')) for r in seg]
    lows = [fnum(r.get('l')) for r in seg]
    mid = len(seg) // 2
    first_h, last_h = max(highs[:mid]), max(highs[mid:])
    first_l, last_l = min(lows[:mid]), min(lows[mid:])
    if last_h > first_h and last_l > first_l:
        return 'HH_HL', 'UP_STRUCTURE'
    if last_h < first_h and last_l < first_l:
        return 'LH_LL', 'DOWN_STRUCTURE'
    if last_h > first_h and last_l < first_l:
        return 'EXPANDING', 'VOLATILE_RANGE'
    return 'COMPRESSED', 'RANGE_STRUCTURE'


def tf_state(symbol: str, date_key: str, tf: str) -> Dict[str, Any]:
    rows = rows_until(load_klines(symbol, tf), date_key, tf)
    if len(rows) < 20:
        return {
            'tf': tf,
            'available': False,
            'date': rows[-1].get('date_key') if rows else '',
            'trend_state': 'UNKNOWN',
            'phase': 'NO_DATA',
            'permission': 'NO_TRADE_PERMISSION',
            'conflict': 'DATA_MISSING',
            'close': 0,
            'ma20': 0,
            'ma60': 0,
            'structure_seq': 'INSUFFICIENT',
        }
    closes = [fnum(r.get('c')) for r in rows]
    c = closes[-1]
    m20 = ma(closes, 20)
    m60 = ma(closes, 60)
    seq, structure = pivot_sequence(rows)
    if c > m20 > m60 and structure in ('UP_STRUCTURE', 'RANGE_STRUCTURE'):
        trend = 'UPTREND_CONFIRMED'
        phase = 'MARKUP_OR_CONTINUATION'
        permission = 'CONTINUATION_ALLOWED'
    elif c > m20 and structure != 'DOWN_STRUCTURE':
        trend = 'RECOVERY_TRANSITION'
        phase = 'ACCUMULATION_TO_MARKUP'
        permission = 'REVERSAL_AND_PULLBACK_ALLOWED'
    elif c < m20 < m60 and structure == 'DOWN_STRUCTURE':
        trend = 'DOWNTREND_CONFIRMED'
        phase = 'MARKDOWN'
        permission = 'REVERSAL_ONLY_AFTER_SSL_CHOCH'
    else:
        trend = 'RANGE_OR_MIXED'
        phase = 'BALANCE'
        permission = 'SELECTIVE_REVERSAL_ONLY'
    conflict = 'NONE'
    if c < m20 and structure == 'UP_STRUCTURE':
        conflict = 'PRICE_BELOW_MA20_BUT_STRUCTURE_UP'
    elif c > m20 and structure == 'DOWN_STRUCTURE':
        conflict = 'PRICE_ABOVE_MA20_BUT_STRUCTURE_DOWN'
    return {
        'tf': tf,
        'available': True,
        'date': rows[-1].get('date_key'),
        'trend_state': trend,
        'phase': phase,
        'permission': permission,
        'conflict': conflict,
        'close': round(c, 4),
        'ma20': round(m20, 4),
        'ma60': round(m60, 4),
        'structure_seq': seq,
        'structure_state': structure,
        'bars': len(rows),
    }


def mtf_contract(row: Dict[str, Any]) -> Dict[str, Any]:
    symbol = row.get('symbol')
    date_key = dkey(row.get('pick_date') or row.get('select_date') or row.get('entry_date') or row.get('event_date'))
    day = tf_state(symbol, date_key, 'D')
    week = tf_state(symbol, date_key, 'W')
    m60 = tf_state(symbol, date_key, '60')
    conflicts = [x['tf'] + ':' + x['conflict'] for x in (week, day, m60) if x.get('conflict') not in ('NONE', '')]
    permissions = {x['tf']: x.get('permission') for x in (week, day, m60)}
    if week.get('trend_state') == 'UPTREND_CONFIRMED' and day.get('trend_state') in ('UPTREND_CONFIRMED', 'RECOVERY_TRANSITION'):
        global_permission = 'MTF_LONG_ALLOWED'
    elif row.get('event_type') == 'SSL_SWEEP_CHOCH_REVERSAL' and day.get('trend_state') != 'DOWNTREND_CONFIRMED':
        global_permission = 'REVERSAL_ALLOWED_DAILY_CONFIRMED'
    elif row.get('event_type') == 'SSL_SWEEP_CHOCH_REVERSAL' and day.get('trend_state') == 'DOWNTREND_CONFIRMED':
        global_permission = 'REVERSAL_ONLY_HIGH_RISK'
    else:
        global_permission = 'WATCH_ONLY_MTF_CONFLICT'
    return {
        'trend_tf': 'W',
        'signal_tf': 'D',
        'entry_tf': '60min/D',
        'weekly_state': week,
        'daily_state': day,
        'm60_state': m60,
        'mtf_stage': f"W:{week.get('phase')}|D:{day.get('phase')}|60:{m60.get('phase')}",
        'mtf_trend_permission': global_permission,
        'mtf_conflict_state': 'NONE' if not conflicts else ';'.join(conflicts),
        'mtf_permissions': permissions,
    }


def combo_key(row: Dict[str, Any]) -> str:
    event = str(row.get('event_type') or row.get('source_event') or row.get('signal_type') or '').upper()
    zone = str(row.get('zone_type') or row.get('poi_type') or '').upper()
    entry = str(row.get('entry_mode') or row.get('entry_semantic') or '').upper()
    if 'SSL_SWEEP_CHOCH' in event and ('DEMAND' in zone or 'OB' in zone):
        return 'REVERSAL_SSL_CHOCH_DEMAND_OB_STRUCTURAL_5R'
    if 'BOS_CONTINUATION' in event or ('BOS' in event and 'CONTINUATION' in event):
        return 'CONTINUATION_BOS_PULLBACK_STRUCTURAL'
    if 'BREAKOUT' in event or ('BOS' in event and 'PULLBACK' not in entry):
        return 'BREAKOUT_BOS_ACCEPTANCE'
    if 'FAILED' in event or 'RECLAIM' in entry:
        return 'FAILED_BREAK_REVERSAL_RECLAIM'
    if 'PULLBACK' in entry or row.get('pd_zone') in ('DISCOUNT', 'DEEP_DISCOUNT'):
        return 'PULLBACK_DISCOUNT_RECLAIM'
    return 'PULLBACK_DISCOUNT_RECLAIM'


def build_dna(trades: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    by_symbol: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in trades:
        by_symbol[str(r.get('symbol') or '')].append(r)
    dna = {}
    for sym in sorted(set(by_symbol) | set(all_cached_symbols())):
        rows = by_symbol.get(sym, [])
        if not sym:
            continue
        n = len(rows)
        if not rows:
            daily = tf_state(sym, '', 'D')
            weekly = tf_state(sym, '', 'W')
            m60 = tf_state(sym, '', '60')
            preferred = 'WATCH_ONLY_NO_TRADE_SAMPLE'
            if daily.get('trend_state') in ('UPTREND_CONFIRMED', 'RECOVERY_TRANSITION'):
                preferred = 'CONTINUATION_OR_PULLBACK_CANDIDATE'
            elif daily.get('trend_state') == 'RANGE_OR_MIXED':
                preferred = 'RANGE_ROTATION_CANDIDATE'
            dna[sym] = {
                'symbol': sym,
                'sample_n': 0,
                'net_wr_ge_0_8': 0.0,
                'avg_net_pnl': 0.0,
                'preferred_behavior': preferred,
                'best_event_type': 'NO_VALIDATED_SAMPLE',
                'common_main_force_behavior': daily.get('phase') or 'UNKNOWN',
                'effective_entry_mode': 'WATCH_ONLY_UNVALIDATED',
                'effective_combo': 'WATCH_ONLY_UNVALIDATED',
                'effective_timeframes': {'trend_tf': 'W', 'signal_tf': 'D', 'entry_tf': '60min/D'},
                'timeframe_profile': {'weekly': weekly, 'daily': daily, 'm60': m60},
                'event_stats': {},
            }
            continue
        wins = [r for r in rows if fnum(r.get('net_pnl_pct'), fnum(r.get('pnl_pct')) - FEE_PCT) >= NET_SUCCESS_PCT]
        avg = sum(fnum(r.get('net_pnl_pct'), fnum(r.get('pnl_pct')) - FEE_PCT) for r in rows) / max(1, n)
        event_stats = {}
        for event in sorted({r.get('event_type') or r.get('source_event') or 'UNKNOWN' for r in rows}):
            rs = [r for r in rows if (r.get('event_type') or r.get('source_event') or 'UNKNOWN') == event]
            event_stats[event] = {
                'n': len(rs),
                'net_wr': round(sum(1 for r in rs if fnum(r.get('net_pnl_pct'), fnum(r.get('pnl_pct')) - FEE_PCT) >= NET_SUCCESS_PCT) / len(rs) * 100, 2),
                'avg_net': round(sum(fnum(r.get('net_pnl_pct'), fnum(r.get('pnl_pct')) - FEE_PCT) for r in rs) / len(rs), 4),
            }
        best_event = max(event_stats.items(), key=lambda kv: (kv[1]['net_wr'], kv[1]['avg_net'], kv[1]['n']))[0] if event_stats else 'UNKNOWN'
        combos = Counter(combo_key(r) for r in rows)
        entries = Counter(r.get('entry_mode') or r.get('entry_semantic') or 'UNKNOWN' for r in rows)
        markets = Counter(r.get('market_state') or 'UNKNOWN' for r in rows)
        if 'SSL_SWEEP_CHOCH' in best_event:
            behavior = 'REVERSAL_SPECIALIST'
        elif 'BOS' in best_event:
            behavior = 'CONTINUATION_OR_BREAKOUT_SPECIALIST'
        elif markets.most_common(1)[0][0] in ('RANGE', 'MIXED'):
            behavior = 'RANGE_ROTATION_SPECIALIST'
        else:
            behavior = 'WATCH_ONLY_UNCLASSIFIED'
        dna[sym] = {
            'symbol': sym,
            'sample_n': n,
            'net_wr_ge_0_8': round(len(wins) / n * 100, 2),
            'avg_net_pnl': round(avg, 4),
            'preferred_behavior': behavior,
            'best_event_type': best_event,
            'common_main_force_behavior': markets.most_common(1)[0][0] if markets else 'UNKNOWN',
            'effective_entry_mode': entries.most_common(1)[0][0] if entries else 'UNKNOWN',
            'effective_combo': combos.most_common(1)[0][0] if combos else 'UNKNOWN',
            'effective_timeframes': {'trend_tf': 'W', 'signal_tf': 'D', 'entry_tf': '60min/D'},
            'event_stats': event_stats,
        }
    return dna


def enrich_row(row: Dict[str, Any], dna: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    x = dict(row)
    realized_hold = x.get('hold_bars_realized')
    if realized_hold not in (None, ''):
        x['hold_bars'] = realized_hold
    elif x.get('hold_bars') in (None, '', 0) and x.get('entry_idx') not in (None, '') and x.get('exit_idx') not in (None, ''):
        x['hold_bars'] = max(0, int(fnum(x.get('exit_idx')) - fnum(x.get('entry_idx'))))
    if not x.get('conf_type'):
        x['conf_type'] = x.get('signal_type') or x.get('source_event') or x.get('event_type') or 'UNKNOWN'
    if not x.get('signal_price'):
        x['signal_price'] = x.get('break_level') or x.get('price') or x.get('entry_price')
    mtf = mtf_contract(x)
    ck = combo_key(x)
    contract = COMBO_CONTRACTS[ck]
    sym_dna = dna.get(str(x.get('symbol') or ''), {})
    x.update(mtf)
    for prefix, state_key in (('weekly', 'weekly_state'), ('daily', 'daily_state'), ('m60', 'm60_state')):
        state = x.get(state_key) or {}
        x[f'{prefix}_trend_state'] = state.get('trend_state') or 'UNKNOWN'
        x[f'{prefix}_phase'] = state.get('phase') or 'UNKNOWN'
        x[f'{prefix}_permission'] = state.get('permission') or 'UNKNOWN'
        x[f'{prefix}_conflict'] = state.get('conflict') or 'UNKNOWN'
        x[f'{prefix}_structure_state'] = state.get('structure_state') or 'UNKNOWN'
        x[f'{prefix}_structure_seq'] = state.get('structure_seq') or 'UNKNOWN'
    x['combo_entry_rule'] = contract['entry_rule']
    x['combo_wait_rule'] = contract['wait_rule']
    x['combo_sl_rule'] = contract['sl_rule']
    x['combo_tp_rule'] = contract['tp_rule']
    x['combo_production_gate'] = contract['production_gate']
    x['smc_dna'] = sym_dna
    x['dna_preferred_behavior'] = sym_dna.get('preferred_behavior') or 'UNKNOWN'
    x['dna_effective_entry_mode'] = sym_dna.get('effective_entry_mode') or x.get('entry_mode') or x.get('entry_semantic')
    x['dna_effective_combo'] = sym_dna.get('effective_combo') or ck
    x['combo_contract_key'] = ck
    x['combo_family'] = contract['family']
    x['combo_contract'] = contract
    whitelist = ck in PRODUCTION_COMBO_WHITELIST
    candidate_whitelist = ck in CANDIDATE_COMBO_WHITELIST
    v100_a = x.get('v100_tier') == 'A_PRODUCTION_CORE' or x.get('production_grade') == 'A_PRODUCTION'
    mtf_ok = x.get('mtf_trend_permission') in ('MTF_LONG_ALLOWED', 'REVERSAL_ALLOWED_DAILY_CONFIRMED', 'REVERSAL_ONLY_HIGH_RISK')
    bos_candidate_gate = (
        ck == 'CONTINUATION_BOS_PULLBACK_STRUCTURAL'
        and x.get('mtf_trend_permission') == 'MTF_LONG_ALLOWED'
        and fnum(x.get('tp2_rr')) >= 5.0
        and fnum(x.get('tp3_rr')) >= 8.0
        and fnum(x.get('expected_tp2_net_pct')) >= NET_SUCCESS_PCT
        and 0 < fnum(x.get('risk_pct')) <= 1.2
    )
    x['production_whitelist_v101'] = whitelist
    x['production_eligible_v101'] = bool(v100_a and whitelist and mtf_ok)
    x['combo_candidate_whitelist_v101'] = candidate_whitelist
    x['combo_candidate_eligible_v101'] = bool(candidate_whitelist and bos_candidate_gate)
    x['combo_candidate_gate_reason_v101'] = (
        'BOS_CONTINUATION_MTF_LONG_TP2_GE_5R_TP3_GE_8R_NET_GE_0_8_RISK_LE_1_2'
        if x['combo_candidate_eligible_v101'] else ''
    )
    x['production_grade_v101'] = (
        'A_PRODUCTION' if x['production_eligible_v101']
        else 'BOS_CONTINUATION_CANDIDATE' if x['combo_candidate_eligible_v101']
        else 'CANDIDATE_ONLY' if whitelist
        else 'WATCH_ONLY_COMBO_NOT_WHITELISTED'
    )
    x['engine_v100'] = x.get('engine')
    x['engine'] = ENGINE
    return x


def field_missing(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    keys = [
        'trend_tf', 'signal_tf', 'entry_tf', 'weekly_state', 'daily_state', 'm60_state',
        'weekly_trend_state', 'daily_trend_state', 'm60_trend_state',
        'weekly_phase', 'daily_phase', 'm60_phase',
        'weekly_permission', 'daily_permission', 'm60_permission',
        'weekly_conflict', 'daily_conflict', 'm60_conflict',
        'weekly_structure_state', 'daily_structure_state', 'm60_structure_state',
        'mtf_stage', 'mtf_trend_permission', 'mtf_conflict_state', 'smc_dna',
        'dna_preferred_behavior', 'dna_effective_entry_mode', 'dna_effective_combo',
        'combo_contract_key', 'combo_family', 'combo_contract',
        'combo_entry_rule', 'combo_wait_rule', 'combo_sl_rule', 'combo_tp_rule', 'combo_production_gate',
        'production_whitelist_v101', 'production_eligible_v101', 'production_grade_v101',
        'combo_candidate_whitelist_v101', 'combo_candidate_eligible_v101',
        'pick_date', 'join_date', 'zone', 'zone_type', 'cost_line', 'smart_money_cost', 'volatility_pct',
    ]
    return {k: sum(1 for r in rows if r.get(k) in (None, '', {}, [])) for k in keys}


def stats(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {'n': 0}
    n = len(rows)
    wins = [r for r in rows if fnum(r.get('net_pnl_pct'), fnum(r.get('pnl_pct')) - FEE_PCT) >= NET_SUCCESS_PCT]
    return {
        'n': n,
        'net_wr_ge_0_8': round(len(wins) / n * 100, 2),
        'avg_net_pnl': round(sum(fnum(r.get('net_pnl_pct'), fnum(r.get('pnl_pct')) - FEE_PCT) for r in rows) / n, 4),
        'sl_rate': round(sum(1 for r in rows if r.get('exit_reason') == 'SL_HIT') / n * 100, 2),
    }


def main() -> None:
    trades = load_json(SRC_DIR / 'v100_trades.json', [])
    active_picks = load_json(SRC_DIR / 'v100_active_picks.json', [])
    watch_picks = load_json(SRC_DIR / 'v100_watch_picks.json', [])
    if not isinstance(trades, list):
        raise SystemExit('v100_trades.json is not a list')
    dna = build_dna(trades)
    enriched_trades = [enrich_row(r, dna) for r in trades]
    enriched_active = [enrich_row(r, dna) for r in active_picks if isinstance(r, dict)]
    enriched_watch = [enrich_row(r, dna) for r in watch_picks if isinstance(r, dict)]
    production = [r for r in enriched_trades if r.get('production_eligible_v101')]
    bos_continuation_candidates = [r for r in enriched_trades if r.get('combo_candidate_eligible_v101')]
    active_production_picks = [r for r in enriched_active if r.get('production_eligible_v101')]
    candidate_picks = [r for r in enriched_active + enriched_watch if not r.get('production_eligible_v101')]

    report = {
        'engine': ENGINE,
        'version': 'V101',
        'source': str(SRC_DIR),
        'contract': 'V101 adds MTF fields + per-symbol SMC DNA + combo contracts; V100 A production whitelist is preserved; new combos are candidates until separately validated.',
        'production_combo_whitelist': sorted(PRODUCTION_COMBO_WHITELIST),
        'candidate_combo_whitelist': sorted(CANDIDATE_COMBO_WHITELIST),
        'combo_contracts': COMBO_CONTRACTS,
        'trade_total_all_audit': len(enriched_trades),
        'production_total': len(production),
        'active_pick_total': len(active_production_picks),
        'candidate_pick_total': len(candidate_picks),
        'bos_continuation_candidate_total': len(bos_continuation_candidates),
        'dna_symbol_total': len(dna),
        'production_stats': stats(production),
        'bos_continuation_candidate_stats': stats(bos_continuation_candidates),
        'combo_counts_all': dict(Counter(r.get('combo_contract_key') for r in enriched_trades)),
        'combo_counts_production': dict(Counter(r.get('combo_contract_key') for r in production)),
        'combo_counts_candidate_whitelist': dict(Counter(r.get('combo_contract_key') for r in bos_continuation_candidates)),
        'family_counts_all': dict(Counter(r.get('combo_family') for r in enriched_trades)),
        'mtf_permission_counts_all': dict(Counter(r.get('mtf_trend_permission') for r in enriched_trades)),
        'mtf_conflict_counts_all': dict(Counter(r.get('mtf_conflict_state') for r in enriched_trades)),
        'field_missing_active': field_missing(active_production_picks),
        'field_missing_candidates': field_missing(candidate_picks),
        't1_violations': sum(1 for r in enriched_trades if dkey(r.get('entry_date')) and dkey(r.get('entry_date')) == dkey(r.get('exit_date'))),
    }
    (OUT_DIR / 'v101_trades.json').write_text(json.dumps(enriched_trades, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v101_active_picks.json').write_text(json.dumps(active_production_picks, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v101_candidate_picks.json').write_text(json.dumps(candidate_picks, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v101_bos_continuation_candidates.json').write_text(json.dumps(bos_continuation_candidates, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v101_symbol_dna.json').write_text(json.dumps(dna, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v101_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
