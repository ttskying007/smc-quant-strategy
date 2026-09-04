#!/usr/bin/env python3
"""V524 no-write diagnostic: volume increment and frozen-ledger cost stress.

This does not alter V517's ontology, thresholds, execution, production, or
scanner.  It answers two bounded questions after V517-V523 promotion:
1) Holding the same price chronology fixed, is the pre-existing sweep-volume
   rank associated with a materially different fixed-contract outcome?
2) How much round-trip cost can the frozen V519 ledger absorb before any year
   loses positive average net PnL?

All rank bands are declared before outcomes are opened.  No band is promoted,
selected, or written to any production-facing artifact.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
KD = ROOT / 'kline_cache'
V517 = AUD / 'v517_daily_effort_result_absorption_seed_gate_latest.json'
V519 = AUD / 'v519_daily_effort_result_absorption_frozen_t1_replay_latest.json'
OUT = AUD / f'v524_effort_increment_cost_stress_audit_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v524_effort_increment_cost_stress_audit_latest.json'

LEFT = RIGHT = 3
SWEEP_PCT = 0.003
LOOKBACK = 20
STOP_BUFFER = 0.99
HOLD = 20
BASE_COST = 0.20
YEARS = ('2023', '2024', '2025', '2026')
# Frozen diagnostic partitions; neither thresholds nor execution are optimized.
BANDS = {
    'LOW_0_00_0_45': (0.00, 0.45),
    'MID_0_50_0_75': (0.50, 0.75),
    'HIGH_0_80_1_00': (0.80, 1.00),
}
COSTS = (0.20, 0.40, 0.60, 0.80, 1.00)


def positive(x: Any) -> float | None:
    try:
        y = float(x)
        return y if y > 0 else None
    except (TypeError, ValueError):
        return None


def date_key(x: Any) -> str:
    s = ''.join(c for c in str(x or '') if c.isdigit())
    return s[:8] if len(s) >= 8 else ''


def load_bars(symbol: str) -> list[dict[str, Any]]:
    code, exchange = symbol.split('.')
    try:
        raw = json.loads((KD / f'{code}_{exchange}_daily_750.json').read_text())
    except Exception:
        return []
    rows = []
    for r in raw if isinstance(raw, list) else []:
        d = date_key(r.get('t') or r.get('date') or r.get('day'))
        o, h, l, c, v = (positive(r.get(k)) for k in ('o', 'h', 'l', 'c', 'v'))
        if d and None not in (o, h, l, c, v):
            rows.append({'d': d, 'o': o, 'h': h, 'l': l, 'c': c, 'v': v})
    return sorted(rows, key=lambda x: x['d'])


def low_pivot(bars: list[dict[str, Any]], j: int) -> bool:
    if j < LEFT or j + RIGHT >= len(bars):
        return False
    return (bars[j]['l'] < min(bars[k]['l'] for k in range(j - LEFT, j))
            and bars[j]['l'] <= min(bars[k]['l'] for k in range(j + 1, j + RIGHT + 1)))


def high_pivot(bars: list[dict[str, Any]], j: int) -> bool:
    if j < LEFT or j + RIGHT >= len(bars):
        return False
    return (bars[j]['h'] > max(bars[k]['h'] for k in range(j - LEFT, j))
            and bars[j]['h'] >= max(bars[k]['h'] for k in range(j + 1, j + RIGHT + 1)))


def rank(prior: list[float], current: float) -> float:
    return sum(x <= current for x in prior) / len(prior) if prior else 0.0


def scan_price_chronology(symbol: str, bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Outcome-blind superset: V517 price chronology, without its high-volume gate."""
    rows = []
    for i in range(max(LOOKBACK, LEFT + RIGHT + 1), len(bars) - 2):
        swing_idx = i - RIGHT - 1
        if not low_pivot(bars, swing_idx):
            continue
        swing, sweep, response = bars[swing_idx], bars[i], bars[i + 1]
        sweep_low = sweep['l'] <= swing['l'] * (1.0 - SWEEP_PCT)
        reclaimed = sweep['c'] > swing['l']
        response_break = response['c'] > sweep['h']
        if not (sweep_low and reclaimed and response_break):
            continue
        volume_rank = rank([bars[k]['v'] for k in range(i - LOOKBACK, i)], sweep['v'])
        rows.append({
            'symbol': symbol, 'sweep_idx': i, 'sweep_date': sweep['d'],
            'sweep_low': sweep['l'], 'response_date': response['d'],
            'entry_idx': i + 2, 'entry_date': bars[i + 2]['d'],
            'prior20_volume_rank': round(volume_rank, 6),
        })
    return rows


def visible_target(bars: list[dict[str, Any]], sweep_idx: int, entry: float) -> tuple[int, float] | None:
    for j in range(sweep_idx - RIGHT - 1, LEFT - 1, -1):
        if high_pivot(bars, j) and bars[j]['h'] > entry:
            return j, bars[j]['h']
    return None


def pct(value: float, base: float) -> float:
    return 100 * (value / base - 1.0)


