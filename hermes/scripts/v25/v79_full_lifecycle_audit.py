#!/usr/bin/env python3
"""V79 full-candidate lifecycle audit.

This is not a production promotion script. It backfills the SMC lifecycle model
onto the full V71/V73 candidate layer (9,931 trades), so we can see whether the
candidate actually follows:
trend regime -> liquidity/BOS/CHOCH/MSS event -> demand POI -> valid entry ->
semantic exit/invalidation.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from v78_smc_lifecycle_state_machine import (
    classify_trend_regime,
    detect_smc_lifecycle_event,
    locate_demand_poi,
    evaluate_entry_location,
    classify_exit_semantics,
    f,
)
from v74_environment_state_machine import add_env_slopes, classify_market_env, classify_setup_story as classify_v74_setup_story, passes_v74_core_gate
from v77_recovery_quality_state_machine import (
    attach_v76_env_fields,
    enrich_stock_pre_entry_features,
    classify_recovery_quality,
    passes_v77_gate,
)
from v78_hysteresis_recovery_trend_gate import passes_v78_gate, reject_reason, simulate_env_exit

BASE_DIR = Path('/root/.hermes')
KLINE_DIR = BASE_DIR / 'kline_cache'
V73_DIR = BASE_DIR / 'smc_opt_v73_structural_env'
V74_DIR = BASE_DIR / 'smc_opt_v74_env_state_machine'
OUT_DIR = BASE_DIR / 'smc_opt_v79_full_lifecycle_audit'
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path: Path):
    return json.loads(path.read_text())


def symbol_to_kline_path(symbol: str) -> Path:
    code, ex = symbol.split('.')
    p750 = KLINE_DIR / f'{code}_{ex}_daily_750.json'
    if p750.exists():
        return p750
    return KLINE_DIR / f'{code}_{ex}_daily_300.json'


def get_date(row: Dict[str, Any]) -> str:
    return str(row.get('entry_date') or row.get('pick_date') or row.get('select_date') or '')[:8]


def metrics(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rs = list(rows)
    if not rs:
        return {'n': 0, 'wr': 0, 'avg_pnl': 0, 'sl_rate': 0, 'env_exit_rate': 0, 'cum': 0}
    wins = [r for r in rs if f(r.get('pnl_pct')) > 0]
    sl = [r for r in rs if r.get('exit_reason') == 'SL_HIT']
    env = [r for r in rs if r.get('exit_reason') == 'ENV_RISK_EXIT']
    return {
        'n': len(rs),
        'wr': round(len(wins) / len(rs) * 100, 2),
        'avg_pnl': round(sum(f(r.get('pnl_pct')) for r in rs) / len(rs), 4),
        'sl_rate': round(len(sl) / len(rs) * 100, 2),
        'env_exit_rate': round(len(env) / len(rs) * 100, 2),
        'cum': round(sum(f(r.get('pnl_pct')) for r in rs), 2),
    }


def bucket(rows: Iterable[Dict[str, Any]], key) -> Dict[str, Any]:
    g = defaultdict(list)
    for r in rows:
        g[str(key(r))].append(r)
    return {k: metrics(v) for k, v in sorted(g.items())}


def annotate_env_and_v74(rows: List[Dict[str, Any]], env_by_date: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        nr = dict(r)
        dt = get_date(nr)
        er = env_by_date.get(dt, {})
        nr['market_state_v74'] = er.get('market_state_v74') or classify_market_env(nr)
        nr['market_bear_slope20'] = er.get('bear_slope20', nr.get('market_bear_slope20', 0))
        nr['market_range_slope20'] = er.get('range_slope20', nr.get('market_range_slope20', 0))
        nr['setup_story_v74'] = classify_v74_setup_story(nr)
        nr['v74_core_gate'] = passes_v74_core_gate(nr)
        out.append(nr)
    return out


def lifecycle_for_trade(trade: Dict[str, Any], ks: List[Dict[str, Any]]) -> Dict[str, Any]:
    confirm_idx = int(trade.get('confirm_bar') or trade.get('reaction_idx') or trade.get('entry_idx') or 0)
    entry_idx = int(trade.get('entry_idx') or confirm_idx)
    zone_low = f(trade.get('zone_low'))
    zone_high = f(trade.get('zone_high'))
    trend_idx = max(0, min(confirm_idx - 1, len(ks) - 1))
    event_idx = max(0, min(confirm_idx, len(ks) - 1))
    entry_idx = max(0, min(entry_idx, len(ks) - 1))

    trend = classify_trend_regime(ks, trend_idx)
    event = detect_smc_lifecycle_event(ks, event_idx, trend)
    poi = locate_demand_poi(ks, event)
    entry = evaluate_entry_location(ks, poi, event.get('event_idx', event_idx) + 1, max(entry_idx, event_idx))

    original_poi = {
        'zone_low': zone_low,
        'zone_high': zone_high,
        'prior_hl': f(trade.get('prior_hl') or trade.get('swing_low') or zone_low),
        'bsl_target': f(trade.get('tp1') or trade.get('bsl_target')),
    }
    exit_sem = classify_exit_semantics(ks[: max(int(trade.get('exit_idx') or entry_idx), entry_idx) + 1], original_poi, entry_idx)

    poi_match = False
    if poi.get('valid') and zone_low and zone_high:
        inter_low = max(zone_low, f(poi.get('zone_low')))
        inter_high = min(zone_high, f(poi.get('zone_high')))
        overlap = max(0.0, inter_high - inter_low)
        denom = max(zone_high - zone_low, f(poi.get('zone_high')) - f(poi.get('zone_low')), 1e-9)
        poi_match = overlap / denom >= 0.35

    lifecycle_valid = (
        trend.get('regime') in {'UP_CONTINUATION', 'DOWN_REVERSAL_REQUIRED', 'RECOVERY_TRANSITION', 'RANGE_TRANSITION'}
        and event.get('event_type') in {'BOS_CONTINUATION', 'SSL_SWEEP_CHOCH_REVERSAL'}
        and poi.get('valid')
        and poi_match
        and entry.get('entry_valid')
    )
    if not lifecycle_valid:
        reasons = []
        if event.get('event_type') not in {'BOS_CONTINUATION', 'SSL_SWEEP_CHOCH_REVERSAL'}:
            reasons.append('NO_LIFECYCLE_EVENT')
        if not poi.get('valid'):
            reasons.append('NO_LIFECYCLE_POI')
        if poi.get('valid') and not poi_match:
            reasons.append('POI_NOT_MATCH_ORIGINAL_ZONE')
        if not entry.get('entry_valid'):
            reasons.append('NO_LIFECYCLE_ENTRY_RECLAIM')
    else:
        reasons = ['PASS']
    return {
        'v79_trend_regime': trend.get('regime'),
        'v79_trend_reason': trend.get('reason'),
        'v79_event_type': event.get('event_type'),
        'v79_event_idx': event.get('event_idx'),
        'v79_poi_type': poi.get('poi_type'),
        'v79_poi_zone_low': poi.get('zone_low'),
        'v79_poi_zone_high': poi.get('zone_high'),
        'v79_poi_match_original': poi_match,
        'v79_entry_valid': entry.get('entry_valid'),
        'v79_entry_type': entry.get('entry_type'),
        'v79_entry_story': entry.get('entry_story'),
        'v79_exit_semantics': exit_sem.get('exit_signal'),
        'v79_lifecycle_valid': lifecycle_valid,
        'v79_reject_reason': '+'.join(reasons),
    }


def main() -> None:
    trades = load_json(V73_DIR / 'v73_annotated_trades.json')
    env = add_env_slopes(load_json(V73_DIR / 'v73_env_by_date.json'))
    v74_selected_symbols = {(r['symbol'], str(r.get('entry_date'))[:8], int(r.get('entry_idx') or -1)) for r in load_json(V74_DIR / 'v74_selected_trades.json')}

    rows = annotate_env_and_v74(trades, env)
    attach_v76_env_fields(rows)
    enrich_stock_pre_entry_features(rows)
    for r in rows:
        r['v77_recovery_quality'] = classify_recovery_quality(r)

    kcache: Dict[str, List[Dict[str, Any]]] = {}
    annotated = []
    missing_kline = 0
    for i, r in enumerate(rows, 1):
        sym = r.get('symbol')
        key = (sym, str(r.get('entry_date'))[:8], int(r.get('entry_idx') or -1))
        nr = dict(r)
        nr['v74_selected_key_match'] = key in v74_selected_symbols
        if sym not in kcache:
            path = symbol_to_kline_path(sym)
            if path.exists():
                kcache[sym] = load_json(path)
            else:
                kcache[sym] = []
        ks = kcache[sym]
        if not ks:
            missing_kline += 1
            nr.update({'v79_lifecycle_valid': False, 'v79_reject_reason': 'MISSING_KLINE'})
        else:
            nr.update(lifecycle_for_trade(nr, ks))
        # Re-evaluate V77/V78 gates on the full candidate layer after adding V77 fields.
        nr['v77_full_gate'] = passes_v77_gate(nr)
        nr['v78_full_gate'] = passes_v78_gate(nr)
        nr['v78_reject_reason'] = reject_reason(nr)
        nr['v79_full_gate'] = bool(nr.get('v79_lifecycle_valid') and nr.get('v78_full_gate'))
        # V79 production-candidate gate: lifecycle semantics first, then V74
        # environment/story, then V78-style hysteresis with slightly wider
        # bull breadth to avoid the V78 over-filtering that erased 2024.
        nr['v79_candidate_gate'] = bool(
            nr.get('v79_lifecycle_valid')
            and nr.get('v74_core_gate')
            and f(nr.get('risk_pct'), 999) <= 5.5
            and f(nr.get('v76_prior5_distribution_days'), 99) == 0
            and f(nr.get('v76_prior10_distribution_days'), 99) <= 3
            and f(nr.get('v76_prior10_demand_valid_days'), 0) >= 1
            and f(nr.get('market_bull_breadth'), 0) <= 0.55
            and bool(nr.get('v77_hl_improving'))
        )
        annotated.append(nr)

    v79_selected = [r for r in annotated if r.get('v79_candidate_gate')]
    v79_sim = []
    for r in v79_selected:
        ks = kcache.get(r.get('symbol')) or []
        sim = simulate_env_exit(r, ks, env)
        sim['pnl_pct'] = sim.get('v78_pnl_pct', sim.get('pnl_pct'))
        sim['exit_reason'] = sim.get('v78_exit_reason', sim.get('exit_reason'))
        sim['exit_date'] = sim.get('v78_exit_date', sim.get('exit_date'))
        sim['exit_price'] = sim.get('v78_exit_price', sim.get('exit_price'))
        v79_sim.append(sim)

    report = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'engine': 'V79_FULL_CANDIDATE_LIFECYCLE_AUDIT',
        'scope': 'Full V71/V73 candidate layer, not V74-selected subset',
        'base_candidates': metrics(annotated),
        'v74_selected_key_match': metrics([r for r in annotated if r.get('v74_selected_key_match')]),
        'v77_full_gate': metrics([r for r in annotated if r.get('v77_full_gate')]),
        'v78_full_gate': metrics([r for r in annotated if r.get('v78_full_gate')]),
        'v79_lifecycle_valid': metrics([r for r in annotated if r.get('v79_lifecycle_valid')]),
        'v79_full_gate_original_exit': metrics(v79_selected),
        'v79_full_gate_env_exit': metrics(v79_sim),
        'v79_candidate_gate_original_exit': metrics(v79_selected),
        'v79_candidate_gate_env_exit': metrics(v79_sim),
        'missing_kline': missing_kline,
        'buckets': {
            'v79_reject_reason': bucket(annotated, lambda r: r.get('v79_reject_reason')),
            'v79_trend_regime': bucket(annotated, lambda r: r.get('v79_trend_regime')),
            'v79_event_type': bucket(annotated, lambda r: r.get('v79_event_type')),
            'v79_entry_story': bucket(annotated, lambda r: r.get('v79_entry_story')),
            'v79_exit_semantics': bucket(annotated, lambda r: r.get('v79_exit_semantics')),
            'v79_full_gate_year_env_exit': bucket(v79_sim, lambda r: str(r.get('entry_date',''))[:4]),
            'v79_full_gate_story_env_exit': bucket(v79_sim, lambda r: r.get('v79_entry_story')),
            'v79_full_gate_exit_env_exit': bucket(v79_sim, lambda r: r.get('exit_reason')),
            'v78_reject_reason': bucket(annotated, lambda r: r.get('v78_reject_reason')),
        },
        'files': {
            'annotated': str(OUT_DIR / 'v79_annotated_trades.json'),
            'selected': str(OUT_DIR / 'v79_selected_trades.json'),
            'simulated': str(OUT_DIR / 'v79_simulated_trades.json'),
            'report': str(OUT_DIR / 'v79_report.json'),
            'markdown': str(OUT_DIR / 'v79_report.md'),
        },
    }

    (OUT_DIR / 'v79_annotated_trades.json').write_text(json.dumps(annotated, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v79_selected_trades.json').write_text(json.dumps(v79_selected, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v79_simulated_trades.json').write_text(json.dumps(v79_sim, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v79_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))

    md = []
    md.append('# V79 全量候选层 SMC 生命周期审计\n')
    md.append('范围：V71/V73全量候选层 9,931 笔，不再只筛 V74 的 850 笔子集。\n')
    md.append('| 项目 | n | WR | avg | SL | ENV_EXIT | cum |\n|---|---:|---:|---:|---:|---:|---:|')
    for name in ['base_candidates','v74_selected_key_match','v77_full_gate','v78_full_gate','v79_lifecycle_valid','v79_candidate_gate_original_exit','v79_candidate_gate_env_exit']:
        m = report[name]
        md.append(f"| {name} | {m['n']} | {m['wr']}% | {m['avg_pnl']}% | {m['sl_rate']}% | {m['env_exit_rate']}% | {m['cum']} |")
    md.append('\n## V79全门禁+环境退出 分年\n')
    md.append('| 年份 | n | WR | avg | SL | ENV_EXIT | cum |\n|---|---:|---:|---:|---:|---:|---:|')
    for y, m in report['buckets']['v79_full_gate_year_env_exit'].items():
        md.append(f"| {y} | {m['n']} | {m['wr']}% | {m['avg_pnl']}% | {m['sl_rate']}% | {m['env_exit_rate']}% | {m['cum']} |")
    md.append('\n## 生命周期拒绝桶\n')
    md.append('| 拒绝原因 | n | WR | avg | SL | cum |\n|---|---:|---:|---:|---:|---:|')
    for k, m in sorted(report['buckets']['v79_reject_reason'].items(), key=lambda kv: -kv[1]['n'])[:20]:
        md.append(f"| {k} | {m['n']} | {m['wr']}% | {m['avg_pnl']}% | {m['sl_rate']}% | {m['cum']} |")
    (OUT_DIR / 'v79_report.md').write_text('\n'.join(md))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
