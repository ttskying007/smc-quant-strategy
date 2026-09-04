#!/usr/bin/env python3
"""V72 layered SL-buffer tiers on expanded V64 source pool.

Keeps V66 as production base and publishes parallel tiers:
- Base: V64 source pool after V66 recent reentry risk overlay
- QualityA: Base with sl buffer >= 0.25%
- QualityB: Base with sl buffer >= 0.50%
- Strict: Base with sl buffer >= 0.75%
"""
from __future__ import annotations

import collections
import json
import pathlib
import statistics
from datetime import datetime

ROOT = pathlib.Path('/root/.hermes')
SRC = ROOT / 'smc_opt_v65' / 'v65_source_v64_trades.json'
OUT = ROOT / 'smc_opt_v72_layered'
OUT.mkdir(parents=True, exist_ok=True)


def f(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def load_json(path):
    try:
        return json.loads(pathlib.Path(path).read_text())
    except Exception:
        return []


def pass_v66_reentry_overlay(trade):
    reasons = []
    if trade.get('v59_setup_family') == 'REENTRY_SETUP':
        bq = f(trade.get('breakout_quality_score'))
        trend_ctx = (trade.get('breakout_quality_detail') or {}).get('trend_ctx') or {}
        near_high = f(trend_ctx.get('near_high_pct'))
        range_atr = f(trend_ctx.get('range_atr'))
        if bq < 60:
            reasons.append('REENTRY_BQ_LT_60')
        if near_high == 0 and range_atr >= 4.4:
            reasons.append('REENTRY_EXACT_HIGH_EXTENDED_RANGE')
    return reasons


def enrich(trade):
    row = dict(trade)
    entry = f(row.get('entry_price'))
    sl = f(row.get('sl'))
    zone_low = f(row.get('raw_zone_low') or row.get('zone_low'))
    zone_high = f(row.get('raw_zone_high') or row.get('zone_high'))
    row['sl_buffer_below_zone_pct'] = round((zone_low / sl - 1) * 100, 3) if zone_low and sl else 0
    row['entry_above_zone_high_pct'] = round((entry / zone_high - 1) * 100, 3) if entry and zone_high else 0
    row['v72_source_pool'] = 'V64_SOURCE_WITH_V66_REENTRY_OVERLAY'
    row['engine'] = 'V72_LAYERED_SL_BUFFER'
    row['definition_version'] = 'V72_LAYERED_SL_BUFFER'
    return row


def tier_for(row):
    slbuf = f(row.get('sl_buffer_below_zone_pct'))
    if slbuf >= 0.75:
        return 'Strict'
    if slbuf >= 0.50:
        return 'QualityB'
    if slbuf >= 0.25:
        return 'QualityA'
    return 'Base'


def metrics(rows):
    if not rows:
        return {'n': 0}
    pnl = [f(r.get('pnl_pct')) for r in rows]
    wins = [x for x in pnl if x > 0]
    losses = [-x for x in pnl if x <= 0]
    sl_count = sum(1 for r in rows if r.get('exit_reason') in ('SL_HIT', 'GAP_SL_HIT'))
    return {
        'n': len(rows),
        'wr': round(len(wins) / len(rows) * 100, 2),
        'sl_rate': round(sl_count / len(rows) * 100, 2),
        'sl_n': sl_count,
        'avg_pnl': round(statistics.mean(pnl), 3),
        'realized_rr': round((statistics.mean(wins) / statistics.mean(losses)) if wins and losses else 999, 3),
        'avg_hold_bars': round(statistics.mean([f(r.get('hold_bars')) for r in rows]), 2),
    }


def pick_from_trade(row):
    pick_date = row.get('entry_date') or row.get('signal_date') or ''
    zone_low = row.get('raw_zone_low') or row.get('zone_low')
    zone_high = row.get('raw_zone_high') or row.get('zone_high')
    return {
        'symbol': row.get('symbol'),
        'name': row.get('name', ''),
        'pick_date': pick_date,
        'select_date': pick_date,
        'join_date': pick_date,
        'entry_date': row.get('entry_date'),
        'signal_date': row.get('signal_date'),
        'price': row.get('entry_price'),
        'entry_price': row.get('entry_price'),
        'sl': row.get('sl'),
        'risk_pct': row.get('risk_pct'),
        'tp1': row.get('tp1_design_price_v59') or row.get('tp1'),
        'tp2': row.get('tp2_design_price_v59') or row.get('tp2'),
        'raw_zone_low': zone_low,
        'raw_zone_high': zone_high,
        'zone_low': zone_low,
        'zone_high': zone_high,
        'zone_type': row.get('zone_type') or row.get('signal_type') or row.get('v59_setup_family') or '',
        'signal_type': row.get('signal_type') or row.get('zone_type') or '',
        'conf_type': row.get('conf_type'),
        'v59_setup_family': row.get('v59_setup_family'),
        'quality_tier': row.get('v72_layer'),
        'v72_layer': row.get('v72_layer'),
        'sl_buffer_below_zone_pct': row.get('sl_buffer_below_zone_pct'),
        'entry_above_zone_high_pct': row.get('entry_above_zone_high_pct'),
        'smart_money_cost': row.get('smart_money_cost') or row.get('cost_line') or row.get('entry_price'),
        'cost_line': row.get('cost_line') or row.get('smart_money_cost') or row.get('entry_price'),
        'volatility_pct': row.get('volatility_pct') or row.get('atr_pct') or row.get('risk_pct'),
        'pnl_pct': row.get('pnl_pct'),
        'exit_reason': row.get('exit_reason'),
        'engine': 'V72_LAYERED_SL_BUFFER',
        'definition_version': 'V72_LAYERED_SL_BUFFER',
        'pick_scope': 'LAYERED_BACKTEST_CANDIDATE',
        'is_active_pick': False,
        'score': row.get('breakout_quality_score'),
    }


def main():
    source = load_json(SRC)
    kept = []
    rejected = []
    for trade in source:
        reasons = pass_v66_reentry_overlay(trade)
        row = enrich(trade)
        row['v72_base_gate_reasons'] = reasons
        if reasons:
            row['reject_reason'] = ';'.join(reasons)
            row['pick_scope'] = 'REJECTED_V72_BASE_OVERLAY'
            rejected.append(row)
            continue
        row['v72_layer'] = tier_for(row)
        kept.append(row)

    layer_thresholds = {'Base': 0.0, 'QualityA': 0.25, 'QualityB': 0.50, 'Strict': 0.75}
    layer_sets = {
        name: [r for r in kept if f(r.get('sl_buffer_below_zone_pct')) >= threshold]
        for name, threshold in layer_thresholds.items()
    }
    picks = [pick_from_trade(r) for r in kept]
    report = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'engine': 'V72_LAYERED_SL_BUFFER',
        'source': str(SRC),
        'n_source': len(source),
        'n_base_after_v66_overlay': len(kept),
        'n_rejected_by_base_overlay': len(rejected),
        'layer_thresholds': layer_thresholds,
        'layers': {name: metrics(rows) for name, rows in layer_sets.items()},
        'base_metrics': metrics(kept),
        'family_counts': dict(collections.Counter(r.get('v59_setup_family') for r in kept)),
        'zone_counts': dict(collections.Counter(r.get('zone_type') for r in kept)),
        'conf_counts': dict(collections.Counter(r.get('conf_type') for r in kept)),
        'exit_counts': dict(collections.Counter(r.get('exit_reason') for r in kept)),
        'reject_counts': dict(collections.Counter(r.get('reject_reason') for r in rejected)),
        'verdict': 'parallel_candidate_only_do_not_replace_v66_production',
    }

    files = {
        'v72_trades.json': kept,
        'v72_rejected.json': rejected,
        'v72_picks.json': picks,
        'v72_report.json': report,
    }
    for name, data in files.items():
        (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