def execute(seed: dict[str, Any], bars: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str | None]:
    by_date = {bar['d']: index for index, bar in enumerate(bars)}
    entry_date, sweep_date = seed['entry_date'], seed['sweep_date']
    if entry_date not in by_date or sweep_date not in by_date:
        return None, 'SEED_DATE_NOT_IN_CACHE'
    i, sweep_idx = by_date[entry_date], by_date[sweep_date]
    if not sweep_idx < i:
        return None, 'INVALID_SEED_DATE_ORDER'
    entry, stop = bars[i]['o'], float(seed['sweep_low']) * STOP_BUFFER
    target_info = visible_target(bars, sweep_idx, entry)
    if stop >= entry:
        return None, 'INVALID_STOP'
    if target_info is None:
        return None, 'NO_VISIBLE_UPSIDE_TARGET'
    _, target = target_info
    path = bars[i + 1:i + 1 + HOLD]
    if len(path) < HOLD:
        return None, 'OPEN_DATA'
    reason, exit_bar, exit_price = 'TIME20', path[-1], path[-1]['c']
    for bar in path:
        if bar['o'] <= stop:
            reason, exit_bar, exit_price = 'GAP_SL', bar, bar['o']
            break
        if bar['l'] <= stop:
            reason, exit_bar, exit_price = 'SL', bar, stop
            break
        if bar['h'] >= target:
            reason, exit_bar, exit_price = 'TP_STRUCTURAL', bar, target
            break
    return {
        **seed, 'exit_date': exit_bar['d'], 'reason': reason,
        'gross_pnl_pct': round(pct(exit_price, entry), 6),
        'net_pnl_pct': round(pct(exit_price, entry) - BASE_COST, 6),
        'same_day_exit_violation': bars[i]['d'] == exit_bar['d'],
    }, None


def measures(rows: list[dict[str, Any]], cost: float = BASE_COST) -> dict[str, Any]:
    pnl = [float(r['gross_pnl_pct']) - cost for r in rows]
    wins, losses = [x for x in pnl if x > 0], [x for x in pnl if x < 0]
    gain, loss = sum(wins), abs(sum(losses))
    return {
        'n': len(rows),
        'gross_wr_pct': round(100 * len(wins) / len(rows), 4) if rows else 0.0,
        'avg_net_pnl_pct': round(sum(pnl) / len(rows), 4) if rows else 0.0,
        'profit_factor': round(gain / loss, 4) if loss else 0.0,
        'payoff_rr': round((sum(wins) / len(wins)) / abs(sum(losses) / len(losses)), 4) if wins and losses else 0.0,
        'total_net_pnl_pct': round(sum(pnl), 4),
        'exit_counts': dict(Counter(r['reason'] for r in rows)),
    }


def band_of(value: float) -> str | None:
    for name, (lo, hi) in BANDS.items():
        if lo <= value <= hi:
            return name
    return None


