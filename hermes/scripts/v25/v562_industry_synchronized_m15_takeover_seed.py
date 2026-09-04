#!/usr/bin/env python3
"""V562 — outcome-blind industry-synchronized volume takeover seed generator.

New ontology (not a V557 threshold/exit variant):
1) a daily demand-touch/reclaim candidate has a confirmed pre-touch M15 lower-high
   CHOCH on its reclaim session (V557 causal seed); and
2) at the *same M15 CHOCH bar*, the candidate's industry is synchronously
   participating: >=5 mapped names, >=60% green from session open, positive mean
   return, and aggregate traded value ranked in the upper half of industries; and
3) the candidate itself is at least as strong as that contemporaneous industry mean.

All cross-sectional data is cut at the exact CHOCH bar. No entry price, future bars,
PnL, exits, MFE/MAE, outcome files, or existing replay results are read.
This is a 2025-2026 source-isolated exploratory/research seed only; no production
or frontend write is possible from this script.
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
INDUSTRY = AUD / 'v225_baostock_industry_participation_probe_20260627_031854' / 'baostock_stock_industry.json'
OUT = AUD / f'v562_industry_synchronized_m15_takeover_seed_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v562_industry_synchronized_m15_takeover_seed_latest.json'


def positive(x: Any) -> float | None:
    try:
        v = float(x)
        return v if math.isfinite(v) and v > 0 else None
    except (TypeError, ValueError):
        return None


def load_industry() -> dict[str, str]:
    rows = json.loads(INDUSTRY.read_text())
    out: dict[str, str] = {}
    for row in rows if isinstance(rows, list) else []:
        symbol = str(row.get('symbol') or '')
        industry = str(row.get('industry') or '').strip()
        if symbol and industry:
            out[symbol] = industry
    return out


def symbol_from_path(path: Path) -> str:
    parts = path.name.split('_')
    return f'{parts[0]}.{parts[1]}' if len(parts) >= 3 else ''


def read_seed_rows() -> list[dict[str, str]]:
    meta = json.loads(V557.read_text())
    path = Path(meta['artifacts']['confirmed_seeds'])
    with path.open(newline='', encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    forbidden = [
        field for field in (rows[0] if rows else {})
        if any(word in field.lower() for word in ('pnl', 'outcome', 'exit', 'mfe', 'mae', 'winner', 'loser', 'entry_price'))
    ]
    if forbidden:
        raise RuntimeError(f'forbidden source fields in V557 input: {forbidden}')
    return rows


def slot_for_timestamp(raw: str) -> int | None:
    """Return Sina's actual A-share 15m closing-bar slot (09:45..11:30, 13:15..15:00)."""
    if len(raw) != 14:
        return None
    try:
        minute = int(raw[8:10]) * 60 + int(raw[10:12])
    except ValueError:
        return None
    if 9 * 60 + 45 <= minute <= 11 * 60 + 30:
        slot = (minute - (9 * 60 + 30)) // 15
    elif 13 * 60 + 15 <= minute <= 15 * 60:
        slot = 8 + (minute - (13 * 60)) // 15
    else:
        return None
    return slot if 1 <= slot <= 16 else None


def exact_slot(seed: dict[str, str]) -> int | None:
    return slot_for_timestamp(str(seed.get('m15_choch_time') or ''))


def build_requests(seeds: list[dict[str, str]]) -> tuple[dict[str, set[int]], Counter]:
    needed: dict[str, set[int]] = defaultdict(set)
    rejects: Counter = Counter()
    for seed in seeds:
        date = str(seed.get('reclaim_date') or '')
        slot = exact_slot(seed)
        if len(date) != 8 or slot is None or not 1 <= slot <= 16:
            rejects['INVALID_CHOCH_TIMESTAMP'] += 1
            continue
        needed[date].add(slot)
    return needed, rejects


def bars_for_needed_dates(path: Path, needed: dict[str, set[int]]) -> dict[str, list[dict[str, float]]]:
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return {}
    out: dict[str, list[dict[str, float]]] = defaultdict(list)
    for bar in raw if isinstance(raw, list) else []:
        timestamp = str(bar.get('t') or '')
        date = timestamp[:8]
        if date not in needed or len(timestamp) != 14:
            continue
        o, h, l, c, v = (positive(bar.get(k)) for k in ('o', 'h', 'l', 'c', 'v'))
        if None in (o, h, l, c, v):
            continue
        out[date].append({'t': timestamp, 'o': o, 'h': h, 'l': l, 'c': c, 'v': v})
    for rows in out.values():
        rows.sort(key=lambda row: row['t'])
    return out


