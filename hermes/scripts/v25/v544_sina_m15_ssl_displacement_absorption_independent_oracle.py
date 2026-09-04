#!/usr/bin/env python3
"""V544 independent raw-bar oracle for V543's frozen participation ontology.

This does not import V543. It independently derives only causal identities from
Sina m15 OHLCV, then compares them against V543 outcome-blind seeds. `shard`
reads raw bars only; `merge` is the only mode that reads the frozen identities.
No outcome, replay, production, frontend, watchlist, or position data is read.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path('/root/.hermes')
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina/m15'
AUDIT = ROOT / 'smc_audit'
V543 = AUDIT / 'v543_sina_m15_ssl_displacement_absorption_seed_gate_latest.json'
SHARDS = AUDIT / 'v544_shards_20260723'
OUT = AUDIT / f'v544_sina_m15_ssl_displacement_absorption_independent_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v544_sina_m15_ssl_displacement_absorption_independent_oracle_latest.json'
LEFT = RIGHT = 3
LOOKBACK = 20
SWEEP_PCT = 0.003
SWEEP_VOL_Q = 0.80
BOS_MAX_BARS = 12
RETEST_MAX_BARS = 20
DISPLACEMENT_RANGE_MULT = 1.20
DISPLACEMENT_VOL_MULT = 1.20
FVG_WIDTH_RANGE_MULT = 0.50
RETEST_VOL_MAX_MULT = 1.00
IDENTITY = ('symbol', 'swing_time', 'sweep_time', 'reference_high_time', 'bos_time', 'fvg_time', 'reclaim_time', 'entry_time')


def number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if result > 0 and math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def read_bars(path: Path) -> list[dict[str, Any]]:
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return []
    rows = []
    for source in raw if isinstance(raw, list) else []:
        stamp = str(source.get('t') or '')
        values = [number(source.get(key)) for key in ('o', 'h', 'l', 'c', 'v')]
        if len(stamp) == 14 and all(value is not None for value in values):
            rows.append({'t': stamp, 'd': stamp[:8], 'o': values[0], 'h': values[1], 'l': values[2], 'c': values[3], 'v': values[4]})
    return sorted(rows, key=lambda row: row['t'])


def swing_flags(rows: list[dict[str, Any]]) -> tuple[list[bool], list[bool]]:
    lows, highs = [False] * len(rows), [False] * len(rows)
    for i in range(LEFT, len(rows) - RIGHT):
        before, after = rows[i - LEFT:i], rows[i + 1:i + RIGHT + 1]
        lows[i] = rows[i]['l'] < min(row['l'] for row in before) and rows[i]['l'] <= min(row['l'] for row in after)
        highs[i] = rows[i]['h'] > max(row['h'] for row in before) and rows[i]['h'] >= max(row['h'] for row in after)
    return lows, highs


def local_reference(rows: list[dict[str, Any]], i: int) -> tuple[float, float, float] | None:
    if i < LOOKBACK:
        return None
    prior = rows[i - LOOKBACK:i]
    ranges = [row['h'] - row['l'] for row in prior]
    volumes = sorted(row['v'] for row in prior)
    return median(ranges), volumes[math.ceil(SWEEP_VOL_Q * len(volumes)) - 1], median(volumes)


def derive(symbol: str, rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    lows, highs = swing_flags(rows)
    bases = [local_reference(rows, i) for i in range(len(rows))]
    low_anchor: int | None = None
    high_anchor: int | None = None
    active: list[dict[str, int | float | str]] = []
    identities: list[dict[str, str]] = []
    last_entry = -1
    for now, bar in enumerate(rows):
        confirmed = now - RIGHT - 1
        if confirmed >= 0 and lows[confirmed]:
            low_anchor, high_anchor = confirmed, None
        if (confirmed >= 0 and highs[confirmed] and low_anchor is not None
                and confirmed > low_anchor and rows[confirmed]['h'] > rows[low_anchor]['l']):
            high_anchor = confirmed
        next_active: list[dict[str, int | float | str]] = []
        for state in active:
            phase = state['phase']
            if phase == 'AWAIT_BREAK':
                if now - int(state['sweep_i']) > BOS_MAX_BARS:
                    continue
                baseline = bases[now]
                if baseline is not None:
                    range_median, _, volume_median = baseline
                    if (bar['c'] > float(state['reference_high']) and bar['c'] - bar['o'] >= range_median * DISPLACEMENT_RANGE_MULT and bar['v'] >= volume_median * DISPLACEMENT_VOL_MULT):
                        state.update({'phase': 'AWAIT_FVG', 'bos_i': now, 'bos_t': bar['t']})
                next_active.append(state)
                continue
            if phase == 'AWAIT_FVG':
                if now - int(state['bos_i']) > RETEST_MAX_BARS:
                    continue
                baseline = bases[now]
                if baseline is not None and now >= 2:
                    range_median, _, volume_median = baseline
                    width = bar['l'] - rows[now - 2]['h']
                    if rows[now - 2]['h'] < bar['l'] and width >= range_median * FVG_WIDTH_RANGE_MULT and bar['v'] >= volume_median * DISPLACEMENT_VOL_MULT:
                        state.update({'phase': 'AWAIT_RETEST', 'fvg_i': now, 'fvg_t': bar['t'], 'fvg_low': rows[now - 2]['h'], 'fvg_high': bar['l']})
                next_active.append(state)
                continue
            if now - int(state['fvg_i']) > RETEST_MAX_BARS:
                continue
            baseline = bases[now]
            if baseline is None:
                next_active.append(state)
                continue
            _, _, volume_median = baseline
            touched = now > int(state['fvg_i']) and bar['l'] <= float(state['fvg_high']) and bar['h'] >= float(state['fvg_low'])
            reclaimed = bar['c'] >= float(state['fvg_high'])
            contracted = bar['v'] <= volume_median * RETEST_VOL_MAX_MULT
            entry_i = now + 1
            # A qualifying first retest consumes its state even when the serial
            # one-position rule rejects that entry because another state already
            # reserved the same/earlier bar. Keeping it alive would incorrectly
            # turn a later touch into a second-retest identity.
            if touched and reclaimed and contracted:
                if entry_i < len(rows) and entry_i > last_entry:
                    identities.append({'symbol': symbol, 'swing_time': rows[int(state['low_i'])]['t'], 'sweep_time': rows[int(state['sweep_i'])]['t'], 'reference_high_time': rows[int(state['high_i'])]['t'], 'bos_time': str(state['bos_t']), 'fvg_time': str(state['fvg_t']), 'reclaim_time': bar['t'], 'entry_time': rows[entry_i]['t']})
                    last_entry = entry_i
            else:
                next_active.append(state)
        active = next_active
        baseline = bases[now]
        if low_anchor is None or high_anchor is None or baseline is None or high_anchor >= now:
            continue
        _, q80, _ = baseline
        low = rows[low_anchor]
        if bar['l'] <= low['l'] * (1 - SWEEP_PCT) and bar['c'] > low['l'] and bar['v'] >= q80:
            active.append({'phase': 'AWAIT_BREAK', 'low_i': low_anchor, 'high_i': high_anchor, 'sweep_i': now, 'reference_high': rows[high_anchor]['h']})
    return identities


def tuple_of(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(row[key]) for key in IDENTITY)


def run_shard(index: int, total: int) -> None:
    if not 0 <= index < total:
        raise ValueError('invalid shard index')
    selected = sorted(RAW.glob('*_m15.json.gz'))[index::total]
    SHARDS.mkdir(parents=True, exist_ok=True)
    output = SHARDS / f'v544_oracle_shard_{index:02d}_of_{total:02d}.csv'
    total_rows = short = 0
    with output.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=IDENTITY)
        writer.writeheader()
        for path in selected:
            rows = read_bars(path)
            if len(rows) < 100:
                short += 1
                continue
            identities = [row for row in derive(path.name.removesuffix('_m15.json.gz').replace('_', '.'), rows) if row['entry_time'][:4] in {'2025', '2026'}]
            writer.writerows(identities)
            total_rows += len(identities)
    print(json.dumps({'mode': 'oracle_shard', 'shard': index, 'total': total, 'files': len(selected), 'short_files': short, 'identities': total_rows, 'output': str(output)}))


def merge(total: int) -> None:
    report = json.loads(V543.read_text())
    frozen_path = Path(report['artifacts']['seeds'])
    with frozen_path.open(newline='', encoding='utf-8') as handle:
        expected = {tuple_of(row) for row in csv.DictReader(handle)}
    paths = [SHARDS / f'v544_oracle_shard_{index:02d}_of_{total:02d}.csv' for index in range(total)]
    if not all(path.exists() for path in paths):
        raise RuntimeError('all oracle shards are required before merge')
    actual: set[tuple[str, ...]] = set()
    for path in paths:
        with path.open(newline='', encoding='utf-8') as handle:
            actual.update(tuple_of(row) for row in csv.DictReader(handle))
    missing, extra = expected - actual, actual - expected
    OUT.mkdir(parents=True, exist_ok=False)
    identities_path = OUT / 'v544_oracle_identities.csv'
    with identities_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle); writer.writerow(IDENTITY); writer.writerows(sorted(actual))
    result = {'version': 'V544_SINA_M15_SSL_DISPLACEMENT_ABSORPTION_INDEPENDENT_ORACLE_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'), 'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False, 'source_contract': 'Sina source-isolated m15 only; partial 2025-04..2026-07 range; no cross-source bars.', 'oracle_contract': 'Independent state-machine derivation of V543 volume/displacement chronology; compares causal event identities only and never reads outcomes.', 'frozen_seed_source': str(frozen_path), 'm15_files_scanned': len(list(RAW.glob('*_m15.json.gz'))), 'shards': [str(path) for path in paths], 'expected_identities': len(expected), 'oracle_identities': len(actual), 'missing_identities': len(missing), 'extra_identities': len(extra), 'identity_match': not missing and not extra, 'samples': {'missing': [dict(zip(IDENTITY, row)) for row in sorted(missing)[:10]], 'extra': [dict(zip(IDENTITY, row)) for row in sorted(extra)[:10]]}, 'decision': 'V544_ORACLE_PASS__ONE_FROZEN_PARTIAL_RANGE_REPLAY_AUTHORIZED' if not missing and not extra else 'V544_ORACLE_MISMATCH__NO_OUTCOME_REPLAY', 'artifacts': {'dir': str(OUT), 'oracle_identities': str(identities_path), 'latest': str(LATEST), 'v543': str(V543)}}
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v544_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit('usage: v544 ... shard INDEX TOTAL | merge TOTAL')
    if sys.argv[1] == 'shard' and len(sys.argv) == 4:
        run_shard(int(sys.argv[2]), int(sys.argv[3]))
    elif sys.argv[1] == 'merge' and len(sys.argv) == 3:
        merge(int(sys.argv[2]))
    else:
        raise SystemExit('usage: v544 ... shard INDEX TOTAL | merge TOTAL')


if __name__ == '__main__':
    main()
