#!/usr/bin/env python3
"""V91 shadow scanner for zone-position entry experiments.

Scanner-only layer: generates current/recent active picks from V85 candidates
using V91 audit-proven daily zone_mid/zone_low limit-entry contracts. It does
not replace the V88 production backtest baseline.
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
from v85_mixed_accumulation_generator import generate_v85_candidates, zone_width_pct
from v90_daily_full_market_scanner import known_bsl_target, recovery_substate
from v93_recovery_time_runner_audit import recovery_gate_label, recovery_passes_v93

OUT = Path('/root/.hermes/smc_opt_v91_shadow_zone_entry_scanner')
OUT.mkdir(parents=True, exist_ok=True)

ENGINE = 'V91_SHADOW_ZONE_ENTRY_SCANNER'
SIGNAL_LAYER = 'V85_SIGNAL_LAYER_ZONE_ENTRY_RECOVERY'
CONTRACT_SOURCE = 'V91_SHADOW_DAILY_ZONE_MID_LOW_LIMIT_ENTRY'
RECENT_BARS = 45


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


def price_in_bar(b: Dict[str, Any], price: float) -> bool:
    return num(b.get('l')) <= price <= num(b.get('h'))


def v91_gate_reason(row: Dict[str, Any]) -> str:
    entry = num(row.get('entry_price'))
    zl = num(row.get('zone_low'))
    risk = num(row.get('risk_pct')) or ((entry / zl - 1) * 100 if entry and zl else 999.0)
    width = num(row.get('v85_zone_width_pct'), 999.0)
    hold = num(row.get('hold_bars'), 999.0)
    takeover = row.get('v83_takeover_type') == 'HOLD_ABOVE_POI'
    if takeover and 1.0 < width <= 1.6 and 1.0 < risk <= 1.5 and hold <= 2:
        return 'PASS'
    if takeover and risk > 1.5 and width <= 1.6 and hold <= 2:
        return 'RISK'
    if takeover and risk > 1.5 and width <= 1.6 and hold > 2:
        return 'RISK_HOLD_LAG'
    return 'REJECT'


def entry_plan_for(row: Dict[str, Any]) -> Tuple[str, float]:
    gate = v91_gate_reason(row)
    zl = num(row.get('zone_low'))
    zh = num(row.get('zone_high'))
    if gate == 'PASS':
        return 'zone_mid_limit_micro', (zl + zh) / 2
    if gate in {'RISK', 'RISK_HOLD_LAG'}:
        return 'zone_mid_limit_micro', (zl + zh) / 2
    return '', 0.0


def fill_idx_for_limit(row: Dict[str, Any], ks: List[Dict[str, Any]], limit_price: float) -> int:
    touch_idx = int(num(row.get('touch_idx'), row.get('entry_idx') or -1))
    entry_idx = int(num(row.get('entry_idx'), -1))
    start = max(1, touch_idx if touch_idx >= 0 else entry_idx)
    end = min(len(ks), max(start + 1, entry_idx + 6))
    for i in range(start, end):
        if price_in_bar(ks[i], limit_price):
            return i
    return -1


def contract_from_candidate(c: Dict[str, Any], ks: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    gate = v91_gate_reason(c)
    if gate == 'REJECT':
        return None
    entry_mode, entry = entry_plan_for(c)
    if not entry:
        return None
    fill_idx = fill_idx_for_limit(c, ks, entry)
    if fill_idx < 1 or fill_idx >= len(ks):
        return None
    pick_date = date_key(c.get('pick_date') or c.get('select_date') or c.get('event_date'))
    join_date = bar_date(ks[fill_idx])
    if not pick_date or not join_date or pick_date == join_date:
        return None

    zl = num(c.get('zone_low'))
    zh = num(c.get('zone_high'))
    width = zone_width_pct(c)
    risk_pct_signal = num(c.get('risk_pct')) or ((entry / zl - 1) * 100 if entry and zl else 0.0)
    # V91 audit contract: zone_mid micro layer first, with tight below-zone stop.
    sl = max(zl * 0.995, entry * 0.975)
    risk_abs = max(entry - sl, 0.000001)
    tp1 = entry + risk_abs * 0.8
    tp2 = entry + risk_abs * 1.5
    tp3 = entry + risk_abs * 3.0
    bsl = known_bsl_target(ks, fill_idx, entry)
    substate = recovery_substate(c, ks)
    rec_label = recovery_gate_label({
        'market_state': c.get('market_state'),
        'daily_state': c.get('daily_state') or c.get('v91_daily_state') or '',
        'gate': gate,
        'hold_bars': c.get('hold_bars'),
        'zone_width': width,
        'risk_signal': risk_pct_signal,
    })
    rec_pass = recovery_passes_v93({
        'market_state': c.get('market_state'),
        'daily_state': c.get('daily_state') or c.get('v91_daily_state') or '',
        'gate': gate,
        'hold_bars': c.get('hold_bars'),
        'zone_width': width,
        'risk_signal': risk_pct_signal,
    })
    # V93: RECOVERY remains quarantined except the audited secondary gate:
    # daily=BULL_CONTINUATION, hold<=1, width<=1.6, risk_signal>5.
    if c.get('market_state') == 'RECOVERY' and not rec_pass:
        return None

    row = dict(c)
    row.update(bsl)
    row.update({
        'engine': ENGINE,
        'signal_engine': SIGNAL_LAYER,
        'contract_source': CONTRACT_SOURCE,
        'v91_shadow_scanner': True,
        'v91_gate_reason': gate,
        'v93_recovery_gate_label': rec_label,
        'v93_recovery_pass': rec_pass,
        'daily_state': c.get('daily_state') or c.get('v91_daily_state') or '',
        'v93_time_stop_runner_variant': 'mfe_50pct_cap_3r',
        'v93_time_stop_runner_rule': 'IF_TIME_STOP_AND_MFE_GE_1_5R_DELAY_EXIT_CAPTURE_50PCT_MFE_CAP_3R',
        'v91_entry_layer': entry_mode,
        'v90_recovery_substate': substate,
        'v91_target_semantics': 'DAILY_ZONE_MID_LIMIT_ENTRY_MICRO_LADDER_PRE_ENTRY_BSL_AUDITED',
        'liquidity_target_original_future_v86': c.get('liquidity_target'),
        'liquidity_target': num(bsl.get('known_bsl_target')) or '',
        'entry_mode': entry_mode,
        'sl_mode': 'zone_low_0_5pct_or_2_5pct_tight',
        'tp_mode': 'micro_0_8_1_5_3_zone_entry',
        'pick_date': pick_date,
        'select_date': pick_date,
        'join_date': join_date,
        'entry_date': join_date,
        'entry_idx': fill_idx,
        'price': round(entry, 4),
        'entry_price': round(entry, 4),
        'sl': round(sl, 4),
        'sl_price': round(sl, 4),
        'tp1': round(tp1, 4),
        'tp2': round(tp2, 4),
        'tp3': round(tp3, 4),
        'tp': round(tp1, 4),
        'tp1_price': round(tp1, 4),
        'rr': round((tp2 - entry) / risk_abs, 4) if risk_abs else 0,
        'risk_pct': round((entry / sl - 1) * 100, 4) if sl else 0,
        'risk_pct_signal': round(risk_pct_signal, 4),
        'zone_type': c.get('zone_type') or c.get('poi_type') or 'DEMAND_OB',
        'signal_type': c.get('signal_type') or c.get('event_type') or c.get('poi_type') or 'DEMAND_OB',
        'zone_low': round(zl, 4),
        'zone_high': round(zh, 4),
        'smart_money_cost': round((zl + zh) / 2 if zl and zh else entry, 4),
        'cost_line': round((zl + zh) / 2 if zl and zh else entry, 4),
        'volatility_pct': round(width or risk_pct_signal or 0.01, 4),
        'volatility': round(width or risk_pct_signal or 0.01, 4),
        'vol_class': f"{gate}|{substate or c.get('market_state') or ''}",
        'zone': f"{round(zl, 4):.4f}~{round(zh, 4):.4f}",
        'pickDate': pick_date,
        'joinDate': join_date,
        'selectDate': pick_date,
        'entryDate': join_date,
        '选股日期': pick_date,
        '加入日期': join_date,
        'pick_scope': 'ACTIVE_CANDIDATE',
        'is_active_pick': True,
        'setup_status': 'V91_SHADOW_ACTIVE_CANDIDATE',
        'state': 'ACTIVE_CANDIDATE',
        'sample_class': 'V91_SHADOW_DAILY_ZONE_ENTRY_CANDIDATE',
        'planned_exit_signal': 'V91_SHADOW_PLAN_NOT_BACKTEST_EXIT',
        'planned_exit_legs': [
            {'name': 'TP1_0_8R', 'price': round(tp1, 4), 'weight': 0.35},
            {'name': 'TP2_1_5R', 'price': round(tp2, 4), 'weight': 0.35},
            {'name': 'TP3_3R_RUNNER', 'price': round(tp3, 4), 'weight': 0.30},
        ],
    })
    return row


def field_audit(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    required = ['engine','pick_date','join_date','选股日期','加入日期','zone_type','zone_low','zone_high','zone','cost_line','volatility_pct','volatility','entry_price','sl','tp1','tp2','tp3','rr','v91_target_semantics','v91_gate_reason']
    numeric = {'zone_low','zone_high','cost_line','entry_price','sl','tp1','tp2','tp3','rr','volatility_pct','volatility'}
    return {k: sum(1 for r in rows if r.get(k) in (None, '') or (k in numeric and num(r.get(k)) <= 0)) for k in required}


def bucket(rows: Iterable[Dict[str, Any]], key: Callable[[Dict[str, Any]], Any]) -> Dict[str, Dict[str, Any]]:
    g: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        g[str(key(r))].append(r)
    return {k: {'n': len(v)} for k, v in sorted(g.items())}


def main() -> None:
    env_raw = load_json(ENV_PATH)
    env_by_date = {str(k)[:8]: normalize_env(v) for k, v in env_raw.items()}
    scanned = 0
    all_contracts: List[Dict[str, Any]] = []
    latest_date = ''
    latest_by_symbol: Dict[str, Dict[str, Any]] = {}
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
            c = dict(c)
            c['v85_zone_width_pct'] = round(zone_width_pct(c), 4)
            entry_idx = int(num(c.get('entry_idx'), -1))
            takeover_idx = int(num(c.get('v83_takeover_idx'), c.get('reclaim_idx') or -1))
            c['hold_bars'] = max(0, entry_idx - takeover_idx) if entry_idx >= 0 and takeover_idx >= 0 else 999
            gate = v91_gate_reason(c)
            if gate == 'REJECT':
                reject_counts['V91_GATE_REJECT'] += 1
                continue
            row = contract_from_candidate(c, ks)
            if row is None:
                reject_counts[f'{gate}_NO_EXECUTABLE_LIMIT_OR_RECOVERY_FAIL'] += 1
                continue
            all_contracts.append(row)
            old = latest_by_symbol.get(sym)
            if old is None or date_key(row.get('entry_date')) > date_key(old.get('entry_date')):
                latest_by_symbol[sym] = row

    recent_contracts: List[Dict[str, Any]] = []
    for r in latest_by_symbol.values():
        p = KLINE_DIR / f"{str(r.get('symbol')).replace('.', '_')}_daily_750.json"
        ks = load_json(p) if p.exists() else []
        dist = len(ks) - 1 - int(num(r.get('entry_idx'), -9999))
        r['bars_since_entry'] = dist
        if 0 <= dist <= RECENT_BARS:
            recent_contracts.append(r)

    recent_contracts.sort(key=lambda r: (int(num(r.get('bars_since_entry'), 999)), date_key(r.get('entry_date'))))
    all_contracts.sort(key=lambda r: date_key(r.get('entry_date')), reverse=True)
    report = {
        'engine': ENGINE,
        'run_at': datetime.now().isoformat(timespec='seconds'),
        'scanned_symbols': scanned,
        'latest_market_date': latest_date,
        'all_contract_candidates': len(all_contracts),
        'recent_active_candidates': len(recent_contracts),
        'recent_window_bars': RECENT_BARS,
        'field_audit_recent': field_audit(recent_contracts),
        'field_audit_all': field_audit(all_contracts),
        't1_entry_guard_violations_recent': sum(1 for r in recent_contracts if date_key(r.get('pick_date')) == date_key(r.get('join_date'))),
        'by_gate_recent': bucket(recent_contracts, lambda r: r.get('v91_gate_reason')),
        'by_market_state_recent': bucket(recent_contracts, lambda r: r.get('market_state')),
        'by_recovery_substate_recent': bucket(recent_contracts, lambda r: r.get('v90_recovery_substate')),
        'reject_counts': dict(reject_counts),
    }
    (OUT / 'v91_all_contract_candidates.json').write_text(json.dumps(all_contracts, ensure_ascii=False, indent=2))
    (OUT / 'v91_active_picks.json').write_text(json.dumps(recent_contracts, ensure_ascii=False, indent=2))
    (OUT / 'v91_shadow_scan_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    with (OUT / 'v91_active_picks.csv').open('w', newline='') as fp:
        fields = sorted({k for r in recent_contracts for k in r.keys()}) if recent_contracts else []
        writer = csv.DictWriter(fp, fieldnames=fields, extrasaction='ignore')
        if fields:
            writer.writeheader(); writer.writerows(recent_contracts)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
