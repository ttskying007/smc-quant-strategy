#!/usr/bin/env python3
"""No-outcome semantic audit of the V539 15m SSL->BOS->FVG candidate contract.

This does not evaluate returns or alter strategy code.  It checks whether a
recorded "reclaim" is actually the *first* post-FVG zone touch, and measures
identity collisions that make a state-machine candidate non-executable.
"""
from __future__ import annotations

import csv
import gzip
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina/m15'
SEED_REPORT = AUDIT / 'v539_sina_m15_ssl_bos_fvg_seed_gate_latest.json'
OUT = AUDIT / 'v602_v539_smc_semantic_lifecycle_audit_latest.json'


def load_bars(symbol: str) -> list[dict]:
    path = RAW / f'{symbol.replace(".", "_")}_m15.json.gz'
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return []
    bars = []
    for row in raw if isinstance(raw, list) else []:
        try:
            t = str(row['t'])
            bars.append({'t': t, 'h': float(row['h']), 'l': float(row['l']), 'c': float(row['c'])})
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(bars, key=lambda row: row['t'])


def pct(n: int, d: int) -> float:
    return round(100 * n / d, 4) if d else 0.0


def main() -> None:
    report = json.loads(SEED_REPORT.read_text())
    with Path(report['artifacts']['seeds']).open(encoding='utf-8', newline='') as handle:
        seeds = list(csv.DictReader(handle))

    by_symbol: dict[str, list[dict]] = defaultdict(list)
    identities = Counter()
    for row in seeds:
        by_symbol[row['symbol']].append(row)
        identities[(row['symbol'], row['entry_date'])] += 1

    status = Counter()
    samples: list[dict] = []
    checked = 0
    for symbol, group in sorted(by_symbol.items()):
        bars = load_bars(symbol)
        ix = {bar['t']: i for i, bar in enumerate(bars)}
        for seed in group:
            fvg_i = ix.get(seed['fvg_time'])
            reclaim_i = ix.get(seed['reclaim_time'])
            if fvg_i is None or reclaim_i is None or reclaim_i <= fvg_i:
                status['MISSING_OR_INVALID_TIME_IDENTITY'] += 1
                continue
            low, high = float(seed['fvg_low']), float(seed['fvg_high'])
            prior_touch = None
            for i in range(fvg_i + 1, reclaim_i):
                bar = bars[i]
                if bar['l'] <= high and bar['h'] >= low:
                    prior_touch = i
                    break
            checked += 1
            if prior_touch is None:
                status['FIRST_TOUCH_IS_RECORDED_RECLAIM'] += 1
                continue
            status['EARLIER_ZONE_TOUCH_BEFORE_RECORDED_RECLAIM'] += 1
            if len(samples) < 20:
                samples.append({
                    'symbol': symbol,
                    'fvg_time': seed['fvg_time'],
                    'first_prior_touch': bars[prior_touch]['t'],
                    'recorded_reclaim': seed['reclaim_time'],
                    'fvg_low': low,
                    'fvg_high': high,
                    'prior_touch_close': bars[prior_touch]['c'],
                })

    entry_counts = list(identities.values())
    duplicate_identities = sum(count > 1 for count in entry_counts)
    duplicate_excess = sum(count - 1 for count in entry_counts if count > 1)
    output = {
        'version': 'V602_V539_SEMANTIC_LIFECYCLE_AUDIT_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'input_contract': 'V539 outcome-blind seed identities plus same-source Sina m15 OHLC; no outcome/trade/PnL/stop/target data.',
        'tested_invariants': {
            'recorded_reclaim_must_be_first_post_fvg_zone_touch': 'A later reclaim after an earlier touch is mitigation-consumed, not a first-retest setup.',
            'one_symbol_one_entry_date': 'Multiple independent state machines cannot emit multiple actionable buys for the same symbol/session.',
        },
        'seed_count': len(seeds),
        'symbols': len(by_symbol),
        'reclaim_lifecycle': {
            'checked': checked,
            'first_touch_is_recorded_reclaim': status['FIRST_TOUCH_IS_RECORDED_RECLAIM'],
            'first_touch_is_recorded_reclaim_pct': pct(status['FIRST_TOUCH_IS_RECORDED_RECLAIM'], checked),
            'earlier_touch_before_recorded_reclaim': status['EARLIER_ZONE_TOUCH_BEFORE_RECORDED_RECLAIM'],
            'earlier_touch_before_recorded_reclaim_pct': pct(status['EARLIER_ZONE_TOUCH_BEFORE_RECORDED_RECLAIM'], checked),
            'invalid_or_missing_identity': status['MISSING_OR_INVALID_TIME_IDENTITY'],
            'samples': samples,
        },
        'execution_identity': {
            'unique_symbol_entry_dates': len(identities),
            'duplicate_symbol_entry_dates': duplicate_identities,
            'duplicate_excess_candidates': duplicate_excess,
            'max_candidates_per_symbol_entry_date': max(entry_counts) if entry_counts else 0,
            'median_candidates_per_symbol_entry_date': median(entry_counts) if entry_counts else 0,
        },
        'semantic_decision': (
            'V539_STATE_MACHINE_SEMANTICS_FAIL__DO_NOT_REPLAY_OR_PROMOTE__'
            'REBUILD_SINGLE_CHAIN_FIRST_TOUCH_INVALIDATION_AND_SINGLE_ACTIVE_STATE'
            if status['EARLIER_ZONE_TOUCH_BEFORE_RECORDED_RECLAIM'] or duplicate_excess else
            'V539_SEMANTIC_LIFECYCLE_PASS__INDEPENDENT_ORACLE_NEXT'
        ),
    }
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
