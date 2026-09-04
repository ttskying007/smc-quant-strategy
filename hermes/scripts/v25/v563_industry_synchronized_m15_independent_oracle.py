#!/usr/bin/env python3
"""V563 — independent raw-bar oracle for V562's industry-synchronized M15 ontology.

This implementation deliberately does not import V562. It rebuilds eligibility from
V557's outcome-blind M15-CHOCH seeds and raw Sina M15 bars, then compares canonical
(symbol, planned daily entry date, CHOCH timestamp) identities with V562.
No price outcome, entry execution, exit, PnL, MFE, or MAE artifact is opened.
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
AUD = ROOT / 'smc_audit'
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina/m15'
V557 = AUD / 'v557_daily_demand_confirmed_m15_choch_seed_latest.json'
V562 = AUD / 'v562_industry_synchronized_m15_takeover_seed_latest.json'
INDUSTRY = AUD / 'v225_baostock_industry_participation_probe_20260627_031854' / 'baostock_stock_industry.json'
OUT = AUD / f'v563_industry_synchronized_m15_independent_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v563_industry_synchronized_m15_independent_oracle_latest.json'


def fnum(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def session_slot(timestamp: str) -> int | None:
    if len(timestamp) != 14:
        return None
    try:
        clock = int(timestamp[8:10]) * 60 + int(timestamp[10:12])
    except ValueError:
        return None
    if 585 <= clock <= 690:
        value = (clock - 570) // 15
    elif 795 <= clock <= 900:
        value = 8 + (clock - 780) // 15
    else:
        return None
    return value if 1 <= value <= 16 else None


def load_mapping() -> dict[str, str]:
    result: dict[str, str] = {}
    for row in json.loads(INDUSTRY.read_text()):
        symbol, sector = str(row.get('symbol') or ''), str(row.get('industry') or '').strip()
        if symbol and sector:
            result[symbol] = sector
    return result


def source_seeds() -> list[dict[str, str]]:
    meta = json.loads(V557.read_text())
    with Path(meta['artifacts']['confirmed_seeds']).open(newline='', encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    invalid = [
        name for name in (rows[0] if rows else {})
        if any(token in name.lower() for token in ('pnl', 'outcome', 'exit', 'mfe', 'mae', 'entry_price'))
    ]
    if invalid:
        raise RuntimeError(f'outcome-bearing source field prohibited: {invalid}')
    return rows


def path_symbol(path: Path) -> str:
    fields = path.name.split('_')
    return f'{fields[0]}.{fields[1]}' if len(fields) >= 3 else ''


def read_needed(path: Path, needed_by_date: dict[str, set[int]]) -> dict[str, list[tuple[int, float, float, float]]]:
    """date -> [(actual slot, first-available session open, close, cumulative amount)]."""
    try:
        raw = json.load(gzip.open(path, 'rt', encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    staging: dict[str, list[tuple[str, float, float, float]]] = defaultdict(list)
    for bar in raw if isinstance(raw, list) else []:
        ts = str(bar.get('t') or '')
        date = ts[:8]
        if date not in needed_by_date:
            continue
        close, volume, opened = fnum(bar.get('c')), fnum(bar.get('v')), fnum(bar.get('o'))
        if len(ts) != 14 or close is None or volume is None or opened is None:
            continue
        staging[date].append((ts, opened, close, volume))
    result: dict[str, list[tuple[int, float, float, float]]] = {}
    for date, values in staging.items():
        values.sort(key=lambda row: row[0])
        if not values:
            continue
        first_open = values[0][1]
        cumulative = 0.0
        records: list[tuple[int, float, float, float]] = []
        for ts, _, close, volume in values:
            cumulative += close * volume
            slot = session_slot(ts)
            if slot in needed_by_date[date]:
                records.append((slot, first_open, close, cumulative))
        if records:
            result[date] = records
    return result


def build_oracle_features(mapping: dict[str, str], needed_by_date: dict[str, set[int]]):
    # key=(date, slot, industry): [n, green count, total return, total amount]
    aggregate: dict[tuple[str, int, str], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    own: dict[tuple[str, str, int], tuple[float, float]] = {}
    files = sorted(RAW.glob('*_m15.json.gz'))
    observed = 0
    for ordinal, filename in enumerate(files, 1):
        symbol = path_symbol(filename)
        sector = mapping.get(symbol)
        if not sector:
            continue
        dates = read_needed(filename, needed_by_date)
        for date, records in dates.items():
            for slot, first_open, close, amount in records:
                ret = (close / first_open - 1.0) * 100.0
                bucket = aggregate[(date, slot, sector)]
                bucket[0] += 1.0
                bucket[1] += float(ret >= 0.0)
                bucket[2] += ret
                bucket[3] += amount
                own[(symbol, date, slot)] = (ret, amount)
                observed += 1
        if ordinal % 500 == 0:
            print(json.dumps({'files': ordinal, 'oracle_observed': observed}, ensure_ascii=False), flush=True)
    sector_features: dict[tuple[str, int, str], tuple[float, float, float, float]] = {}
    group_by_clock: dict[tuple[str, int], list[tuple[tuple[str, int, str], float]]] = defaultdict(list)
    for key, values in aggregate.items():
        n, green, return_sum, amount = values
        if n < 5:
            continue
        green_pct, mean_ret = 100.0 * green / n, return_sum / n
        sector_features[key] = (n, green_pct, mean_ret, amount)
        group_by_clock[(key[0], key[1])].append((key, amount))
    ranks: dict[tuple[str, int, str], float] = {}
    for _, entries in group_by_clock.items():
        for rank, (key, _) in enumerate(sorted(entries, key=lambda x: x[1], reverse=True), 1):
            ranks[key] = 100.0 * rank / len(entries)
    return sector_features, ranks, own, {'files_scanned': len(files), 'observed_stock_date_slots': observed, 'eligible_sector_date_slots': len(sector_features)}


def canonical(rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    result: dict[tuple[str, str], dict[str, str]] = {}
    for row in sorted(rows, key=lambda x: (x['planned_entry_date'], x['symbol'], x['m15_choch_time'], x.get('event_date', ''))):
        result.setdefault((row['symbol'], row['planned_entry_date']), row)
    return result


def main() -> None:
    seeds, mapping = source_seeds(), load_mapping()
    needed: dict[str, set[int]] = defaultdict(set)
    for row in seeds:
        slot = session_slot(str(row.get('m15_choch_time') or ''))
        date = str(row.get('reclaim_date') or '')
        if slot is not None and len(date) == 8:
            needed[date].add(slot)
    sector, rank, own, coverage = build_oracle_features(mapping, needed)
    accepted: list[dict[str, str]] = []
    labels = Counter()
    for row in seeds:
        symbol, date = str(row.get('symbol') or ''), str(row.get('reclaim_date') or '')
        slot = session_slot(str(row.get('m15_choch_time') or ''))
        industry = mapping.get(symbol)
        if slot is None or not industry:
            labels['MISSING_TIME_OR_INDUSTRY'] += 1
            continue
        summary = sector.get((date, slot, industry))
        stock = own.get((symbol, date, slot))
        pct_rank = rank.get((date, slot, industry))
        if summary is None or stock is None or pct_rank is None:
            labels['CROSS_SECTION_MISSING'] += 1
            continue
        _, green_pct, mean_ret, _ = summary
        stock_ret, _ = stock
        if green_pct >= 60.0 and mean_ret > 0.0 and pct_rank <= 50.0 and stock_ret >= mean_ret:
            accepted.append(row)
            labels['PASS'] += 1
        else:
            labels['REJECT_CROSS_SECTION_CONTRACT'] += 1
    oracle = canonical(accepted)
    v562 = json.loads(V562.read_text())
    with Path(v562['artifacts']['seeds']).open(newline='', encoding='utf-8') as handle:
        v562_rows = list(csv.DictReader(handle))
    subject = canonical(v562_rows)
    # Identity includes exact causal CHOCH time; canonical key equality alone is not sufficient.
    oracle_ids = {(key[0], key[1], row['m15_choch_time']) for key, row in oracle.items()}
    subject_ids = {(key[0], key[1], row['m15_choch_time']) for key, row in subject.items()}
    missing, extra = sorted(subject_ids - oracle_ids), sorted(oracle_ids - subject_ids)
    yearly = Counter(identity[1][:4] for identity in oracle_ids)
    OUT.mkdir(parents=True, exist_ok=False)
    identity_path = OUT / 'v563_oracle_identities.csv'
    with identity_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=['symbol', 'planned_entry_date', 'm15_choch_time'])
        writer.writeheader()
        writer.writerows({'symbol': s, 'planned_entry_date': d, 'm15_choch_time': t} for s, d, t in sorted(oracle_ids))
    report = {
        'version': 'V563_INDUSTRY_SYNCHRONIZED_M15_INDEPENDENT_ORACLE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'oracle_contract': 'Independent raw-bar reconstruction: exact M15 CHOCH-bar industry members>=5, green breadth>=60%, mean return>0, industry aggregate amount top half, stock return>=industry mean; canonical earliest CHOCH per symbol+planned entry.',
        'input_contract': 'V557 outcome-blind seed source only; outcome-bearing source headers rejected.',
        'oracle_identity_count': len(oracle_ids),
        'oracle_yearly_identity_count': dict(sorted(yearly.items())),
        'v562_identity_count': len(subject_ids),
        'missing_identities': len(missing),
        'extra_identities': len(extra),
        'identity_match': not missing and not extra,
        'samples': {'missing': missing[:10], 'extra': extra[:10]},
        'label_counts': dict(labels),
        'coverage': coverage,
        'invariants': {
            'no_outcome_files_read': True,
            'all_oracle_identities_before_planned_entry': all(t[:8] <= d for _, d, t in oracle_ids),
            'all_writes_false': True,
        },
        'decision': 'INDEPENDENT_ORACLE_PASS__FROZEN_STRICT_T1_REPLAY_AUTHORIZED' if not missing and not extra else 'INDEPENDENT_ORACLE_FAIL__NO_REPLAY_ALLOWED',
        'artifacts': {'out_dir': str(OUT), 'identities': str(identity_path), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v563_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