def build_cross_sectional(
    industry_map: dict[str, str], needed: dict[str, set[int]]
) -> tuple[dict[tuple[str, int, str], dict[str, float]], dict[tuple[str, int, str], dict[str, float]], dict[str, int]]:
    # Accumulator values: members, green, summed returns, and traded amount through the exact slot.
    agg: dict[tuple[str, int, str], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    stock: dict[tuple[str, int, str], dict[str, float]] = {}
    coverage = Counter()
    files = sorted(RAW.glob('*_m15.json.gz'))
    for number, path in enumerate(files, 1):
        symbol = symbol_from_path(path)
        industry = industry_map.get(symbol)
        if not industry:
            continue
        daily = bars_for_needed_dates(path, needed)
        for date, rows in daily.items():
            if not rows:
                continue
            open0 = rows[0]['o']
            cumulative_amount = 0.0
            requested = needed[date]
            for bar in rows:
                slot = slot_for_timestamp(str(bar['t']))
                cumulative_amount += bar['c'] * bar['v']
                if slot is None or slot not in requested:
                    continue
                ret = 100.0 * (bar['c'] / open0 - 1.0)
                key = (date, slot, industry)
                a = agg[key]
                a[0] += 1.0
                a[1] += float(ret >= 0)
                a[2] += ret
                a[3] += cumulative_amount
                stock[(symbol, slot, date)] = {
                    'stock_ret_pct': ret,
                    'stock_amount': cumulative_amount,
                    'stock_slot': float(slot),
                }
                coverage['stock_date_slot_features'] += 1
        if number % 500 == 0:
            print(json.dumps({'files': number, 'feature_rows': coverage['stock_date_slot_features']}, ensure_ascii=False), flush=True)
    # Reduce per-industry features, then rank only among industries observable at the same date/slot.
    features: dict[tuple[str, int, str], dict[str, float]] = {}
    per_time: dict[tuple[str, int], list[tuple[tuple[str, int, str], dict[str, float]]]] = defaultdict(list)
    for key, (members, green, ret_sum, amount) in agg.items():
        if members < 5:
            continue
        f = {
            'industry_members': members,
            'industry_green_pct': 100.0 * green / members,
            'industry_mean_ret_pct': ret_sum / members,
            'industry_amount': amount,
        }
        features[key] = f
        per_time[(key[0], key[1])].append((key, f))
    for _, items in per_time.items():
        ordered = sorted(items, key=lambda pair: pair[1]['industry_amount'], reverse=True)
        total = len(ordered)
        for rank, (key, f) in enumerate(ordered, 1):
            f['industry_amount_rank_pct'] = 100.0 * rank / total
            f['industry_universe_count'] = float(total)
    coverage['m15_files_scanned'] = len(files)
    coverage['industry_date_slot_features'] = len(features)
    coverage['industry_map_symbols'] = len(industry_map)
    return features, stock, dict(coverage)


def main() -> None:
    seeds = read_seed_rows()
    needed, timestamp_rejects = build_requests(seeds)
    industry_map = load_industry()
    OUT.mkdir(parents=True, exist_ok=False)
    feature, stock, coverage = build_cross_sectional(industry_map, needed)
    labels: Counter = Counter(timestamp_rejects)
    chosen: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    for seed in seeds:
        date = str(seed.get('reclaim_date') or '')
        slot = exact_slot(seed)
        symbol = str(seed.get('symbol') or '')
        industry = industry_map.get(symbol, '')
        if slot is None or not industry:
            label = 'NO_PIT_FROZEN_INDUSTRY_MAPPING' if not industry else 'INVALID_CHOCH_TIMESTAMP'
            labels[label] += 1
            all_rows.append({**seed, 'v562_label': label})
            continue
        ind = feature.get((date, slot, industry))
        own = stock.get((symbol, slot, date))
        if ind is None or own is None:
            label = 'M15_CROSS_SECTION_MISSING'
        elif ind['industry_green_pct'] < 60.0:
            label = 'INDUSTRY_BREADTH_BELOW_60'
        elif ind['industry_mean_ret_pct'] <= 0.0:
            label = 'INDUSTRY_MEAN_RETURN_NONPOSITIVE'
        elif ind['industry_amount_rank_pct'] > 50.0:
            label = 'INDUSTRY_AMOUNT_NOT_TOP_HALF'
        elif own['stock_ret_pct'] < ind['industry_mean_ret_pct']:
            label = 'STOCK_NOT_PARTICIPATING_ABOVE_INDUSTRY_MEAN'
        else:
            label = 'INDUSTRY_SYNCHRONIZED_VOLUME_TAKEOVER'
        labels[label] += 1
        row: dict[str, Any] = {
            **seed,
            'ontology': 'DAILY_DEMAND_M15_CHOCH__INDUSTRY_SYNCHRONIZED_VOLUME_TAKEOVER',
            'v562_label': label,
            'industry': industry,
            'm15_choch_slot': slot,
            'no_outcome_fields': 'true',
            'tradable': 'false',
            'buy_enabled': 'false',
        }
        if ind:
            row.update({key: round(value, 8) for key, value in ind.items()})
        if own:
            row.update({key: round(value, 8) for key, value in own.items()})
        if label == 'INDUSTRY_SYNCHRONIZED_VOLUME_TAKEOVER':
            chosen.append(row)
        all_rows.append(row)
    # A daily candidate identity is symbol + executable next daily open.  Several
    # upstream BOS histories can converge on that same open; retain only the
    # earliest exact-session CHOCH provenance, never multiply it into trades.
    chosen.sort(key=lambda row: (str(row['planned_entry_date']), str(row['symbol']), str(row['m15_choch_time']), str(row.get('event_date') or '')))
    canonical: dict[tuple[str, str], dict[str, Any]] = {}
    for row in chosen:
        canonical.setdefault((str(row['symbol']), str(row['planned_entry_date'])), row)
    duplicate_lineages_removed = len(chosen) - len(canonical)
    chosen = sorted(canonical.values(), key=lambda row: (str(row['planned_entry_date']), str(row['symbol']), str(row['m15_choch_time'])))
    yearly = Counter(str(row['planned_entry_date'])[:4] for row in chosen)
    unique = len(chosen)
    support = len(chosen) >= 1000 and yearly.get('2025', 0) >= 300 and yearly.get('2026', 0) >= 300
    fields = sorted({key for row in all_rows for key in row})
    for name, rows in [('v562_all_m15_choch_industry_rows.csv', all_rows), ('v562_outcome_blind_seeds.csv', chosen)]:
        with (OUT / name).open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)
    report = {
        'version': 'V562_INDUSTRY_SYNCHRONIZED_M15_TAKEOVER_SEED_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'scope': 'SINA_SOURCE_ISOLATED_PARTIAL_2025_2026__EXPLORATORY_RESEARCH_ONLY',
        'frozen_ontology': 'daily demand BOS/touch/reclaim -> confirmed pre-touch M15 lower-high CHOCH -> exact-CHOCH-bar industry breadth>=60%, mean return>0, aggregate amount top half, and stock return>=industry mean -> following daily open eligibility',
        'information_dimension': 'Cross-sectional contemporaneous industry breadth plus aggregate traded-value participation at the exact M15 structural confirmation bar; no later same-session bar is used.',
        'input_contract': 'V557 outcome-blind confirmed M15 CHOCH seeds only; forbidden outcome headers are rejected before processing.',
        'industry_mapping_contract': 'Frozen local Baostock industry classification snapshot dated 2026-06-22; research-only classification witness, not PIT production authorization.',
        'seed_count': len(chosen),
        'yearly_seed_count': dict(sorted(yearly.items())),
        'unique_symbol_planned_entry_count': unique,
        'duplicate_upstream_lineages_removed': duplicate_lineages_removed,
        'label_counts': dict(labels),
        'coverage': coverage,
        'support_gate': {
            'aggregate_n_min': 1000,
            'each_available_year_min': 300,
            'available_years': ['2025', '2026'],
            'pass': support,
        },
        'invariants': {
            'no_outcome_files_read': True,
            'all_candidates_nontradable': all(row.get('tradable', 'false') == 'false' and row.get('buy_enabled', 'false') == 'false' for row in all_rows),
            'all_selected_choch_before_planned_entry': all(str(row['m15_choch_time'])[:8] <= str(row['reclaim_date']) < str(row['planned_entry_date']) for row in chosen),
            'all_selected_have_exact_choch_slot': all(1 <= int(row['m15_choch_slot']) <= 16 for row in chosen),
            'no_later_session_bar_used_by_contract': True,
            'no_production_write': True,
        },
        'decision': 'OUTCOME_BLIND_SEED_SUPPORT_PASS__INDEPENDENT_ORACLE_REQUIRED_NEXT' if support else 'PRE_OUTCOME_SUPPORT_FAIL__NO_REPLAY_ALLOWED',
        'artifacts': {
            'out_dir': str(OUT),
            'all_rows': str(OUT / 'v562_all_m15_choch_industry_rows.csv'),
            'seeds': str(OUT / 'v562_outcome_blind_seeds.csv'),
            'latest': str(LATEST),
        },
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v562_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
