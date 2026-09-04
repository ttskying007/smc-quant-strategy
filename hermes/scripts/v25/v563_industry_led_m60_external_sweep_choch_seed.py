#!/usr/bin/env python3
"""V563 outcome-blind generator: industry-led M60 external SSL sweep -> CHOCH.

Reads only OHLCV/industry mapping and writes no outcome fields.  The separate
oracle/replay stages are intentionally not in this program.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

BASE = Path('/root/.hermes')
AUDIT = BASE / 'smc_audit'
K60 = BASE / 'kline_cache_60min'
KDAY = BASE / 'kline_cache'
INDMAP = AUDIT / 'v225_baostock_industry_participation_probe_20260627_031854/baostock_stock_industry.json'
PREREG = AUDIT / 'v563_industry_led_m60_external_sweep_choch_preregistration.json'
LATEST = AUDIT / 'v563_industry_led_m60_external_sweep_choch_seed_latest.json'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v563_industry_led_m60_external_sweep_choch_seed_no_outcome_{TS}'


def sf(x: Any, default: float = math.nan) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def day(x: Any) -> str:
    s = ''.join(c for c in str(x or '') if c.isdigit())
    return s[:8] if len(s) >= 8 else ''


def load(p: Path) -> list[dict[str, Any]]:
    try:
        x = json.loads(p.read_text())
        return x if isinstance(x, list) else []
    except Exception:
        return []


def sym_from_path(p: Path) -> str:
    a = p.name.split('_')
    return f'{a[0]}.{a[1]}' if len(a) >= 4 and len(a[0]) == 6 else ''


def daily_path(sym: str) -> Path:
    c, ex = sym.split('.')
    return KDAY / f'{c}_{ex}_daily_750.json'


def build_industry_context(industry: dict[str, str]) -> tuple[dict[tuple[str, str], bool], dict[str, str], int]:
    """Return (previous_day, industry)->activation from strictly completed daily bars."""
    by_day: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    calendar: set[str] = set()
    files = 0
    for p in KDAY.glob('*_daily_750.json'):
        sym = sym_from_path(p)
        ind = industry.get(sym, '')
        if not ind:
            continue
        bars = sorted(load(p), key=lambda b: day(b.get('t') or b.get('date')))
        prev_close = math.nan
        files += 1
        for b in bars:
            d = day(b.get('t') or b.get('date'))
            close, high = sf(b.get('c')), sf(b.get('h'))
            if not d or close <= 0:
                continue
            calendar.add(d)
            if prev_close > 0:
                ret = (close / prev_close - 1) * 100
                hi_ret = (high / prev_close - 1) * 100 if high > 0 else ret
                by_day[(d, ind)].append((ret, hi_ret))
            prev_close = close
    dates = sorted(calendar)
    prev = {dates[i]: dates[i - 1] for i in range(1, len(dates))}
    active: dict[tuple[str, str], bool] = {}
    for key, rows in by_day.items():
        # At least five mapped names prevents tiny industry artifacts.
        if len(rows) < 5:
            continue
        strong5 = sum(ret >= 5 for ret, _ in rows) / len(rows) * 100
        limit_touch = sum(hi >= 9.5 for _, hi in rows)
        active[key] = limit_touch >= 3 or strong5 >= 20
    return active, prev, files


def confirmed_swing_high(bars: list[dict[str, Any]], before: int) -> int | None:
    """Latest 2L/2R high whose right confirmation finishes before `before`."""
    for k in range(before - 3, 1, -1):
        h = sf(bars[k].get('h'))
        if h <= 0:
            continue
        window = [sf(bars[j].get('h')) for j in range(k - 2, k + 3)]
        if all(v > 0 for v in window) and h == max(window) and window.count(h) == 1:
            return k
    return None


def seeds_for_symbol(sym: str, ind: str, active: dict[tuple[str, str], bool], prev_day: dict[str, str]) -> list[dict[str, Any]]:
    p = K60 / f"{sym.split('.')[0]}_{sym.split('.')[1]}_60min_500.json"
    bars = sorted(load(p), key=lambda b: str(b.get('t') or ''))
    by_day: dict[str, list[int]] = defaultdict(list)
    for i, b in enumerate(bars):
        d = day(b.get('t'))
        if d:
            by_day[d].append(i)
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for d, idxs in sorted(by_day.items()):
        prior = prev_day.get(d, '')
        if not prior or not active.get((prior, ind), False):
            continue
        # A-shares normally have four 60m bars; only early-session first three
        # are permitted, so the structural confirmation is observable before close.
        idxs = sorted(idxs)[:3]
        for i in idxs:
            if i < 10:
                continue
            b = bars[i]
            lo, close = sf(b.get('l')), sf(b.get('c'))
            ref_low = min(sf(bars[j].get('l')) for j in range(i - 8, i))
            if lo <= 0 or ref_low <= 0 or not (lo < ref_low and close > ref_low):
                continue
            sh = confirmed_swing_high(bars, i)
            if sh is None:
                continue
            sh_high = sf(bars[sh].get('h'))
            if sh_high <= 0:
                continue
            shift = None
            for j in idxs:
                if j <= i:
                    continue
                if sf(bars[j].get('c')) > sh_high:
                    shift = j
                    break
            if shift is None:
                continue
            key = (sym, d)
            if key in seen:
                break
            # Entry date is determined from the canonical daily calendar, but no
            # entry OHLC/outcome is read in this outcome-blind generator.
            daily = sorted(load(daily_path(sym)), key=lambda x: day(x.get('t') or x.get('date')))
            ds = [day(x.get('t') or x.get('date')) for x in daily]
            try:
                pos = ds.index(d)
            except ValueError:
                break
            if pos + 1 >= len(ds) or not ds[pos + 1]:
                break
            out.append({
                'symbol': sym, 'industry': ind,
                'prior_industry_date': prior, 'event_date': d, 'entry_date': ds[pos + 1],
                'sweep_time': str(b.get('t')), 'sweep_idx': i,
                'sweep_low': round(lo, 6), 'external_ref_low': round(ref_low, 6),
                'reclaim_close': round(close, 6),
                'swing_high_time': str(bars[sh].get('t')), 'swing_high_idx': sh,
                'swing_high': round(sh_high, 6),
                'choch_time': str(bars[shift].get('t')), 'choch_idx': shift,
                'choch_close': round(sf(bars[shift].get('c')), 6),
                'stop_pre_entry': round(lo * 0.99, 6),
                'semantic_path': 'PRIOR_INDUSTRY_ACTIVATION->M60_EXTERNAL_SSL_SWEEP_RECLAIM->CONFIRMED_M60_CHOCH->NEXT_DAILY_OPEN',
            })
            seen.add(key)
            break
    return out


def main() -> None:
    prereg = json.loads(PREREG.read_text())
    industry = {str(r.get('symbol')): str(r.get('industry')) for r in json.loads(INDMAP.read_text()) if r.get('symbol') and r.get('industry')}
    active, prev_day, daily_files = build_industry_context(industry)
    rows: list[dict[str, Any]] = []
    for p in sorted(K60.glob('*_60min_500.json')):
        sym = sym_from_path(p)
        ind = industry.get(sym, '')
        if sym and ind:
            rows.extend(seeds_for_symbol(sym, ind, active, prev_day))
    rows.sort(key=lambda r: (r['event_date'], r['symbol']))
    identities = [(r['symbol'], r['event_date']) for r in rows]
    assert len(identities) == len(set(identities)), 'duplicate event identities'
    forbidden = {'pnl', 'exit', 'reason', 'hold', 'mfe', 'mae', 'won'}
    assert not (set().union(*(set(r) for r in rows)) & forbidden), 'outcome field leaked'
    years = defaultdict(int)
    for r in rows:
        years[r['event_date'][:4]] += 1
    OUT.mkdir(parents=True, exist_ok=True)
    rows_path = OUT / 'v563_seed_rows.csv'
    fields = sorted(set().union(*(r.keys() for r in rows))) if rows else []
    with rows_path.open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows(rows)
    report = {
        'version': 'V563_INDUSTRY_LED_M60_EXTERNAL_SWEEP_CHOCH_SEED_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'preregistration': str(PREREG),
        'input_contract': 'local same-source 60m_500 OHLCV + daily OHLCV + static industry map; generator reads no outcome fields',
        'inputs': {'m60_files': len(list(K60.glob('*_60min_500.json'))), 'daily_files': daily_files, 'mapped_symbols': len(industry), 'industry_active_dates': sum(active.values())},
        'support': {'seeds': len(rows), 'year_counts': dict(sorted(years.items())), 'unique_symbol_event_identities': len(set(identities))},
        'invariants': {'no_outcome_fields_read': True, 'duplicate_identity_count': len(identities)-len(set(identities)), 'production_write': False, 'frontend_write': False, 'watchlist_write': False},
        'artifacts': {'dir': str(OUT), 'rows': str(rows_path), 'summary': str(OUT / 'v563_report.json')},
    }
    (OUT / 'v563_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({'status': 'PASS', 'latest': str(LATEST), 'support': report['support'], 'invariants': report['invariants']}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