def serial_replay(seeds: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Counter]:
    seeds.sort(key=lambda r: (r['entry_date'], r['symbol'], r['sweep_idx']))
    cache: dict[str, list[dict[str, Any]]] = {}
    busy: dict[str, str] = {}
    done, skipped = [], Counter()
    for seed in seeds:
        if busy.get(seed['symbol'], '') >= seed['entry_date']:
            skipped['SYMBOL_ALREADY_OPEN'] += 1
            continue
        result, why = execute(seed, cache.setdefault(seed['symbol'], load_bars(seed['symbol'])))
        if result is None:
            skipped[why or 'UNKNOWN'] += 1
            continue
        done.append(result)
        busy[seed['symbol']] = result['exit_date']
    return done, skipped


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    v517, v519 = json.loads(V517.read_text()), json.loads(V519.read_text())
    if not (v517.get('support_gate_pass') and v519.get('promotion_gate_pass')):
        raise RuntimeError('V517/V519 frozen prerequisites failed; diagnostic blocked')

    # Freeze the diagnostic universe to the final V517 eligible date.  The cache
    # can contain newer bars; including them would turn a fixed historical audit
    # into a moving sample and can create an unclosed fresh row.
    with Path(v517['artifacts']['seeds']).open(newline='', encoding='utf-8') as h:
        v517_seeds = list(csv.DictReader(h))
    frozen_end_date = max(row['entry_eligible_date'] for row in v517_seeds)
    # Bar indices are cache-relative and can shift when the provider backfills an
    # older date.  Stable causal identity is symbol + sweep trading date.
    v517_high_keys = {(row['symbol'], row['sweep_date']) for row in v517_seeds}

    # Stage A does not open outcomes: recreate the price-only superset and rank it.
    all_seeds = []
    invalid_files = 0
    for path in sorted(KD.glob('*_daily_750.json')):
        try:
            code, exchange = path.name.replace('_daily_750.json', '').rsplit('_', 1)
        except ValueError:
            invalid_files += 1
            continue
        bars = load_bars(f'{code}.{exchange}')
        if not bars:
            invalid_files += 1
            continue
        all_seeds.extend(scan_price_chronology(f'{code}.{exchange}', bars))
    all_seeds = [row for row in all_seeds if row['entry_date'] <= frozen_end_date]
    all_seeds.sort(key=lambda r: (r['entry_date'], r['symbol'], r['sweep_idx']))
    band_seeds = defaultdict(list)
    for row in all_seeds:
        name = band_of(float(row['prior20_volume_rank']))
        if name:
            band_seeds[name].append(row)

    # Outcome stage: each predeclared band gets the same frozen execution contract.
    band_results, diagnostics = {}, {}
    for name in BANDS:
        trades, skips = serial_replay(band_seeds[name])
        annual = {y: measures([r for r in trades if r['entry_date'].startswith(y)]) for y in YEARS}
        band_results[name] = {
            'outcome_blind_seed_count': len(band_seeds[name]),
            'closed_trade_count': len(trades), 'skip_counts': dict(skips),
            'overall': measures(trades), 'yearly': annual,
            'all_t1_clean': not any(r['same_day_exit_violation'] for r in trades),
        }
        diagnostics[name] = trades

    high, low = band_results['HIGH_0_80_1_00']['overall'], band_results['LOW_0_00_0_45']['overall']
    regenerated_high_keys = {(row['symbol'], row['sweep_date']) for row in band_seeds['HIGH_0_80_1_00']}
    # Cost stress only uses the exact V519 frozen trade ledger, never alternate entries.
    with Path(v519['artifacts']['trades']).open(newline='', encoding='utf-8') as h:
        frozen = list(csv.DictReader(h))
    cost_stress = {}
    for cost in COSTS:
        annual = {y: measures([r for r in frozen if r['entry_date'].startswith(y)], cost) for y in YEARS}
        overall = measures(frozen, cost)
        cost_stress[f'{cost:.2f}'] = {
            'round_trip_cost_pct': cost, 'overall': overall, 'yearly': annual,
            'all_years_avg_net_positive': all(x['avg_net_pnl_pct'] > 0 for x in annual.values()),
            'overall_pf_gt_1': overall['profit_factor'] > 1.0,
        }
    max_supported = max(cost for cost, data in ((float(k), v) for k, v in cost_stress.items())
                        if data['all_years_avg_net_positive'] and data['overall_pf_gt_1'])
    contract = ('confirmed 3-left/3-right swing low -> >=0.3% wick breach and close reclaim '
                '-> next completed close breaks sweep high -> following open eligible; volume rank is '
                'only stratified for diagnostic; frozen SL/TP/T+1/serial execution unchanged')
    report = {
        'version': 'V524_EFFORT_INCREMENT_AND_COST_STRESS_AUDIT_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'scope': 'post-promotion diagnostic only; no new candidate or parameter selection',
        'predeclared_contract': contract,
        'rank_bands': {k: {'min': v[0], 'max': v[1]} for k, v in BANDS.items()},
        'outcome_blind_stage': {
            'files_scanned': len(list(KD.glob('*_daily_750.json'))), 'invalid_or_empty_files': invalid_files,
            'frozen_end_date_from_v517': frozen_end_date,
            'price_chronology_seed_count': len(all_seeds),
            'per_band_seed_count': {k: len(v) for k, v in band_seeds.items()},
            'outcomes_opened_before_banding': False,
        },
        'fixed_contract_band_replay': band_results,
        'volume_increment': {
            'comparison': 'HIGH_0_80_1_00 minus LOW_0_00_0_45, fixed price chronology and frozen execution',
            'avg_net_pnl_pct_delta': round(high['avg_net_pnl_pct'] - low['avg_net_pnl_pct'], 4),
            'gross_wr_pct_delta': round(high['gross_wr_pct'] - low['gross_wr_pct'], 4),
            'profit_factor_delta': round(high['profit_factor'] - low['profit_factor'], 4),
            'supportive_direction': (high['avg_net_pnl_pct'] > low['avg_net_pnl_pct'] and high['profit_factor'] > low['profit_factor']),
            'warning': 'observational strata result, not a license to replace V517 or tune a cutoff',
        },
        'frozen_ledger_cost_stress': cost_stress,
        'max_predeclared_cost_with_all_years_positive_and_pf_gt_1': max_supported,
        'invariants': {
            'all_production_writes_false': True,
            'no_scanner_or_watchlist_source_used': True,
            'frozen_end_date_applied': all(row['entry_date'] <= frozen_end_date for row in all_seeds),
            'regenerated_high_band_exactly_matches_v517_seed_set': regenerated_high_keys == v517_high_keys,
            'cost_stress_uses_exact_v519_ledger': len(frozen) == v519['closed_trade_count'],
            'all_band_trades_t1_clean': all(x['all_t1_clean'] for x in band_results.values()),
        },
        'decision': 'V524_DIAGNOSTIC_COMPLETE__NO_PRODUCTION_STATE_CHANGE',
        'artifacts': {'out_dir': str(OUT), 'latest': str(LATEST), 'v517': str(V517), 'v519': str(V519)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v524_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
