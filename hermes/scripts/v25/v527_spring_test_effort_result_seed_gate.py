#!/usr/bin/env python3
"""V527 outcome-blind seed gate: Wyckoff spring -> low-volume test -> SOS.

Frozen causal ontology (not a V517 threshold variation):
1. a 3-left/3-right swing low is already confirmed before the spring;
2. price sweeps that low >=0.3%, closes back above it, on top-quintile
   relative volume versus 20 completed prior sessions (absorption);
3. within the next five sessions, a test revisits the lower half of the
   spring range without breaking the spring low, closes above the old swing,
   and uses less volume than the spring (supply drying up);
4. within five sessions after the test, close breaks the spring high (SOS);
5. only the following session open is eligible.  No outcomes are read here.

Predeclared support gate: total >=300 and each 2023-2026 year >=40.
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
OUT = AUD / f'v527_spring_test_effort_result_seed_gate_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v527_spring_test_effort_result_seed_gate_latest.json'
LEFT = RIGHT = 3
LOOKBACK_VOL = 20
TEST_WAIT = 5
SOS_WAIT = 5
YEARS = ('2023', '2024', '2025', '2026')


def number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if result > 0 else None
    except (TypeError, ValueError):
        return None


def trading_day(value: Any) -> str:
    digits = ''.join(char for char in str(value or '') if char.isdigit())
    return digits[:8] if len(digits) >= 8 else ''


def load_bars(path: Path) -> list[dict[str, Any]]:
    try:
        source = json.loads(path.read_text())
    except Exception:
        return []
    bars = []
    for row in source if isinstance(source, list) else []:
        date = trading_day(row.get('t') or row.get('date') or row.get('day'))
        o, h, l, c, v = (number(row.get(key)) for key in ('o', 'h', 'l', 'c', 'v'))
        if date and None not in (o, h, l, c, v):
            bars.append({'t': date, 'o': o, 'h': h, 'l': l, 'c': c, 'v': v})
    return sorted(bars, key=lambda item: item['t'])


def confirmed_swing_low(bars: list[dict[str, Any]], index: int) -> bool:
    if index < LEFT or index + RIGHT >= len(bars):
        return False
    low = bars[index]['l']
    return (
        all(low < bars[pos]['l'] for pos in range(index - LEFT, index))
        and all(low <= bars[pos]['l'] for pos in range(index + 1, index + RIGHT + 1))
    )


def top_quintile_volume(bars: list[dict[str, Any]], index: int) -> bool:
    if index < LOOKBACK_VOL:
        return False
    previous = [bars[pos]['v'] for pos in range(index - LOOKBACK_VOL, index)]
    if len(previous) != LOOKBACK_VOL:
        return False
    threshold = sorted(previous)[int(LOOKBACK_VOL * 0.8) - 1]
    return bars[index]['v'] >= threshold


def scan_symbol(symbol: str, bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # One spring may sit below several older pivots.  Its causal liquidity anchor
    # is exclusively the nearest already-confirmed swing low, preventing one
    # physical event from being multiplied by historical pivot identities.
    confirmed = [idx for idx in range(LEFT, len(bars) - RIGHT) if confirmed_swing_low(bars, idx)]
    rows: list[dict[str, Any]] = []
    for spring_idx in range(LEFT + RIGHT + 1, len(bars) - 1):
        prior = [idx for idx in confirmed if idx + RIGHT < spring_idx]
        if not prior:
            continue
        swing_idx = prior[-1]
        swing_low = bars[swing_idx]['l']
        spring = bars[spring_idx]
        if not (
            spring['l'] <= swing_low * 0.997
            and spring['c'] > swing_low
            and top_quintile_volume(bars, spring_idx)
        ):
            continue
        spring_high = spring['h']
        spring_range = spring_high - spring['l']
        test_idx = None
        for pos in range(spring_idx + 1, min(spring_idx + TEST_WAIT + 1, len(bars))):
            test = bars[pos]
            if (
                test['l'] > spring['l']
                and test['l'] <= spring['l'] + spring_range * 0.5
                and test['c'] > swing_low
                and test['v'] < spring['v']
            ):
                test_idx = pos
                break
        if test_idx is None:
            continue
        sos_idx = None
        for pos in range(test_idx + 1, min(test_idx + SOS_WAIT + 1, len(bars))):
            if bars[pos]['c'] > spring_high:
                sos_idx = pos
                break
        if sos_idx is None:
            continue
        entry_idx = sos_idx + 1
        if entry_idx >= len(bars):
            continue
        rows.append({
            'symbol': symbol,
            'swing_idx': swing_idx,
            'swing_date': bars[swing_idx]['t'],
            'swing_low': round(swing_low, 6),
            'spring_idx': spring_idx,
            'spring_date': spring['t'],
            'spring_low': round(spring['l'], 6),
            'spring_high': round(spring_high, 6),
            'spring_volume': round(spring['v'], 6),
            'test_idx': test_idx,
            'test_date': bars[test_idx]['t'],
            'test_low': round(bars[test_idx]['l'], 6),
            'test_volume': round(bars[test_idx]['v'], 6),
            'sos_idx': sos_idx,
            'sos_date': bars[sos_idx]['t'],
            'entry_eligible_idx': entry_idx,
            'entry_eligible_date': bars[entry_idx]['t'],
            'sequence': 'CONFIRMED_SSL->HIGH_EFFORT_SPRING->LOW_VOLUME_TEST->SOS_BREAK->NEXT_OPEN',
        })
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    scanned = usable = 0
    for path in sorted(KDIR.glob('*_daily_750.json')):
        scanned += 1
        stem = path.name.removesuffix('_daily_750.json')
        code, exchange = stem.rsplit('_', 1)
        bars = load_bars(path)
        if not bars:
            continue
        usable += 1
        rows.extend(scan_symbol(f'{code}.{exchange}', bars))
    rows.sort(key=lambda row: (row['entry_eligible_date'], row['symbol'], row['spring_date']))
    yearly = {year: sum(row['entry_eligible_date'].startswith(year) for row in rows) for year in YEARS}
    support = {'n>=300': len(rows) >= 300, 'each_year_n>=40': all(yearly[year] >= 40 for year in YEARS)}
    fields = list(rows[0]) if rows else ['symbol', 'entry_eligible_date']
    seeds = OUT / 'v527_outcome_blind_seeds.csv'
    with seeds.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    report = {
        'version': 'V527_SPRING_TEST_EFFORT_RESULT_SEED_GATE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'frozen_contract': 'confirmed 3-left/3-right swing low -> high-effort >=0.3% SSL spring/reclaim -> lower-half low-volume non-break test within 5 bars -> SOS close above spring high within 5 bars -> following open eligible',
        'outcomes_opened': False,
        'scanned_files': scanned,
        'usable_files': usable,
        'seed_count': len(rows),
        'yearly_seed_count': yearly,
        'support_gate': {'n_min': 300, 'year_n_min': 40},
        'support_checks': support,
        'support_gate_pass': all(support.values()),
        'decision': 'V527_SUPPORT_PASS__INDEPENDENT_ORACLE_REQUIRED' if all(support.values()) else 'V527_SUPPORT_FAIL__CLOSE_ONTOLOGY__NO_OUTCOMES_OPENED',
        'artifacts': {'out_dir': str(OUT), 'seeds': str(seeds)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v527_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
