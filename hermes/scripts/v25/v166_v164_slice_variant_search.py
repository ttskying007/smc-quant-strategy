#!/usr/bin/env python3
"""V166: search non-outcome V164 scanner-time slices across outcome variants.

Read-only. No production/frontend/watchlist writes.

V165 found V164 is economically unusable as a whole and only has research-usable
sub-slices under 0.5R. V166 checks whether any scanner-time slice becomes truly
production-usable after varying TP/SL/hold rules, using only fields already
available in V164 dry-run rows.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any, Callable

ROOT = Path('/root/.hermes')
IN = ROOT / 'smc_audit' / 'v164_corrected_scanner_dry_run_20260622' / 'v164_dryrun_rows.json'
OUT = ROOT / 'smc_audit' / 'v166_v164_slice_variant_search_20260623'
OUT.mkdir(parents=True, exist_ok=True)
ENGINE = 'V166_V164_SLICE_VARIANT_SEARCH'

PROD = {'n': 200, 'min_year_n': 35, 'wr': 82.0, 'avg': 3.0, 'micro_pct': 1.0}
RESEARCH = {'n': 80, 'min_year_n': 15, 'wr': 72.0, 'avg': 1.5}


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return default
        if isinstance(v, str) and not v.strip():
            return default
        return float(v)
    except Exception:
        return default


def bval(v: Any) -> bool:
    return str(v).strip().lower() in {'true', '1', 'yes'}


def date_key(b: dict[str, Any]) -> str:
    return str(b.get('t') or b.get('date') or '').replace('-', '')[:8]


def kline_path(symbol: str) -> Path:
    code, ex = symbol.split('.')
    return ROOT / 'kline_cache' / f'{code}_{ex}_daily_750.json'


def load_bars(symbol: str) -> list[dict[str, Any]]:
    p = kline_path(symbol)
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text(encoding='utf-8'))
        return d if isinstance(d, list) else []
    except Exception:
        return []


def locate(bars: list[dict[str, Any]], entry_date: str) -> int:
    ed = str(entry_date).replace('-', '')[:8]
    for i, b in enumerate(bars):
        if date_key(b) == ed:
            return i
    return -1


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    vals = [fnum(r['pnl_pct']) for r in rows]
    n = len(vals)
    if not n:
        return {'n': 0, 'wr': 0.0, 'avg': 0.0, 'median': 0.0, 'loss_n': 0, 'micro_pct': 0.0, 'min_year_n': 0, 'year_counts': {}, 'year_wr': {}, 't1': 0}
    ym: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        y = str(r.get('entry_date'))[:4]
        if y >= '2023':  # production robustness window; 2017 rows are stale cache anomalies.
            ym[y].append(fnum(r['pnl_pct']))
    yc = {y: len(v) for y, v in sorted(ym.items())}
    yw = {y: round(sum(x > 0 for x in v) / len(v) * 100, 2) for y, v in sorted(ym.items()) if v}
    return {
        'n': n,
        'wr': round(sum(x > 0 for x in vals) / n * 100, 2),
        'avg': round(sum(vals) / n, 4),
        'median': round(median(vals), 4),
        'loss_n': sum(x <= 0 for x in vals),
        'micro_pct': round(sum(0 < x <= 0.55 for x in vals) / n * 100, 2),
        'min_year_n': min(yc.values()) if yc else 0,
        'year_counts': yc,
        'year_wr': yw,
        't1': 0,
    }


def classify(m: dict[str, Any]) -> str:
    if m['n'] >= PROD['n'] and m['min_year_n'] >= PROD['min_year_n'] and m['wr'] >= PROD['wr'] and m['avg'] >= PROD['avg'] and m['micro_pct'] <= PROD['micro_pct'] and m['t1'] == 0:
        return 'PRODUCTION_USABLE'
    if m['n'] >= RESEARCH['n'] and m['min_year_n'] >= RESEARCH['min_year_n'] and m['wr'] >= RESEARCH['wr'] and m['avg'] >= RESEARCH['avg'] and m['t1'] == 0:
        return 'RESEARCH_USABLE'
    return 'UNUSABLE'


def simulate(row: dict[str, Any], bars: list[dict[str, Any]], r_mult: float, max_hold: int, sl_buf: float) -> dict[str, Any] | None:
    idx = int(row['_idx'])
    entry = fnum(row.get('entry_price'))
    zl = fnum(row.get('zone_low'))
    if entry <= 0 or zl <= 0:
        return None
    sl = zl * (1 - sl_buf / 100.0)
    risk = entry - sl
    if risk <= 0:
        return None
    tp = entry + risk * r_mult
    start, end = idx + 1, min(len(bars) - 1, idx + max_hold)
    if start > end:
        return None
    exit_idx, exit_price, reason = end, fnum(bars[end].get('c')), 'TIME'
    mfe = -1e9
    mae = 1e9
    for j in range(start, end + 1):
        b = bars[j]
        o, h, l = fnum(b.get('o')), fnum(b.get('h')), fnum(b.get('l'))
        mfe = max(mfe, (h - entry) / entry * 100)
        mae = min(mae, (l - entry) / entry * 100)
        if o <= sl:
            exit_idx, exit_price, reason = j, o, 'GAP_SL'; break
        if l <= sl:
            exit_idx, exit_price, reason = j, sl, 'SL'; break
        if h >= tp:
            exit_idx, exit_price, reason = j, tp, 'TP'; break
    return {**row, 'pnl_pct': round((exit_price - entry) / entry * 100, 6), 'exit_reason': reason, 'exit_date': date_key(bars[exit_idx]), 'hold_bars': exit_idx - idx, 'mfe_pct': round(mfe, 6), 'mae_pct': round(mae, 6), 'variant': f'R{r_mult}_H{max_hold}_SL{sl_buf}', 'r_mult': r_mult, 'max_hold': max_hold, 'sl_buffer_pct': sl_buf}


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text('', encoding='utf-8'); return
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader(); w.writerows(rows)


def main() -> None:
    raw = json.loads(IN.read_text(encoding='utf-8'))
    buys = [r for r in raw if r.get('v164_dry_action') == 'BUY' and bval(r.get('v164_rule_pass')) and str(r.get('entry_date'))[:4] >= '2023']
    cache: dict[str, list[dict[str, Any]]] = {}
    prepared: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    invalid = Counter()
    for r in buys:
        sym = str(r.get('symbol'))
        bars = cache.setdefault(sym, load_bars(sym))
        idx = locate(bars, str(r.get('entry_date'))) if bars else -1
        if idx < 0:
            invalid['missing_kline_or_date'] += 1; continue
        r['_idx'] = idx
        prepared.append((r, bars))

    variants = [(r, h, s) for r in [0.5, 0.75, 1.0, 1.25, 1.5, 2.0] for h in [5, 10, 20, 30, 60] for s in [0.0, 0.5, 1.0]]
    all_results: list[dict[str, Any]] = []
    best_slice_rows: list[dict[str, Any]] = []
    best_slice_key: dict[str, Any] = {}

    numeric_gates: list[tuple[str, Callable[[dict[str, Any]], bool]]] = [
        ('ALL', lambda r: True),
        ('CHASE_LE_2', lambda r: fnum(r.get('entry_chase_above_zone_pct')) <= 2.0),
        ('CHASE_LE_3', lambda r: fnum(r.get('entry_chase_above_zone_pct')) <= 3.0),
        ('BODY_LE_65', lambda r: fnum(r.get('v132_reclaim_bull_body_pct')) <= 65.0),
        ('BODY_LE_75', lambda r: fnum(r.get('v132_reclaim_bull_body_pct')) <= 75.0),
        ('RECLAIM_ABOVE_GE_2', lambda r: fnum(r.get('v132_reclaim_close_above_zone_high_pct')) >= 2.0),
        ('RECLAIM_POS_GE_75', lambda r: fnum(r.get('v132_reclaim_close_pos_pct')) >= 75.0),
        ('RISK_LE_7', lambda r: fnum(r.get('risk_pct')) <= 7.0),
        ('RISK_3_TO_8', lambda r: 3.0 <= fnum(r.get('risk_pct')) <= 8.0),
    ]
    group_fields = [
        ('market_state',),
        ('poi_source',),
        ('v132_reclaim_class',),
        ('market_state', 'poi_source'),
        ('market_state', 'v132_reclaim_class'),
        ('poi_source', 'v132_reclaim_class'),
        ('market_state', 'poi_source', 'v132_reclaim_class'),
        ('market_state', 'combo_family', 'poi_source', 'v132_reclaim_class'),
    ]

    for r_mult, max_hold, sl_buf in variants:
        variant_rows: list[dict[str, Any]] = []
        for row, bars in prepared:
            sim = simulate(row, bars, r_mult, max_hold, sl_buf)
            if sim:
                variant_rows.append(sim)
        # total variant baseline
        m_total = metrics(variant_rows)
        all_results.append({'variant': f'R{r_mult}_H{max_hold}_SL{sl_buf}', 'slice': 'ALL', 'gate': 'ALL', **m_total, 'classification': classify(m_total)})
        for fields in group_fields:
            groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
            for row in variant_rows:
                groups[tuple(str(row.get(f, '')) for f in fields)].append(row)
            for val, grp in groups.items():
                if len(grp) < 80:
                    continue
                for gate_name, pred in numeric_gates:
                    g = [x for x in grp if pred(x)]
                    if len(g) < 80:
                        continue
                    m = metrics(g)
                    cls = classify(m)
                    rec = {'variant': f'R{r_mult}_H{max_hold}_SL{sl_buf}', 'slice': '+'.join(fields), 'bucket': '|'.join(val), 'gate': gate_name, **m, 'classification': cls}
                    all_results.append(rec)
                    if cls == 'PRODUCTION_USABLE' and (not best_slice_rows or (m['avg'], m['wr'], m['n']) > (best_slice_key.get('avg', -999), best_slice_key.get('wr', 0), best_slice_key.get('n', 0))):
                        best_slice_rows = g
                        best_slice_key = rec

    all_results.sort(key=lambda x: (x['classification'] != 'PRODUCTION_USABLE', x['classification'] != 'RESEARCH_USABLE', -x['avg'], -x['wr'], -x['n']))
    prod_slices = [r for r in all_results if r['classification'] == 'PRODUCTION_USABLE']
    research_slices = [r for r in all_results if r['classification'] == 'RESEARCH_USABLE']
    write_csv(OUT / 'v166_slice_variant_metrics.csv', all_results)
    write_csv(OUT / 'v166_production_slices.csv', prod_slices)
    write_csv(OUT / 'v166_research_slices.csv', research_slices[:500])
    write_csv(OUT / 'v166_best_production_slice_rows.csv', best_slice_rows)

    decision = 'V166_FOUND_PRODUCTION_USABLE_SCANNER_SLICE__NEXT_FULL_DRYRUN_GATE' if prod_slices else ('V166_ONLY_RESEARCH_USABLE__REBUILD_UPSTREAM_SIGNAL_LAYER' if research_slices else 'V166_NO_USABLE_SLICE__ABANDON_V164_DIRECTION')
    summary = {
        'decision': decision,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'engine': ENGINE,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'acceptance': {'production': PROD, 'research': RESEARCH, 'window': 'entry_year>=2023'},
        'source': {'buy_rows_2023_plus': len(buys), 'prepared': len(prepared), 'invalid': dict(invalid)},
        'production_slices_count': len(prod_slices),
        'research_slices_count': len(research_slices),
        'best_production_slice': prod_slices[0] if prod_slices else None,
        'top_research_slices': research_slices[:20],
        'next_required': 'If production slice exists: build V167 exact scanner dry-run from the slice rule, verify no outcome leak/current watchlist isolation, then only consider promotion. If not: stop V164 route and rebuild upstream signal generator.',
        'artifacts': {
            'all_metrics': str(OUT / 'v166_slice_variant_metrics.csv'),
            'production_slices': str(OUT / 'v166_production_slices.csv'),
            'research_slices': str(OUT / 'v166_research_slices.csv'),
            'best_rows': str(OUT / 'v166_best_production_slice_rows.csv'),
        },
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    (OUT / 'report.md').write_text('# V166 V164 slice variant search\n\n```json\n' + json.dumps(summary, ensure_ascii=False, indent=2, default=str) + '\n```\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
