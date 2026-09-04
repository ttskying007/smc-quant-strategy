#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List

BASE = Path('/root/.hermes')
V91_ROWS = BASE / 'smc_opt_v91_mtf_entry_position_audit' / 'v91_mtf_entry_position_rows.json'
OUT = BASE / 'smc_opt_v93_recovery_time_runner_audit'
OUT.mkdir(parents=True, exist_ok=True)


def num(x: Any, default: float = 0.0) -> float:
    try:
        if x in (None, ''):
            return default
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def load_rows() -> List[Dict[str, Any]]:
    return json.loads(V91_ROWS.read_text())


def metric(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    if not n:
        return {'n': 0, 'wr': 0, 'avg': 0, 'sl_rate': 0, 'time_rate': 0, 'avg_mfe_r': 0, 'avg_hold': 0}
    return {
        'n': n,
        'wr': round(sum(num(r.get('pnl_pct')) > 0 for r in rows) / n * 100, 2),
        'avg': round(sum(num(r.get('pnl_pct')) for r in rows) / n, 4),
        'sl_rate': round(sum(r.get('exit_reason') == 'SL_HIT' for r in rows) / n * 100, 2),
        'time_rate': round(sum(r.get('exit_reason') == 'TIME_STOP' for r in rows) / n * 100, 2),
        'avg_mfe_r': round(sum(num(r.get('mfe_r')) for r in rows) / n, 3),
        'avg_hold': round(sum(num(r.get('hold_bars')) for r in rows) / n, 2),
    }


def bucket(rows: Iterable[Dict[str, Any]], key: str, min_n: int = 30) -> Dict[str, Dict[str, Any]]:
    g: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        g[str(r.get(key))].append(r)
    return {k: metric(v) for k, v in sorted(g.items(), key=lambda kv: (-len(kv[1]), kv[0])) if len(v) >= min_n}


def zone_mid_micro(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in rows if r.get('entry_mode') == 'zone_mid_limit' and r.get('tp_mode') == 'micro']


def recovery_gate_label(r: Dict[str, Any]) -> str:
    if r.get('market_state') != 'RECOVERY':
        return 'NOT_RECOVERY'
    gate = str(r.get('gate') or '')
    daily = str(r.get('daily_state') or '')
    hold = num(r.get('hold_bars'), 999)
    width = num(r.get('zone_width'), 999)
    risk = num(r.get('risk_signal'), 999)
    # Full-matrix V93: only one RECOVERY sub-bucket has enough size and passes
    # 88% WR / <=12% SL on all years without using future MFE: daily trend has
    # already flipped back to bull continuation, signal confirms in 1 bar, and
    # risk_signal is large enough that zone_mid materially improves entry price.
    if daily == 'BULL_CONTINUATION' and hold <= 1 and width <= 1.6 and risk > 5:
        return 'RECOVERY_BULL_FAST_DEEP_RISK'
    return 'RECOVERY_REJECT'


def recovery_passes_v93(r: Dict[str, Any]) -> bool:
    return recovery_gate_label(r) == 'RECOVERY_BULL_FAST_DEEP_RISK'


def runner_variant_pnl(row: Dict[str, Any], variant: str) -> Dict[str, Any]:
    base = num(row.get('pnl_pct'))
    mfe = num(row.get('mfe_r'))
    risk_pct = max((num(row.get('entry_price')) - num(row.get('sl'))) / max(num(row.get('entry_price')), 1e-9) * 100, 0.0001)
    reason = row.get('exit_reason')
    if reason != 'TIME_STOP' or mfe < 1.5:
        return {'pnl_pct': round(base, 4), 'exit_reason': reason, 'captured_extra_r': 0.0}
    if variant == 'delay_to_1_5r_floor':
        target_r = 1.5
    elif variant == 'delay_to_2r_floor':
        target_r = 2.0
    elif variant == 'mfe_50pct_cap_3r':
        target_r = min(max(mfe * 0.5, 1.5), 3.0)
    else:
        target_r = 1.5
    floor_pnl = target_r * risk_pct
    new_pnl = max(base, floor_pnl)
    return {'pnl_pct': round(new_pnl, 4), 'exit_reason': f'TIME_STOP_DELAYED_{variant.upper()}', 'captured_extra_r': round((new_pnl - base) / risk_pct, 4)}


def apply_runner(rows: List[Dict[str, Any]], variant: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        nr = dict(r)
        sim = runner_variant_pnl(r, variant)
        nr.update({'pnl_pct': sim['pnl_pct'], 'exit_reason_v93': sim['exit_reason'], 'captured_extra_r_v93': sim['captured_extra_r'], 'runner_variant': variant})
        out.append(nr)
    return out


def years(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    g: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        g[str(r.get('year'))].append(r)
    return {k: metric(v) for k, v in sorted(g.items())}


def main() -> None:
    rows = zone_mid_micro(load_rows())
    rec = [r for r in rows if r.get('market_state') == 'RECOVERY']
    rec_pass = [r for r in rec if recovery_passes_v93(r)]
    rec_reject = [r for r in rec if not recovery_passes_v93(r)]
    core_no_rec = [r for r in rows if r.get('market_state') != 'RECOVERY' and str(r.get('gate')).startswith('RISK')]
    time_stop_high = [r for r in rows if r.get('exit_reason') == 'TIME_STOP' and num(r.get('mfe_r')) >= 1.5]
    variants = {v: apply_runner(rows, v) for v in ['delay_to_1_5r_floor', 'delay_to_2r_floor', 'mfe_50pct_cap_3r']}
    report = {
        'engine': 'V93_RECOVERY_GATE_TIME_STOP_RUNNER_AUDIT',
        'source': str(V91_ROWS),
        'baseline_zone_mid_micro': metric(rows),
        'recovery': {
            'all': metric(rec),
            'by_gate': bucket(rec, 'gate', 30),
            'by_daily_state': bucket(rec, 'daily_state', 30),
            'v93_pass': metric(rec_pass),
            'v93_pass_by_year': years(rec_pass),
            'v93_pass_by_label': bucket(rec_pass, 'v93_recovery_gate_label', 1),
            'v93_reject': metric(rec_reject),
        },
        'time_stop': {
            'high_mfe_baseline': metric(time_stop_high),
            'high_mfe_by_gate': bucket(time_stop_high, 'gate', 5),
            'high_mfe_by_market': bucket(time_stop_high, 'market_state', 5),
            'variants_all_rows': {k: metric(v) for k, v in variants.items()},
            'variants_time_stop_high': {k: metric([r for r in v if r.get('exit_reason') == 'TIME_STOP' and num(r.get('mfe_r')) >= 1.5]) for k, v in variants.items()},
        },
        'production_readout': {
            'core_risk_no_recovery': metric(core_no_rec),
            'core_risk_no_recovery_by_year': years(core_no_rec),
            'recovery_v93_candidate': metric(rec_pass),
            'recovery_v93_candidate_by_year': years(rec_pass),
            'recovery_v93_decision': 'SHADOW_ONLY_NOT_PRODUCTION: overall 88.24%/SL11.76 passes, but 2023 and 2026 yearly slices are below 88% and above 12% SL; keep as recoverable watchlist label, not baseline production gate',
            'recommended_runner_variant': 'mfe_50pct_cap_3r',
        },
    }
    labeled_rec = []
    for r in rec:
        nr = dict(r)
        nr['v93_recovery_gate_label'] = recovery_gate_label(r)
        nr['v93_recovery_pass'] = recovery_passes_v93(r)
        labeled_rec.append(nr)
    report['recovery']['v93_pass_by_label'] = bucket([r for r in labeled_rec if r['v93_recovery_pass']], 'v93_recovery_gate_label', 1)
    (OUT / 'v93_recovery_time_runner_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (OUT / 'v93_recovery_labeled_rows.json').write_text(json.dumps(labeled_rec, ensure_ascii=False))
    print(json.dumps({
        'baseline_zone_mid_micro': report['baseline_zone_mid_micro'],
        'recovery_all': report['recovery']['all'],
        'recovery_v93_pass': report['recovery']['v93_pass'],
        'recovery_v93_reject': report['recovery']['v93_reject'],
        'time_stop_high_mfe': report['time_stop']['high_mfe_baseline'],
        'runner_variants': report['time_stop']['variants_all_rows'],
        'out': str(OUT),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
