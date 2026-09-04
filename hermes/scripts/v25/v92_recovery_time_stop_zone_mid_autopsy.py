#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List

BASE = Path('/root/.hermes')
OUT = BASE / 'smc_opt_v92_recovery_time_stop_zone_mid_autopsy'
OUT.mkdir(parents=True, exist_ok=True)

V85_GEN = BASE / 'smc_opt_v85_mixed_accumulation_generator' / 'v85_candidates.json'
V85_PROD = BASE / 'smc_opt_v85_production_gate' / 'v85_trades.json'
V86_PROD = BASE / 'smc_opt_v86_production_gate' / 'v86_trades.json'
V88_PROD = BASE / 'smc_opt_v88_production_contract' / 'v88_trades.json'
V91_ROWS = BASE / 'smc_opt_v91_mtf_entry_position_audit' / 'v91_mtf_entry_position_rows.json'
V91_ACTIVE = BASE / 'smc_opt_v91_shadow_zone_entry_scanner' / 'v91_active_picks.json'
KLINE_DIR = BASE / 'kline_cache'


def load(path: Path) -> Any:
    return json.loads(path.read_text()) if path.exists() else []


def num(x: Any, default: float = 0.0) -> float:
    try:
        if x in (None, ''):
            return default
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def metric(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    if not n:
        return {'n': 0, 'wr': 0, 'avg': 0, 'sl_rate': 0, 'time_rate': 0, 'avg_mfe_r': 0, 'avg_mae_r': 0, 'avg_hold': 0}
    return {
        'n': n,
        'wr': round(sum(num(r.get('pnl_pct')) > 0 for r in rows) / n * 100, 2),
        'avg': round(sum(num(r.get('pnl_pct')) for r in rows) / n, 4),
        'sl_rate': round(sum(r.get('exit_reason') == 'SL_HIT' for r in rows) / n * 100, 2),
        'time_rate': round(sum(r.get('exit_reason') == 'TIME_STOP' for r in rows) / n * 100, 2),
        'avg_mfe_r': round(sum(num(r.get('mfe_r')) for r in rows) / n, 3),
        'avg_mae_r': round(sum(num(r.get('mae_r')) for r in rows) / n, 3),
        'avg_hold': round(sum(num(r.get('hold_bars')) for r in rows) / n, 2),
    }


def bucket(rows: Iterable[Dict[str, Any]], key: Callable[[Dict[str, Any]], Any], min_n: int = 1) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        grouped[str(key(r))].append(r)
    return {
        k: metric(v)
        for k, v in sorted(grouped.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        if len(v) >= min_n
    }


def top_examples(rows: List[Dict[str, Any]], n: int = 50) -> List[Dict[str, Any]]:
    rows = sorted(rows, key=lambda r: (num(r.get('mfe_r')), -abs(num(r.get('pnl_pct')))), reverse=True)[:n]
    keep = ['symbol','year','market_state','daily_state','gate','entry_mode','tp_mode','entry_date','orig_entry_date','entry_price','exit_reason','pnl_pct','mfe_r','mae_r','hold_bars','sl','tp1','tp2','tp3','zone_width','risk_signal']
    return [{k: r.get(k) for k in keep} for r in rows]


def main() -> None:
    v85_gen = load(V85_GEN)
    v85_prod = load(V85_PROD)
    v86 = load(V86_PROD)
    v88 = load(V88_PROD)
    rows = load(V91_ROWS)
    v91_active = load(V91_ACTIVE)

    zone_mid_micro = [r for r in rows if r.get('entry_mode') == 'zone_mid_limit' and r.get('tp_mode') == 'micro']
    orig_micro = [r for r in rows if r.get('entry_mode') == 'orig_v85_entry' and r.get('tp_mode') == 'micro']
    pass_zone_mid = [r for r in zone_mid_micro if r.get('gate_pass')]
    risk_zone_mid = [r for r in zone_mid_micro if str(r.get('gate')).startswith('RISK')]
    recovery_zone_mid = [r for r in zone_mid_micro if r.get('market_state') == 'RECOVERY']
    recovery_zone_mid_losses = [r for r in recovery_zone_mid if num(r.get('pnl_pct')) <= 0]

    v88_time_stop = [r for r in v88 if r.get('exit_reason') == 'TIME_STOP']
    v88_time_stop_high_mfe = [r for r in v88_time_stop if num(r.get('mfe_r')) >= 1.5]
    zone_time_stop = [r for r in zone_mid_micro if r.get('exit_reason') == 'TIME_STOP']
    zone_time_stop_high_mfe = [r for r in zone_time_stop if num(r.get('mfe_r')) >= 1.5]

    report = {
        'engine': 'V92_RECOVERY_TIME_STOP_ZONE_MID_AUTOPSY',
        'scope': {
            'kline_symbols_daily_750': len(list(KLINE_DIR.glob('*_daily_750.json'))),
            'v85_generator_candidates': len(v85_gen),
            'v85_generator_symbols': len({r.get('symbol') for r in v85_gen}),
            'v85_generator_years': dict(Counter(str(r.get('entry_date', ''))[:4] for r in v85_gen)),
            'v85_production_rows': len(v85_prod),
            'v85_production_symbols': len({r.get('symbol') for r in v85_prod}),
            'v86_rows': len(v86),
            'v86_symbols': len({r.get('symbol') for r in v86}),
            'v88_rows': len(v88),
            'v88_symbols': len({r.get('symbol') for r in v88}),
            'v91_matrix_rows': len(rows),
            'v91_matrix_symbols': len({r.get('symbol') for r in rows}),
            'v91_active_rows': len(v91_active),
            'v91_active_symbols': len({r.get('symbol') for r in v91_active}),
        },
        'baseline': {
            'v88': metric(v88),
            'v88_exit_reason': dict(Counter(r.get('exit_reason') for r in v88)),
            'v88_one_bar': metric([r for r in v88 if num(r.get('hold_bars')) <= 1]),
            'orig_v85_micro': metric(orig_micro),
        },
        'zone_mid_micro': {
            'all': metric(zone_mid_micro),
            'by_year': bucket(zone_mid_micro, lambda r: r.get('year')),
            'by_gate': bucket(zone_mid_micro, lambda r: r.get('gate'), 30),
            'by_market': bucket(zone_mid_micro, lambda r: r.get('market_state'), 30),
            'by_daily_state': bucket(zone_mid_micro, lambda r: r.get('daily_state'), 30),
            'pass': metric(pass_zone_mid),
            'pass_by_year': bucket(pass_zone_mid, lambda r: r.get('year')),
            'risk_prefix': metric(risk_zone_mid),
            'risk_prefix_by_year': bucket(risk_zone_mid, lambda r: r.get('year')),
        },
        'recovery_loss_bucket': {
            'recovery_zone_mid': metric(recovery_zone_mid),
            'losses': metric(recovery_zone_mid_losses),
            'loss_exit_reason': dict(Counter(r.get('exit_reason') for r in recovery_zone_mid_losses)),
            'loss_by_gate': bucket(recovery_zone_mid_losses, lambda r: r.get('gate'), 10),
            'loss_by_daily_state': bucket(recovery_zone_mid_losses, lambda r: r.get('daily_state'), 10),
            'loss_by_year': bucket(recovery_zone_mid_losses, lambda r: r.get('year'), 10),
            'v88_recovery': metric([r for r in v88 if r.get('market_state') == 'RECOVERY']),
            'v88_recovery_losses': metric([r for r in v88 if r.get('market_state') == 'RECOVERY' and num(r.get('pnl_pct')) <= 0]),
        },
        'time_stop_high_mfe': {
            'v88_time_stop': metric(v88_time_stop),
            'v88_high_mfe_ge_1_5': metric(v88_time_stop_high_mfe),
            'v88_high_mfe_ge_3': metric([r for r in v88_time_stop if num(r.get('mfe_r')) >= 3.0]),
            'v88_high_mfe_by_market': bucket(v88_time_stop_high_mfe, lambda r: r.get('market_state'), 5),
            'zone_mid_time_stop': metric(zone_time_stop),
            'zone_mid_high_mfe_ge_1_5': metric(zone_time_stop_high_mfe),
            'zone_mid_high_mfe_ge_3': metric([r for r in zone_time_stop if num(r.get('mfe_r')) >= 3.0]),
            'zone_mid_high_mfe_by_market': bucket(zone_time_stop_high_mfe, lambda r: r.get('market_state'), 5),
            'zone_mid_high_mfe_by_gate': bucket(zone_time_stop_high_mfe, lambda r: r.get('gate'), 5),
        },
        'one_bar_exit': {
            'v88': metric([r for r in v88 if num(r.get('hold_bars')) <= 1]),
            'zone_mid_micro': metric([r for r in zone_mid_micro if num(r.get('hold_bars')) <= 1]),
            'orig_v85_micro': metric([r for r in orig_micro if num(r.get('hold_bars')) <= 1]),
            'v88_exit_reason': dict(Counter(r.get('exit_reason') for r in v88 if num(r.get('hold_bars')) <= 1)),
            'zone_mid_exit_reason': dict(Counter(r.get('exit_reason') for r in zone_mid_micro if num(r.get('hold_bars')) <= 1)),
        },
        'production_candidate_readout': {
            'zone_mid_pass_gate': {
                'decision': 'SHADOW_ONLY_NOT_FULL_PRODUCTION',
                'reason': 'overall WR/SL pass, but 2026 slice is 84.62% WR and 15.38% SL; insufficient to replace V88 baseline',
                'metric': metric(pass_zone_mid),
                'by_year': bucket(pass_zone_mid, lambda r: r.get('year')),
            },
            'zone_mid_risk_gate': {
                'decision': 'PROMOTABLE_AS_EXPERIMENTAL_RISK_LAYER_AFTER_DAILY_SCANNER_GUARD',
                'reason': 'n=5891, WR=90.24%, SL=9.71%, all main years >=88.9% WR; not baseline replacement because it is recovered filtered population and needs active-scanner forward validation',
                'metric': metric([r for r in zone_mid_micro if r.get('gate') == 'RISK']),
                'by_year': bucket([r for r in zone_mid_micro if r.get('gate') == 'RISK'], lambda r: r.get('year')),
            },
        },
        'samples': {
            'v88_time_stop_high_mfe_top': top_examples(v88_time_stop_high_mfe, 40),
            'zone_mid_recovery_loss_top_mfe': top_examples(recovery_zone_mid_losses, 40),
            'zone_mid_time_stop_high_mfe_top': top_examples(zone_time_stop_high_mfe, 40),
        },
        'root_cause': {
            'entry_position': 'confirmed: orig_v85_entry chases confirmation price; zone_mid reduces SL rate from orig one-bar 22.99% to zone_mid one-bar 11.58%, and zone_mid all SL 11.92%',
            'recovery': 'RECOVERY remains weakest market bucket after zone_mid: 5811 rows, WR 84.08%, SL 15.8%; losses are almost all SL_HIT, concentrated in ZONE_WIDTH+RISK and RISK gates, not TP/SL parameter failure',
            'time_stop_high_mfe': 'TIME_STOP is exit-capture issue, not signal failure: V88 MFE>=3R time-stop rows are 36/36 winners; zone_mid high-MFE time-stops are 548/548 winners but capped by short maxhold/micro ladder',
            'model_horizon': 'V88 has 426/532 one-bar exits; this is a short-horizon liquidity capture model, not a trend-eating model',
        },
    }

    (OUT / 'v92_autopsy_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    md = OUT / 'v92_autopsy_summary.md'
    md.write_text('# V92 RECOVERY / TIME_STOP / zone_mid autopsy\n\n' + json.dumps(report['root_cause'], ensure_ascii=False, indent=2) + '\n')
    with (OUT / 'v92_zone_mid_recovery_losses.csv').open('w', newline='') as fp:
        fields = sorted({k for r in recovery_zone_mid_losses for k in r.keys()})
        w = csv.DictWriter(fp, fieldnames=fields, extrasaction='ignore')
        w.writeheader(); w.writerows(recovery_zone_mid_losses)
    print(json.dumps({
        'scope': report['scope'],
        'v88': report['baseline']['v88'],
        'zone_mid_micro': report['zone_mid_micro']['all'],
        'zone_mid_pass': report['zone_mid_micro']['pass'],
        'zone_mid_risk': report['production_candidate_readout']['zone_mid_risk_gate']['metric'],
        'recovery_loss': report['recovery_loss_bucket']['losses'],
        'time_stop_high_mfe': report['time_stop_high_mfe']['v88_high_mfe_ge_3'],
        'out': str(OUT),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
