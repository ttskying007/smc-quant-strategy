#!/usr/bin/env python3
"""V165: outcome + next-direction audit for V164 scanner-contract BUY rows.

Read-only research. No production/frontend/watchlist writes.

Purpose:
- V164 proved scan-time field integrity, but did not prove economic usability.
- Simulate real T+1 outcomes from cached K-lines for every V164 BUY row.
- Define explicit usable/unusable gates and identify the next research direction.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path('/root/.hermes')
IN = ROOT / 'smc_audit' / 'v164_corrected_scanner_dry_run_20260622' / 'v164_dryrun_rows.json'
OUT = ROOT / 'smc_audit' / 'v165_v164_outcome_and_direction_audit_20260623'
OUT.mkdir(parents=True, exist_ok=True)

ENGINE = 'V165_V164_OUTCOME_AND_DIRECTION_AUDIT'

# Fixed acceptance definition requested by the user: stop endless iteration with a hard boundary.
ACCEPTANCE = {
    'production_usable': {
        'n_min': 200,
        'min_year_n_min': 35,
        'wr_min_pct': 82.0,
        'avg_pnl_min_pct': 3.0,
        't1_violations': 0,
        'synthetic_be_rows': 0,
        'micro_profit_pct_max': 1.0,
        'scanner_contract_pass': True,
    },
    'research_usable': {
        'n_min': 80,
        'min_year_n_min': 15,
        'wr_min_pct': 72.0,
        'avg_pnl_min_pct': 1.5,
        't1_violations': 0,
    },
    'unusable': 'Any slice below research_usable, any outcome leak, or any T+1 violation.',
}


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        if isinstance(v, float) and math.isnan(v):
            return default
        if isinstance(v, str) and not v.strip():
            return default
        return float(v)
    except Exception:
        return default


def bval(v: Any) -> bool:
    return str(v).strip().lower() in {'true', '1', 'yes'}


def sym_to_kline_path(symbol: str) -> Path:
    code, exch = symbol.split('.')
    return ROOT / 'kline_cache' / f'{code}_{exch}_daily_750.json'


def load_bars(symbol: str) -> list[dict[str, Any]]:
    p = sym_to_kline_path(symbol)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def date_key(bar: dict[str, Any]) -> str:
    return str(bar.get('t') or bar.get('date') or '').replace('-', '')[:8]


def locate_entry(bars: list[dict[str, Any]], entry_date: str) -> int:
    ed = str(entry_date).replace('-', '')[:8]
    for i, b in enumerate(bars):
        if date_key(b) == ed:
            return i
    return -1


def simulate(row: dict[str, Any], bars: list[dict[str, Any]], *, r_mult: float, max_hold: int, sl_buffer_pct: float) -> dict[str, Any]:
    idx = locate_entry(bars, str(row.get('entry_date')))
    if idx < 0 or idx >= len(bars):
        return {'valid': False, 'reason': 'ENTRY_DATE_NOT_IN_KLINE'}
    entry = fnum(row.get('entry_price'))
    zone_low = fnum(row.get('zone_low'))
    zone_high = fnum(row.get('zone_high'))
    if entry <= 0 or zone_low <= 0 or zone_high <= 0:
        return {'valid': False, 'reason': 'BAD_PRICE'}
    sl = zone_low * (1.0 - sl_buffer_pct / 100.0)
    risk = entry - sl
    if risk <= 0:
        return {'valid': False, 'reason': 'NON_POSITIVE_RISK'}
    tp = entry + risk * r_mult

    # A-share T+1 hard gate: earliest exit is next trading bar.
    start = idx + 1
    end = min(len(bars) - 1, idx + max_hold)
    if start > end:
        return {'valid': False, 'reason': 'NO_FUTURE_BARS'}

    mfe = -10**9
    mae = 10**9
    exit_idx = end
    exit_price = fnum(bars[end].get('c'))
    exit_reason = 'TIME_EXIT'
    for j in range(start, end + 1):
        b = bars[j]
        o, h, l, c = fnum(b.get('o')), fnum(b.get('h')), fnum(b.get('l')), fnum(b.get('c'))
        mfe = max(mfe, (h - entry) / entry * 100.0)
        mae = min(mae, (l - entry) / entry * 100.0)
        # Conservative same-bar ordering: if both touch, assume SL first.
        if o <= sl:
            exit_idx, exit_price, exit_reason = j, o, 'GAP_SL'
            break
        if l <= sl:
            exit_idx, exit_price, exit_reason = j, sl, 'SL'
            break
        if h >= tp:
            exit_idx, exit_price, exit_reason = j, tp, 'TP'
            break
    pnl = (exit_price - entry) / entry * 100.0
    return {
        'valid': True,
        'entry_idx_found': idx,
        'exit_idx': exit_idx,
        'exit_date': date_key(bars[exit_idx]),
        'exit_price': round(exit_price, 6),
        'exit_reason': exit_reason,
        'pnl_pct': round(pnl, 6),
        'mfe_pct': round(mfe if mfe > -10**8 else 0.0, 6),
        'mae_pct': round(mae if mae < 10**8 else 0.0, 6),
        'sl': round(sl, 6),
        'tp': round(tp, 6),
        'risk_pct': round(risk / entry * 100.0, 6),
        'hold_bars': int(exit_idx - idx),
        't1_violation': bool(exit_idx == idx),
    }


def metrics(rows: list[dict[str, Any]], pnl_key: str = 'pnl_pct') -> dict[str, Any]:
    vals = [fnum(r.get(pnl_key)) for r in rows if r.get('valid', True)]
    n = len(vals)
    if n == 0:
        return {'n': 0, 'wr': 0.0, 'avg': 0.0, 'median': 0.0, 'sum': 0.0, 'loss_n': 0, 'micro_pct': 0.0, 'min_year_n': 0, 'year_counts': {}, 'year_wr': {}, 't1': 0}
    year_map: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        if not r.get('valid', True):
            continue
        y = str(r.get('entry_date', ''))[:4]
        year_map[y].append(fnum(r.get(pnl_key)))
    year_counts = {y: len(v) for y, v in sorted(year_map.items())}
    year_wr = {y: round(sum(1 for x in v if x > 0) / len(v) * 100.0, 2) for y, v in sorted(year_map.items()) if v}
    micro = sum(1 for x in vals if 0 < x <= 0.55)
    return {
        'n': n,
        'wr': round(sum(1 for x in vals if x > 0) / n * 100.0, 2),
        'avg': round(sum(vals) / n, 4),
        'median': round(median(vals), 4),
        'sum': round(sum(vals), 4),
        'loss_n': sum(1 for x in vals if x <= 0),
        'micro_pct': round(micro / n * 100.0, 2),
        'min_year_n': min(year_counts.values()) if year_counts else 0,
        'year_counts': year_counts,
        'year_wr': year_wr,
        't1': sum(1 for r in rows if r.get('t1_violation')),
    }


def classify(m: dict[str, Any]) -> str:
    p = ACCEPTANCE['production_usable']
    if (m['n'] >= p['n_min'] and m['min_year_n'] >= p['min_year_n_min'] and m['wr'] >= p['wr_min_pct']
            and m['avg'] >= p['avg_pnl_min_pct'] and m['t1'] == 0 and m['micro_pct'] <= p['micro_profit_pct_max']):
        return 'PRODUCTION_USABLE'
    r = ACCEPTANCE['research_usable']
    if (m['n'] >= r['n_min'] and m['min_year_n'] >= r['min_year_n_min'] and m['wr'] >= r['wr_min_pct']
            and m['avg'] >= r['avg_pnl_min_pct'] and m['t1'] == 0):
        return 'RESEARCH_USABLE'
    return 'UNUSABLE'


def group_table(rows: list[dict[str, Any]], keys: list[str], *, min_n: int = 30) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key in keys:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            groups[str(r.get(key, ''))].append(r)
        for val, g in groups.items():
            if len(g) < min_n:
                continue
            m = metrics(g)
            out.append({'bucket_key': key, 'bucket': val, **m, 'classification': classify(m)})
    out.sort(key=lambda x: (x['classification'] != 'PRODUCTION_USABLE', x['classification'] != 'RESEARCH_USABLE', -x['n'], -x['wr'], -x['avg']))
    return out


def combo_table(rows: list[dict[str, Any]], combos: list[tuple[str, ...]], *, min_n: int = 50) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for combo in combos:
        groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            groups[tuple(str(r.get(k, '')) for k in combo)].append(r)
        for val, g in groups.items():
            if len(g) < min_n:
                continue
            m = metrics(g)
            out.append({'bucket_key': '+'.join(combo), 'bucket': '|'.join(val), **m, 'classification': classify(m)})
    out.sort(key=lambda x: (x['classification'] != 'PRODUCTION_USABLE', x['classification'] != 'RESEARCH_USABLE', -x['wr'], -x['avg'], -x['n']))
    return out


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    all_rows = json.loads(IN.read_text(encoding='utf-8'))
    buys = [r for r in all_rows if r.get('v164_dry_action') == 'BUY' and bval(r.get('v164_rule_pass'))]
    bars_cache: dict[str, list[dict[str, Any]]] = {}
    # Pre-resolve K-line bars and entry index once. The first implementation did
    # this inside every matrix variant and timed out; this keeps V165 read-only but
    # makes the audit executable over all 11k V164 BUY rows.
    prepared: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    invalid_counts: Counter[str] = Counter()
    for row in buys:
        sym = str(row.get('symbol'))
        bars = bars_cache.setdefault(sym, load_bars(sym))
        idx = locate_entry(bars, str(row.get('entry_date'))) if bars else -1
        if idx < 0:
            invalid_counts['ENTRY_DATE_NOT_IN_KLINE'] += 1
            continue
        row['_v165_entry_idx_found'] = idx
        prepared.append((row, bars))

    matrix_rows: list[dict[str, Any]] = []
    best_rows_by_variant: dict[str, list[dict[str, Any]]] = {}

    variants = []
    for r_mult in [0.5, 0.75, 1.0, 1.5, 2.0]:
        for max_hold in [5, 10, 20, 30, 60]:
            for sl_buf in [0.0, 0.5, 1.0]:
                variants.append((r_mult, max_hold, sl_buf))

    def simulate_prepared(row: dict[str, Any], bars: list[dict[str, Any]], *, r_mult: float, max_hold: int, sl_buffer_pct: float) -> dict[str, Any]:
        idx = int(row['_v165_entry_idx_found'])
        entry = fnum(row.get('entry_price'))
        zone_low = fnum(row.get('zone_low'))
        zone_high = fnum(row.get('zone_high'))
        if entry <= 0 or zone_low <= 0 or zone_high <= 0:
            return {'valid': False, 'reason': 'BAD_PRICE'}
        sl = zone_low * (1.0 - sl_buffer_pct / 100.0)
        risk = entry - sl
        if risk <= 0:
            return {'valid': False, 'reason': 'NON_POSITIVE_RISK'}
        tp = entry + risk * r_mult
        start = idx + 1
        end = min(len(bars) - 1, idx + max_hold)
        if start > end:
            return {'valid': False, 'reason': 'NO_FUTURE_BARS'}
        mfe = -10**9
        mae = 10**9
        exit_idx = end
        exit_price = fnum(bars[end].get('c'))
        exit_reason = 'TIME_EXIT'
        for j in range(start, end + 1):
            b = bars[j]
            o, h, l = fnum(b.get('o')), fnum(b.get('h')), fnum(b.get('l'))
            mfe = max(mfe, (h - entry) / entry * 100.0)
            mae = min(mae, (l - entry) / entry * 100.0)
            if o <= sl:
                exit_idx, exit_price, exit_reason = j, o, 'GAP_SL'
                break
            if l <= sl:
                exit_idx, exit_price, exit_reason = j, sl, 'SL'
                break
            if h >= tp:
                exit_idx, exit_price, exit_reason = j, tp, 'TP'
                break
        pnl = (exit_price - entry) / entry * 100.0
        return {
            'valid': True,
            'entry_idx_found': idx,
            'exit_idx': exit_idx,
            'exit_date': date_key(bars[exit_idx]),
            'exit_price': round(exit_price, 6),
            'exit_reason': exit_reason,
            'pnl_pct': round(pnl, 6),
            'mfe_pct': round(mfe if mfe > -10**8 else 0.0, 6),
            'mae_pct': round(mae if mae < 10**8 else 0.0, 6),
            'sl': round(sl, 6),
            'tp': round(tp, 6),
            'risk_pct': round(risk / entry * 100.0, 6),
            'hold_bars': int(exit_idx - idx),
            't1_violation': False,
        }

    for r_mult, max_hold, sl_buf in variants:
        sim_rows: list[dict[str, Any]] = []
        invalid = Counter()
        variant_name = f'R{r_mult}_H{max_hold}_SLBUF{sl_buf}'
        for row, bars in prepared:
            res = simulate_prepared(row, bars, r_mult=r_mult, max_hold=max_hold, sl_buffer_pct=sl_buf)
            if not res.get('valid'):
                invalid[str(res.get('reason'))] += 1
                continue
            merged = {**row, **res, 'r_mult': r_mult, 'max_hold': max_hold, 'sl_buffer_pct': sl_buf, 'variant': variant_name}
            sim_rows.append(merged)
        m = metrics(sim_rows)
        matrix_rows.append({'variant': variant_name, 'r_mult': r_mult, 'max_hold': max_hold, 'sl_buffer_pct': sl_buf, **m, 'classification': classify(m), 'invalid': dict(invalid)})
        best_rows_by_variant[variant_name] = sim_rows
        invalid_counts.update(invalid)

    matrix_rows.sort(key=lambda x: (x['classification'] != 'PRODUCTION_USABLE', x['classification'] != 'RESEARCH_USABLE', -x['wr'], -x['avg'], -x['n']))
    best_variant = matrix_rows[0]['variant'] if matrix_rows else ''
    best_rows = best_rows_by_variant.get(best_variant, [])
    bucket_rows = group_table(best_rows, ['entry_date', 'poi_source', 'market_state', 'combo_family', 'event_type', 'v132_reclaim_class'], min_n=40)
    combo_rows = combo_table(best_rows, [
        ('market_state', 'poi_source'),
        ('market_state', 'combo_family'),
        ('poi_source', 'combo_family'),
        ('market_state', 'poi_source', 'v132_reclaim_class'),
    ], min_n=60)

    losses = sorted([r for r in best_rows if fnum(r.get('pnl_pct')) <= 0], key=lambda r: (str(r.get('entry_date')), fnum(r.get('pnl_pct'))))[:300]
    write_csv(OUT / 'v165_matrix_metrics.csv', matrix_rows)
    write_csv(OUT / 'v165_best_variant_rows.csv', best_rows)
    write_csv(OUT / 'v165_best_variant_losses_top300.csv', losses)
    write_csv(OUT / 'v165_bucket_metrics.csv', bucket_rows)
    write_csv(OUT / 'v165_combo_metrics.csv', combo_rows)

    best_m = {k: v for k, v in matrix_rows[0].items() if k not in {'invalid'}} if matrix_rows else {}
    production_slices = [r for r in combo_rows + bucket_rows if r.get('classification') == 'PRODUCTION_USABLE']
    research_slices = [r for r in combo_rows + bucket_rows if r.get('classification') == 'RESEARCH_USABLE']
    exit_counter = Counter(str(r.get('exit_reason')) for r in best_rows)
    buy_years = Counter(str(r.get('entry_date'))[:4] for r in buys)

    if best_m.get('classification') == 'PRODUCTION_USABLE':
        decision = 'V164_OUTCOME_PRODUCTION_USABLE__NEXT_PROMOTION_GATE'
        next_direction = 'Run endpoint/frontend dry-run mapping and current watchlist isolation before production write.'
    elif production_slices:
        decision = 'V164_HAS_PRODUCTION_USABLE_SUBSLICE__BUILD_V166_SCANNER_RULE'
        next_direction = 'Build V166 as explicit scanner-time rule from the best production-usable slice; rerun full scanner dry-run and production gates.'
    elif research_slices:
        decision = 'V164_ONLY_RESEARCH_USABLE_SUBSLICE__CONTINUE_RULE_REBUILD'
        next_direction = 'Use research-usable slice as seed, but do not promote; search non-outcome gates around market_state/POI/reclaim strength and reject weak years.'
    else:
        decision = 'V164_ECONOMICALLY_UNUSABLE__CHANGE_RESEARCH_DIRECTION'
        next_direction = 'Stop expanding TRUE_TAKEOVER reclaim gates. Rebuild signal layer upstream: market-state first, POI quality before touch/reclaim, and separate continuation vs reversal generators.'

    summary = {
        'decision': decision,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'engine': ENGINE,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'input': str(IN),
        'acceptance_definition': ACCEPTANCE,
        'source': {
            'v164_buy_rows': len(buys),
            'buy_year_counts': dict(sorted(buy_years.items())),
            'missing_or_invalid': dict(invalid_counts),
        },
        'best_variant_metrics': best_m,
        'best_variant_exit_reason_counts': dict(exit_counter),
        'production_usable_slices_count': len(production_slices),
        'research_usable_slices_count': len(research_slices),
        'top_production_slices': production_slices[:20],
        'top_research_slices': research_slices[:20],
        'top_matrix': matrix_rows[:20],
        'next_direction': next_direction,
        'artifacts': {
            'matrix': str(OUT / 'v165_matrix_metrics.csv'),
            'best_rows': str(OUT / 'v165_best_variant_rows.csv'),
            'losses': str(OUT / 'v165_best_variant_losses_top300.csv'),
            'buckets': str(OUT / 'v165_bucket_metrics.csv'),
            'combos': str(OUT / 'v165_combo_metrics.csv'),
        },
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

    report = [
        '# V165 V164 outcome + direction audit', '',
        f"Decision: `{decision}`", '',
        '## Acceptance boundary', '```json', json.dumps(ACCEPTANCE, ensure_ascii=False, indent=2), '```', '',
        '## Best variant', '```json', json.dumps(best_m, ensure_ascii=False, indent=2), '```', '',
        f"Exit reasons: `{dict(exit_counter)}`", '',
        '## Next direction', next_direction, '',
        '## Artifacts', json.dumps(summary['artifacts'], ensure_ascii=False, indent=2),
    ]
    (OUT / 'report.md').write_text('\n'.join(report), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
