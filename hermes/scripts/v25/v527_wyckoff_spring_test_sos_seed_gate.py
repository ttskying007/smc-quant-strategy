#!/usr/bin/env python3
"""V527 outcome-blind support gate: volume-confirmed Wyckoff spring -> test -> SOS.

Frozen ontology, before any outcome is read:
1. A 3-left/3-right swing low has become visible.
2. A later high-volume spring breaches it by >=0.3% but closes back above it.
3. The *first* test in the next five completed sessions holds above the spring low,
   has lower volume (<=60% of spring volume), and closes above the old swing low.
4. Within the next three completed sessions, a Sign of Strength closes above that
   test's high. Only the following session open is eligible for a strict T+1 entry.

This is distinct from V517's immediate response-break ontology: it requires an
explicit low-effort supply test after the high-effort spring. This script opens
no outcomes and writes no production-facing state.
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
OUT = AUD / f'v527_wyckoff_spring_test_sos_seed_gate_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v527_wyckoff_spring_test_sos_seed_gate_latest.json'

LEFT = RIGHT = 3
SWEEP_PCT = 0.003
VOLUME_LOOKBACK = 20
HIGH_VOLUME_RANK_MIN = 0.80
TEST_MAX_VOLUME_OF_SPRING = 0.60
TEST_LOOKAHEAD = 5
SOS_LOOKAHEAD = 3
YEARS = ('2023', '2024', '2025', '2026')
SUPPORT_TOTAL_MIN = 300
SUPPORT_YEAR_MIN = 40
PROMOTION_TARGET = {
    'gross_wr_pct_min': 60.0,
    'avg_net_pnl_pct_min': 0.75,
    'pf_min': 1.30,
    'payoff_min': 1.00,
    'each_year_avg_net_pnl_pct_min': 0.0,
    't1_violations': 0,
}


def positive(value: Any) -> float | None:
    try:
        result = float(value)
        return result if result > 0 else None
    except (TypeError, ValueError):
        return None


def day(value: Any) -> str:
    digits = ''.join(char for char in str(value or '') if char.isdigit())
    return digits[:8] if len(digits) >= 8 else ''


def load_bars(path: Path) -> list[dict[str, Any]]:
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return []
    bars = []
    for row in raw if isinstance(raw, list) else []:
        date = day(row.get('t') or row.get('date') or row.get('day'))
        o, h, l, c, v = (positive(row.get(key)) for key in ('o', 'h', 'l', 'c', 'v'))
        if date and None not in (o, h, l, c, v):
            bars.append({'t': date, 'o': o, 'h': h, 'l': l, 'c': c, 'v': v})
    return sorted(bars, key=lambda bar: bar['t'])


def confirmed_swing_low(bars: list[dict[str, Any]], index: int) -> bool:
    if index < LEFT or index + RIGHT >= len(bars):
        return False
    low = bars[index]['l']
    return (low < min(bars[j]['l'] for j in range(index - LEFT, index))
            and low <= min(bars[j]['l'] for j in range(index + 1, index + RIGHT + 1)))


def prior_volume_rank(bars: list[dict[str, Any]], index: int) -> float:
    prior = [bars[j]['v'] for j in range(index - VOLUME_LOOKBACK, index)]
    return sum(volume <= bars[index]['v'] for volume in prior) / len(prior) if prior else 0.0


def scan_symbol(symbol: str, bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = []
    start = max(VOLUME_LOOKBACK, LEFT + RIGHT + 1)
    # Reserve spring + test window + SOS window + following eligible open.
    end = len(bars) - TEST_LOOKAHEAD - SOS_LOOKAHEAD - 1
    for spring_index in range(start, end):
        swing_index = spring_index - RIGHT - 1
        if not confirmed_swing_low(bars, swing_index):
            continue
        swing, spring = bars[swing_index], bars[spring_index]
        if not (spring['l'] <= swing['l'] * (1 - SWEEP_PCT)
                and spring['c'] > swing['l']
                and prior_volume_rank(bars, spring_index) >= HIGH_VOLUME_RANK_MIN):
            continue

        test_index = next((index for index in range(spring_index + 1, spring_index + 1 + TEST_LOOKAHEAD)
                           if bars[index]['l'] >= spring['l']
                           and bars[index]['c'] > swing['l']
                           and bars[index]['v'] <= spring['v'] * TEST_MAX_VOLUME_OF_SPRING), None)
        if test_index is None:
            continue
        test = bars[test_index]
        sos_index = next((index for index in range(test_index + 1, test_index + 1 + SOS_LOOKAHEAD)
                          if bars[index]['c'] > test['h']), None)
        if sos_index is None:
            continue
        entry_index = sos_index + 1
        entry = bars[entry_index]
        seeds.append({
            'symbol': symbol,
            'ontology': 'WYCKOFF_HIGH_EFFORT_SPRING_LOW_EFFORT_TEST_SOS',
            'swing_idx': swing_index,
            'swing_date': swing['t'],
            'swing_low': round(swing['l'], 6),
            'spring_idx': spring_index,
            'spring_date': spring['t'],
            'spring_low': round(spring['l'], 6),
            'spring_high': round(spring['h'], 6),
            'spring_close': round(spring['c'], 6),
            'spring_volume': round(spring['v'], 6),
            'prior20_volume_rank': round(prior_volume_rank(bars, spring_index), 6),
            'test_idx': test_index,
            'test_date': test['t'],
            'test_low': round(test['l'], 6),
            'test_high': round(test['h'], 6),
            'test_close': round(test['c'], 6),
            'test_volume': round(test['v'], 6),
            'test_to_spring_volume_ratio': round(test['v'] / spring['v'], 6),
            'sos_idx': sos_index,
            'sos_date': bars[sos_index]['t'],
            'sos_close': round(bars[sos_index]['c'], 6),
            'entry_eligible_idx': entry_index,
            'entry_eligible_date': entry['t'],
            'causal_trace': 'confirmed_swing_low -> high_effort_spring_reclaim -> first_low_effort_test_holds_spring -> SOS_close_above_test_high -> following_open_eligible',
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
            print(f'progress {number}/{len(files)} seeds={len(seeds)}')

    seeds.sort(key=lambda row: (row['entry_eligible_date'], row['symbol'], row['spring_idx']))
    yearly = Counter(row['entry_eligible_date'][:4] for row in seeds)
    forbidden_outcome_fields = {'pnl', 'exit', 'mfe', 'mae', 'tp', 'sl', 'entry_price'}
    invariants = {
        'no_outcome_fields': all(not any(field.lower() in forbidden_outcome_fields for field in row) for row in seeds),
        'strict_chronology': all(row['swing_idx'] < row['spring_idx'] < row['test_idx'] < row['sos_idx'] < row['entry_eligible_idx'] for row in seeds),
        'all_years_declared': all(row['entry_eligible_date'][:4] in YEARS for row in seeds),
    }
    support_checks = {
        'total_n>=300': len(seeds) >= SUPPORT_TOTAL_MIN,
        'each_year_n>=40': all(yearly[year] >= SUPPORT_YEAR_MIN for year in YEARS),
        **invariants,
    }
    support_pass = all(support_checks.values())
    seed_path = OUT / 'v527_outcome_blind_seeds.csv'
    fields = list(seeds[0].keys()) if seeds else ['symbol', 'ontology', 'entry_eligible_date']
    with seed_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(seeds)
    report = {
        'version': 'V527_WYCKOFF_SPRING_TEST_SOS_SEED_GATE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'distinctness': 'A volume-sequenced high-effort spring followed by an explicit low-effort test and SOS; not V517 immediate response, not double-raid, and not a price-only SMC threshold variant.',
        'frozen_contract': 'confirmed 3-left/3-right swing low -> >=0.3% high-volume spring reclaim -> first 1..5-bar low-volume test holds spring low -> 1..3-bar SOS close above test high -> following open eligible',
        'constants': {
            'swing_left_right': 3,
            'spring_breach_pct': SWEEP_PCT,
            'volume_lookback': VOLUME_LOOKBACK,
            'spring_volume_rank_min': HIGH_VOLUME_RANK_MIN,
            'test_max_volume_of_spring': TEST_MAX_VOLUME_OF_SPRING,
            'test_lookahead': TEST_LOOKAHEAD,
            'sos_lookahead': SOS_LOOKAHEAD,
        },
        'support_gate': {'total_min': SUPPORT_TOTAL_MIN, 'year_min': SUPPORT_YEAR_MIN, 'years': YEARS},
        'promotion_target_if_support_passes': PROMOTION_TARGET,
        'files_seen': len(files),
        'files_valid': valid,
        'seed_count': len(seeds),
        'yearly_seed_count': {year: yearly[year] for year in YEARS},
        'invariants': invariants,
        'support_checks': support_checks,
        'support_gate_pass': support_pass,
        'outcomes_opened': False,
        'decision': ('V527_SUPPORT_PASS__INDEPENDENT_ORACLE_REQUIRED_BEFORE_ONE_FROZEN_T1_REPLAY'
                     if support_pass else 'V527_SUPPORT_FAIL__CLOSE_ONTOLOGY_WITHOUT_OUTCOMES__DO_NOT_RELAX'),
        'artifacts': {'out_dir': str(OUT), 'seeds': str(seed_path), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v527_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
