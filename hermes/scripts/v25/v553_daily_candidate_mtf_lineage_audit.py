#!/usr/bin/env python3
"""V553 no-outcome lineage audit: original daily supply -> m15 confirmation.

Purpose
-------
Answer whether the old daily-only rules discarded candidates that lower-timeframe
confirmation could validate.  This is deliberately a lineage audit, not a
backtest and not a new trading strategy:

* regenerate the broad V262-style daily BOS -> bearish-demand -> reclaim supply
  from the same Sina daily/m15 source;
* record the first exact daily stage at which each BOS event is rejected;
* label each valid daily candidate with a pre-entry m15 zone-touch/reclaim/MSS
  observation on its daily reclaim session;
* compare identities only (symbol + planned entry date) with the old selected
  daily baseline.  No PnL, exit, return, target, stop or future bar is read.

All m15 evidence is at or before the daily reclaim close.  The proposed entry
is the following daily open, so this script cannot promote, trade, or evaluate
an outcome.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina'
AUDIT = ROOT / 'smc_audit'
OLD_SELECTED = ROOT / 'smc_audit/v248_v246_independent_audit_no_write_20260701_172916/v248_recomputed_selected_rows.csv'
OLD_V548 = ROOT / 'smc_audit/v548_htf_trend_m15_entry_seed_gate_latest.json'
OUT = AUDIT / f'v553_daily_candidate_mtf_lineage_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v553_daily_candidate_mtf_lineage_latest.json'
YEARS = {'2025', '2026'}

# These are the original V262 daily eligibility semantics, not optimized values.
DAILY_BOS_LOOKBACK = 20
DAILY_DEMAND_BACK = 8
DAILY_RECLAIM_MAX = 7
MIN_RISK_PCT = 0.8
MAX_RISK_PCT = 12.0


def positive(value: Any) -> float | None:
    try:
        value = float(value)
        return value if math.isfinite(value) and value > 0 else None
    except (TypeError, ValueError):
        return None


def load(path: Path, frame: str) -> list[dict[str, Any]]:
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return []
    rows = []
    for row in raw if isinstance(raw, list) else []:
        stamp = str(row.get('t') or '')
        date = str(row.get('d') or stamp[:8])[:8]
        values = [positive(row.get(key)) for key in ('o', 'h', 'l', 'c')]
        if frame == 'm15':
            valid = len(stamp) == 14
        else:
            valid = len(date) == 8
        if valid and len(date) == 8 and all(value is not None for value in values):
            rows.append({'t': stamp if frame == 'm15' else date, 'd': date,
                         'o': values[0], 'h': values[1], 'l': values[2], 'c': values[3]})
    return sorted(rows, key=lambda item: item['t'])


def old_selected_keys() -> set[tuple[str, str]]:
    """Read only identity columns; never load old outcome columns."""
    keys: set[tuple[str, str]] = set()
    try:
        with OLD_SELECTED.open(newline='', encoding='utf-8') as handle:
            for row in csv.DictReader(handle):
                symbol = str(row.get('symbol') or '')
                date = ''.join(ch for ch in str(row.get('entry_date') or '') if ch.isdigit())[:8]
                if symbol and len(date) == 8:
                    keys.add((symbol, date))
    except OSError:
        pass
    return keys


def m15_label(rows: list[dict[str, Any]], zone_low: float, zone_high: float) -> tuple[str, dict[str, str]]:
    """Classify same-session evidence without using bars after daily reclaim day."""
    if len(rows) < 4:
        return 'M15_MISSING_OR_SHORT_SESSION', {}
    touch = next((i for i, bar in enumerate(rows) if bar['l'] <= zone_high and bar['h'] >= zone_low), None)
    if touch is None:
        return 'M15_NO_ZONE_TOUCH', {}
    reclaim = next((i for i in range(touch, len(rows)) if rows[i]['c'] >= zone_high), None)
    if reclaim is None:
        return 'M15_TOUCH_NO_RECLAIM', {'m15_touch_time': rows[touch]['t']}
    pre_high = max(bar['h'] for bar in rows[:touch + 1])
    mss = next((i for i in range(reclaim + 1, len(rows)) if rows[i]['c'] > pre_high * 1.001), None)
    if mss is None:
        return 'M15_RECLAIM_NO_MSS', {'m15_touch_time': rows[touch]['t'], 'm15_reclaim_time': rows[reclaim]['t']}
    if any(bar['c'] < zone_low for bar in rows[mss:]):
        return 'M15_MSS_THEN_ZONE_FAIL', {'m15_touch_time': rows[touch]['t'], 'm15_reclaim_time': rows[reclaim]['t'], 'm15_mss_time': rows[mss]['t']}
    return 'M15_TAKEOVER_CONFIRMED', {'m15_touch_time': rows[touch]['t'], 'm15_reclaim_time': rows[reclaim]['t'], 'm15_mss_time': rows[mss]['t']}


def scan_symbol(path: Path, old_keys: set[tuple[str, str]]) -> tuple[Counter, list[dict[str, Any]], str | None]:
    symbol = path.name.removesuffix('_daily.json.gz').replace('_', '.')
    daily = load(path, 'daily')
    m15_path = RAW / 'm15' / path.name.replace('_daily.json.gz', '_m15.json.gz')
    m15 = load(m15_path, 'm15')
    if len(daily) < DAILY_BOS_LOOKBACK + DAILY_RECLAIM_MAX + 2:
        return Counter({'SHORT_DAILY_SOURCE': 1}), [], 'short_daily'
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for bar in m15:
        by_day[bar['d']].append(bar)
    stages: Counter = Counter()
    rows: list[dict[str, Any]] = []
    for event_i in range(DAILY_BOS_LOOKBACK, len(daily) - 1):
        event = daily[event_i]
        if event['d'][:4] not in YEARS or event['c'] <= event['o']:
            continue
        previous_high = max(bar['h'] for bar in daily[event_i - DAILY_BOS_LOOKBACK:event_i])
        if event['c'] <= previous_high:
            continue
        stages['DAILY_BOS_EVENT'] += 1
        demand_i = next((i for i in range(event_i - 1, max(-1, event_i - DAILY_DEMAND_BACK - 1), -1) if daily[i]['c'] < daily[i]['o']), None)
        if demand_i is None:
            stages['REJECT_NO_PRE_EVENT_BEARISH_DEMAND'] += 1
            continue
        demand = daily[demand_i]
        zone_low = demand['l']
        zone_high = max(demand['o'], demand['c'])
        reclaim_i = None
        for i in range(event_i + 1, min(event_i + DAILY_RECLAIM_MAX + 1, len(daily) - 1)):
            bar = daily[i]
            touched = bar['l'] <= zone_high * 1.005
            reclaimed = bar['c'] >= zone_high and bar['c'] > bar['o'] and (bar['c'] - bar['l']) / max(bar['h'] - bar['l'], 1e-12) >= 0.55
            if touched and reclaimed:
                reclaim_i = i
                break
        if reclaim_i is None:
            stages['REJECT_NO_DAILY_ZONE_TOUCH_RECLAIM_IN_7'] += 1
            continue
        entry_i = reclaim_i + 1
        entry = daily[entry_i]['o']
        stop = zone_low * 0.99
        risk_pct = (entry / stop - 1) * 100
        if not MIN_RISK_PCT <= risk_pct <= MAX_RISK_PCT:
            stages['REJECT_DAILY_RISK_GATE'] += 1
            continue
        stages['DAILY_CANDIDATE_AFTER_OLD_RULES'] += 1
        label, evidence = m15_label(by_day.get(daily[reclaim_i]['d'], []), zone_low, zone_high)
        stages[label] += 1
        key = (symbol, daily[entry_i]['d'])
        rows.append({
            'symbol': symbol,
            'event_date': event['d'], 'zone_date': demand['d'], 'reclaim_date': daily[reclaim_i]['d'],
            'planned_entry_date': daily[entry_i]['d'], 'daily_event_index': event_i,
            'daily_zone_index': demand_i, 'daily_reclaim_index': reclaim_i,
            'zone_low': round(zone_low, 6), 'zone_high': round(zone_high, 6),
            'planned_entry_open': round(entry, 6), 'structural_stop': round(stop, 6),
            'risk_pct': round(risk_pct, 4), 'm15_confirmation_label': label,
            'old_daily_selected_identity_match': key in old_keys,
            **evidence,
        })
    return stages, rows, None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=False)
    old_keys = old_selected_keys()
    aggregate: Counter = Counter()
    candidates: list[dict[str, Any]] = []
    failures: Counter = Counter()
    paths = sorted((RAW / 'daily').glob('*_daily.json.gz'))
    for number, path in enumerate(paths, 1):
        stages, rows, error = scan_symbol(path, old_keys)
        aggregate.update(stages)
        candidates.extend(rows)
        if error:
            failures[error] += 1
        if number % 500 == 0:
            print(json.dumps({'symbols': number, 'daily_candidates': len(candidates)}, ensure_ascii=False), flush=True)

    candidates.sort(key=lambda row: (row['planned_entry_date'], row['symbol']))
    labels = Counter(row['m15_confirmation_label'] for row in candidates)
    old_match = Counter('OLD_DAILY_SELECTED' if row['old_daily_selected_identity_match'] else 'OLD_DAILY_NOT_SELECTED' for row in candidates)
    cross = Counter((('OLD_DAILY_SELECTED' if row['old_daily_selected_identity_match'] else 'OLD_DAILY_NOT_SELECTED'), row['m15_confirmation_label']) for row in candidates)
    years = Counter(row['planned_entry_date'][:4] for row in candidates)
    csv_path = OUT / 'v553_daily_candidate_mtf_lineage.csv'
    fields = list(candidates[0]) if candidates else ['symbol', 'planned_entry_date']
    with csv_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(candidates)
    report = {
        'version': 'V553_DAILY_CANDIDATE_MTF_LINEAGE_AUDIT_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'purpose': 'Trace original daily candidate attrition and attach an independent same-session m15 confirmation label; no outcomes are read.',
        'source_contract': 'Sina source-isolated daily/m15 cache only, 2025-2026 partial range; no cross-source substitution.',
        'old_daily_contract_reconstructed': {
            'daily_BOS': 'bullish close above prior 20-session high',
            'daily_demand': 'nearest bearish candle in preceding 8 sessions',
            'daily_reclaim': 'first zone touch + bullish reclaim within next 7 sessions',
            'daily_risk_gate_pct': [MIN_RISK_PCT, MAX_RISK_PCT],
            'entry': 'following daily open',
        },
        'm15_label_contract': 'On the daily reclaim date only: daily-zone touch -> close reclaim above zone high -> later m15 close breaks pre-touch high -> no later m15 close below zone low. This label does not require V548 weekly trend, SSL sweep, volume, FVG, or its timing windows.',
        'invariants': {
            'no_outcome_files_read': True,
            'all_candidate_entries_after_reclaim': all(row['planned_entry_date'] > row['reclaim_date'] for row in candidates),
            'all_m15_evidence_on_or_before_reclaim': all((not row.get('m15_mss_time')) or row['m15_mss_time'][:8] == row['reclaim_date'] for row in candidates),
            'old_selected_identity_read_only': True,
        },
        'coverage': {'daily_symbols_scanned': len(paths), 'source_failures': dict(failures), 'old_selected_identity_keys_read': len(old_keys)},
        'daily_stage_attrition': dict(aggregate),
        'candidate_count': len(candidates), 'candidate_year_counts': dict(years),
        'm15_confirmation_counts': dict(labels),
        'old_selection_identity_counts': dict(old_match),
        'old_selection_x_m15_confirmation': [
            {'old_selection': old, 'm15_confirmation': label, 'n': count}
            for (old, label), count in sorted(cross.items())
        ],
        'interpretation_boundary': 'M15_TAKEOVER_CONFIRMED means a formerly daily-only candidate has independent pre-entry lower-timeframe structural evidence. It is not an outcome claim, a quality claim, or production authorization.',
        'artifacts': {'out_dir': str(OUT), 'candidate_lineage_csv': str(csv_path), 'latest': str(LATEST)},
        'decision': 'LINEAGE_AUDIT_COMPLETE__NO_OUTCOME_REPLAY__NO_PRODUCTION_WRITE',
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v553_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
