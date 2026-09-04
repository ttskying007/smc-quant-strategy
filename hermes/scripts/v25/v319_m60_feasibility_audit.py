#!/usr/bin/env python3
"""V319 no-write audit: 60min data feasibility for V185/V167 full-history promotion.

After V315-V318 closed daily row-filter/exit/candidate-supply branches, this checks
whether the next required information source (60min entry refinement) is actually
available locally for full 2023-2026 validation. It does not write production,
frontend, or watchlist files.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
K60 = ROOT / 'kline_cache_60min'
AUDIT = ROOT / 'smc_audit'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUTDIR = AUDIT / f'v319_m60_feasibility_no_write_{TS}'
LATEST = AUDIT / 'v319_m60_feasibility_latest.json'
DATASETS = {
    'V185': ROOT / 'smc_opt_v185_combined_production_candidate' / 'v185_trades.json',
    'V167': ROOT / 'smc_opt_v167_exact_scanner_gate' / 'v167_trades.json',
}


def dkey(v) -> str:
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def load60(symbol: str):
    if not symbol or '.' not in symbol:
        return []
    code, exch = symbol.split('.')
    p = K60 / f'{code}_{exch}_60min_500.json'
    if not p.exists():
        return []
    try:
        data = json.load(open(p))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def audit_dataset(name: str, path: Path):
    rows = json.load(open(path))
    by_year = Counter(); hit_year = Counter(); cache_year = Counter()
    missing_examples = []
    ranges = []
    cache_exist = 0
    entry_hit_rows = []
    for r in rows:
        sym = r.get('symbol')
        ed = dkey(r.get('entry_date'))
        y = ed[:4]
        by_year[y] += 1
        bars = load60(sym)
        if bars:
            cache_exist += 1
            cache_year[y] += 1
            ds = [dkey(b.get('t')) for b in bars]
            ranges.append({'symbol': sym, 'first': ds[0], 'last': ds[-1], 'bars': len(ds)})
            if ed in set(ds):
                hit_year[y] += 1
                entry_hit_rows.append({'symbol': sym, 'entry_date': ed, 'source': r.get('v185_source') or r.get('engine')})
            elif len(missing_examples) < 20:
                missing_examples.append({'symbol': sym, 'entry_date': ed, 'm60_first': ds[0], 'm60_last': ds[-1], 'reason': 'ENTRY_DATE_OUTSIDE_LOCAL_60MIN_RANGE'})
        elif len(missing_examples) < 20:
            missing_examples.append({'symbol': sym, 'entry_date': ed, 'reason': 'NO_LOCAL_60MIN_CACHE'})
    year_table = {}
    for y in sorted(by_year):
        n = by_year[y]
        year_table[y] = {
            'rows': n,
            'symbol_cache_exists': cache_year[y],
            'entry_date_hit': hit_year[y],
            'entry_date_hit_pct': round(hit_year[y] / n * 100, 2) if n else 0,
        }
    firsts = [r['first'] for r in ranges if r.get('first')]
    lasts = [r['last'] for r in ranges if r.get('last')]
    return {
        'dataset': name,
        'input': str(path),
        'rows': len(rows),
        'symbol_cache_exists': cache_exist,
        'symbol_cache_exists_pct': round(cache_exist / len(rows) * 100, 2) if rows else 0,
        'entry_date_hit': sum(hit_year.values()),
        'entry_date_hit_pct': round(sum(hit_year.values()) / len(rows) * 100, 2) if rows else 0,
        'year_coverage': year_table,
        'local_60min_global_first': min(firsts) if firsts else '',
        'local_60min_global_last': max(lasts) if lasts else '',
        'range_examples': ranges[:8],
        'entry_hit_examples': entry_hit_rows[:20],
        'missing_examples': missing_examples,
    }


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    datasets = {name: audit_dataset(name, path) for name, path in DATASETS.items()}
    gates = {
        'full_history_entry_hit_pct_required': 95.0,
        'per_year_entry_hit_pct_required': 90.0,
        'min_years_required': ['2023', '2024', '2025', '2026'],
    }
    feasible = True
    reasons = []
    for name, d in datasets.items():
        if d['entry_date_hit_pct'] < gates['full_history_entry_hit_pct_required']:
            feasible = False; reasons.append(f"{name} full-history hit {d['entry_date_hit_pct']}% < 95%")
        for y in gates['min_years_required']:
            yp = d['year_coverage'].get(y, {}).get('entry_date_hit_pct', 0)
            if yp < gates['per_year_entry_hit_pct_required']:
                feasible = False; reasons.append(f"{name} {y} hit {yp}% < 90%")
    report = {
        'version': 'V319_M60_FEASIBILITY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'k60_dir': str(K60),
        'gates': gates,
        'datasets': datasets,
        'feasible_for_full_2023_2026_m60_backtest': feasible,
        'failure_reasons': reasons,
        'decision': 'M60_FULL_HISTORY_FEASIBLE__NEXT_BUILD_ENTRY_MATRIX' if feasible else 'M60_LOCAL_CACHE_NOT_FULL_HISTORY__DO_NOT_CLAIM_M60_PROMOTION',
        'next_required': 'Acquire/construct complete historical intraday data for 2023-2026 before any M60 entry/SL/RR promotion claim; current cache can only support recent smoke diagnostics.',
        'artifacts': {'report': str(OUTDIR / 'v319_report.json'), 'latest': str(LATEST)},
    }
    json.dump(report, open(OUTDIR / 'v319_report.json', 'w'), ensure_ascii=False, indent=2)
    json.dump(report, open(LATEST, 'w'), ensure_ascii=False, indent=2)
    print(json.dumps({'latest': str(LATEST), 'decision': report['decision'], 'feasible': feasible, 'datasets': {k: {'rows': v['rows'], 'entry_date_hit': v['entry_date_hit'], 'entry_date_hit_pct': v['entry_date_hit_pct'], 'year_coverage': v['year_coverage'], 'range': [v['local_60min_global_first'], v['local_60min_global_last']]} for k,v in datasets.items()}, 'failure_reasons': reasons[:8]}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
