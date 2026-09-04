#!/usr/bin/env python3
"""V537 outcome-blind support gate: no-supply compression -> demand expansion.

Frozen causal ontology, distinct from V517/V527/V530/V533:
1. A 3-left/3-right structural swing low is confirmed before the base begins.
2. Three completed sessions hold that low while both volume and true range
   contract session-by-session: supply is visibly exhausted, not swept.
3. A later high-effort demand bar closes above the entire base range.
4. Only the following session open is eligible. No outcome is read here.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
KDIR = ROOT / 'kline_cache'
AUD = ROOT / 'smc_audit'
OUT = AUD / f'v537_no_supply_compression_expansion_seed_gate_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v537_no_supply_compression_expansion_seed_gate_latest.json'

LEFT = RIGHT = 3
VOL_LOOKBACK = 20
BASE_BARS = 3
LOW_VOLUME_OF_PRIOR_MEDIAN = 0.80
EXPANSION_VOLUME_RANK_MIN = 0.80
YEARS = ('2023', '2024', '2025', '2026')
SUPPORT_TOTAL_MIN = 300
SUPPORT_YEAR_MIN = 40
PROMOTION_GATE = {
    'gross_wr_pct_min': 55.0,
    'avg_net_pnl_pct_min': 0.5,
    'pf_min': 1.15,
    'payoff_min': 0.70,
    'each_year_avg_net_pnl_pct_min': 0.0,
    't1_violations': 0,
}


def positive(value: Any) -> float | None:
    try:
        number = float(value)
        return number if number > 0 else None
    except (TypeError, ValueError):
        return None


def date_key(value: Any) -> str:
    digits = ''.join(char for char in str(value or '') if char.isdigit())
    return digits[:8] if len(digits) >= 8 else ''


def load_bars(path: Path) -> list[dict[str, Any]]:
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return []
    bars = []
    for row in raw if isinstance(raw, list) else []:
        date = date_key(row.get('t') or row.get('date') or row.get('day'))
        values = [positive(row.get(key)) for key in ('o', 'h', 'l', 'c', 'v')]
        if date and all(value is not None for value in values):
            bars.append(dict(zip(('t', 'o', 'h', 'l', 'c', 'v'), (date, *values))))
    return sorted(bars, key=lambda bar: bar['t'])


def is_confirmed_swing_low(bars: list[dict[str, Any]], index: int) -> bool:
    if index < LEFT or index + RIGHT >= len(bars):
        return False
    low = bars[index]['l']
    return (low < min(bars[j]['l'] for j in range(index - LEFT, index))
            and low <= min(bars[j]['l'] for j in range(index + 1, index + RIGHT + 1)))


def median(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def volume_rank_prior(bars: list[dict[str, Any]], index: int) -> float:
    prior = [bars[j]['v'] for j in range(index - VOL_LOOKBACK, index)]
    return sum(value <= bars[index]['v'] for value in prior) / len(prior) if len(prior) == VOL_LOOKBACK else 0.0


def scan_symbol(symbol: str, bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = []
    start = max(VOL_LOOKBACK, LEFT + RIGHT + 1) + BASE_BARS
    for expansion_index in range(start, len(bars) - 1):
        base_start = expansion_index - BASE_BARS
        base = bars[base_start:expansion_index]
        swing_index = base_start - RIGHT - 1
        if not is_confirmed_swing_low(bars, swing_index):
            continue
        swing = bars[swing_index]
        prior_volume = [bars[j]['v'] for j in range(base_start - VOL_LOOKBACK, base_start)]
        base_ranges = [bar['h'] - bar['l'] for bar in base]
        base_volumes = [bar['v'] for bar in base]
        holds_structural_low = all(bar['l'] >= swing['l'] for bar in base)
        contracting_ranges = base_ranges[0] > base_ranges[1] > base_ranges[2]
        contracting_volumes = base_volumes[0] > base_volumes[1] > base_volumes[2]
        low_effort_base = all(volume <= median(prior_volume) * LOW_VOLUME_OF_PRIOR_MEDIAN for volume in base_volumes)
        expansion = bars[expansion_index]
        base_high = max(bar['h'] for bar in base)
        high_effort_expansion = volume_rank_prior(bars, expansion_index) >= EXPANSION_VOLUME_RANK_MIN
        breaks_base = expansion['c'] > base_high
        if not (holds_structural_low and contracting_ranges and contracting_volumes
                and low_effort_base and high_effort_expansion and breaks_base):
            continue
        entry = bars[expansion_index + 1]
        seeds.append({
            'symbol': symbol,
            'ontology': 'VSA_NO_SUPPLY_COMPRESSION_DEMAND_EXPANSION',
            'swing_idx': swing_index,
            'swing_date': swing['t'],
            'swing_low': round(swing['l'], 6),
            'base_start_idx': base_start,
            'base_start_date': base[0]['t'],
            'base_end_idx': expansion_index - 1,
            'base_end_date': base[-1]['t'],
            'base_low': round(min(bar['l'] for bar in base), 6),
            'base_high': round(base_high, 6),
            'base_volume_to_prior_median': round(base_volumes[-1] / median(prior_volume), 6),
            'expansion_idx': expansion_index,
            'expansion_date': expansion['t'],
            'expansion_close': round(expansion['c'], 6),
            'expansion_volume_rank': round(volume_rank_prior(bars, expansion_index), 6),
            'entry_eligible_idx': expansion_index + 1,
            'entry_eligible_date': entry['t'],
            'causal_trace': 'confirmed_swing_low -> three_bar_low_effort_range_and_volume_contraction_holds_low -> high_effort_close_breaks_base_high -> following_open_eligible',
        })
    return seeds


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(KDIR.glob('*_daily_750.json'))
    seeds: list[dict[str, Any]] = []
    valid = 0
    for number, path in enumerate(files, 1):
        bars = load_bars(path)
        if len(bars) < 80:
            continue
        valid += 1
        try:
            code, exchange = path.name.removesuffix('_daily_750.json').rsplit('_', 1)
        except ValueError:
            continue
        seeds.extend(scan_symbol(f'{code}.{exchange}', bars))
        if number % 1000 == 0:
            print(f'progress {number}/{len(files)} seeds={len(seeds)}', flush=True)

    seeds.sort(key=lambda row: (row['entry_eligible_date'], row['symbol'], row['expansion_idx']))
    yearly = Counter(row['entry_eligible_date'][:4] for row in seeds)
    forbidden = {'pnl', 'exit', 'mfe', 'mae', 'tp', 'sl', 'entry_price'}
    checks = {
        'total_n>=300': len(seeds) >= SUPPORT_TOTAL_MIN,
        'each_year_n>=40': all(yearly[year] >= SUPPORT_YEAR_MIN for year in YEARS),
        'no_outcome_fields': all(not any(field in forbidden for field in row) for row in seeds),
        'strict_chronology': all(row['swing_idx'] < row['base_start_idx'] <= row['base_end_idx'] < row['expansion_idx'] < row['entry_eligible_idx'] for row in seeds),
    }
    seed_path = OUT / 'v537_outcome_blind_seeds.csv'
    fields = list(seeds[0]) if seeds else ['symbol', 'ontology', 'entry_eligible_date']
    with seed_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(seeds)
    report = {
        'version': 'V537_VSA_NO_SUPPLY_COMPRESSION_DEMAND_EXPANSION_SEED_GATE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'outcomes_opened': False,
        'distinctness': 'Begins with supply exhaustion in a low-volume, contracting base above a confirmed low, then demand expansion. It is not V517 high-effort sweep/reclaim, V527 spring/test/SOS, V530 SOS/backup, or V533 selling climax.',
        'frozen_contract': 'confirmed 3-left/3-right swing low -> three consecutive low-effort sessions with strictly contracting volume and range holding that low -> high-effort close above base high -> following-session open eligible',
        'constants': {'left_right': LEFT, 'volume_lookback': VOL_LOOKBACK, 'base_bars': BASE_BARS, 'low_volume_of_prior_median': LOW_VOLUME_OF_PRIOR_MEDIAN, 'expansion_volume_rank_min': EXPANSION_VOLUME_RANK_MIN},
        'support_gate': {'total_min': SUPPORT_TOTAL_MIN, 'year_min': SUPPORT_YEAR_MIN, 'years': YEARS},
        'promotion_gate_if_replay': PROMOTION_GATE,
        'files_seen': len(files),
        'files_valid': valid,
        'seed_count': len(seeds),
        'yearly_seed_count': {year: yearly[year] for year in YEARS},
        'support_checks': checks,
        'support_gate_pass': all(checks.values()),
        'decision': 'V537_SUPPORT_PASS__INDEPENDENT_ORACLE_REQUIRED_BEFORE_ONE_FROZEN_T1_REPLAY' if all(checks.values()) else 'V537_SUPPORT_FAIL__CLOSE_ONTOLOGY_WITHOUT_OUTCOMES__NO_RELAXATION',
        'artifacts': {'out_dir': str(OUT), 'seeds': str(seed_path), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v537_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
