#!/usr/bin/env python3
"""V301 no-write: previous-day limit-up/strong-board leadership overlay on V300 rows.

V300 proved entry-session 60m price+volume diffusion is informative but still
fails weak months.  This script tests a different parent-state source available
before entry: previous trading day's market/industry board leadership, proxied
from daily OHLCV limit-up and strong-up participation.

No production/frontend/watchlist writes.  Outputs audit artifacts only.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

BASE = Path('/root/.hermes')
AUDIT = BASE / 'smc_audit'
V294_SCRIPT = BASE / 'scripts/v25/v294_entry60_persistence_audit.py'
V300_LATEST = AUDIT / 'v300_entry60_volume_diffusion_latest.json'
INDMAP = AUDIT / 'v225_baostock_industry_participation_probe_20260627_031854/baostock_stock_industry.json'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v301_prevday_board_leadership_no_write_{TS}'
LATEST = AUDIT / 'v301_prevday_board_leadership_latest.json'


def load_core():
    spec = importlib.util.spec_from_file_location('v294_core_for_v301', V294_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


core = load_core()


def sf(x: Any, d: float = math.nan) -> float:
    return core.sf(x, d)


def dn(x: Any) -> str:
    return core.dn(x)


def read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open() as fh:
        return list(csv.DictReader(fh))


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text('')
        return
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with path.open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader(); w.writerows(rows)


def metric(rows: list[dict[str, Any]], stock_count: int, source_n: int) -> dict[str, Any]:
    agg = core.blank()
    for r in rows:
        core.add(agg, r)
    return core.metrics(agg, stock_count, source_n)


def daily_symbol_from_path(p: Path) -> str:
    parts = p.name.split('_')
    if len(parts) >= 2 and parts[0].isdigit() and parts[1] in {'SH', 'SZ', 'BJ'}:
        return f'{parts[0]}.{parts[1]}'
    return ''


def build_board_context(sym_ind: dict[str, str]) -> tuple[dict[str, dict[str, float]], dict[tuple[str, str], dict[str, float]], dict[str, str], int]:
    """Return market and industry board context by trading date.

    Context is computed from daily bars.  It will later be shifted to the prior
    trading date before joining candidate rows, so it is entry-time safe.
    """
    seen: set[str] = set()
    daily_by_date: dict[str, list[dict[str, float]]] = defaultdict(list)
    ind_by_date: dict[tuple[str, str], list[dict[str, float]]] = defaultdict(list)
    files = 0
    for d in (core.KDAY,):
        for p in d.glob('*_daily_750.json'):
            sym = daily_symbol_from_path(p)
            if not sym or sym not in sym_ind or sym in seen:
                continue
            seen.add(sym); files += 1
            bars = core.load_json(p)
            prev_c = math.nan
            for b in bars:
                day = dn(b.get('t') or b.get('date'))
                c = sf(b.get('c'))
                h = sf(b.get('h'))
                if not day or c <= 0 or prev_c <= 0:
                    prev_c = c if c > 0 else prev_c
                    continue
                ret = (c / prev_c - 1) * 100
                high_ret = (h / prev_c - 1) * 100 if h > 0 else ret
                rec = {
                    'ret': ret,
                    'high_ret': high_ret,
                    'limit_close': float(ret >= 9.5),
                    'limit_touch': float(high_ret >= 9.5),
                    'strong5': float(ret >= 5.0),
                    'strong3': float(ret >= 3.0),
                    'down3': float(ret <= -3.0),
                }
                daily_by_date[day].append(rec)
                ind_by_date[(day, sym_ind[sym])].append(rec)
                prev_c = c
    mctx: dict[str, dict[str, float]] = {}
    for day, rs in daily_by_date.items():
        n = len(rs)
        if n == 0:
            continue
        mctx[day] = {
            'mkt_board_n': n,
            'mkt_limit_close_cnt': sum(r['limit_close'] for r in rs),
            'mkt_limit_touch_cnt': sum(r['limit_touch'] for r in rs),
            'mkt_limit_close_pct': sum(r['limit_close'] for r in rs) / n * 100,
            'mkt_limit_touch_pct': sum(r['limit_touch'] for r in rs) / n * 100,
            'mkt_strong5_pct': sum(r['strong5'] for r in rs) / n * 100,
            'mkt_strong3_pct': sum(r['strong3'] for r in rs) / n * 100,
            'mkt_down3_pct': sum(r['down3'] for r in rs) / n * 100,
            'mkt_med_ret': median([r['ret'] for r in rs]),
        }
    ictx: dict[tuple[str, str], dict[str, float]] = {}
    # Need daily ranks of industries by limit/strong participation.
    by_day_ind_metrics: dict[str, list[tuple[str, dict[str, float]]]] = defaultdict(list)
    for (day, ind), rs in ind_by_date.items():
        n = len(rs)
        if n < 5:
            continue
        rec = {
            'ind_board_n': n,
            'ind_limit_close_cnt': sum(r['limit_close'] for r in rs),
            'ind_limit_touch_cnt': sum(r['limit_touch'] for r in rs),
            'ind_limit_close_pct': sum(r['limit_close'] for r in rs) / n * 100,
            'ind_limit_touch_pct': sum(r['limit_touch'] for r in rs) / n * 100,
            'ind_strong5_pct': sum(r['strong5'] for r in rs) / n * 100,
            'ind_strong3_pct': sum(r['strong3'] for r in rs) / n * 100,
            'ind_down3_pct': sum(r['down3'] for r in rs) / n * 100,
            'ind_med_ret': median([r['ret'] for r in rs]),
        }
        by_day_ind_metrics[day].append((ind, rec))
    for day, vals in by_day_ind_metrics.items():
        ranked = sorted(vals, key=lambda x: (x[1]['ind_limit_touch_cnt'], x[1]['ind_strong5_pct'], x[1]['ind_med_ret']), reverse=True)
        for rank, (ind, rec) in enumerate(ranked, start=1):
            full = dict(rec)
            full['ind_board_rank'] = rank
            full['ind_board_rank_pct'] = rank / max(1, len(ranked)) * 100
            ictx[(day, ind)] = full
    dates = sorted(mctx)
    prev: dict[str, str] = {}
    for i, day in enumerate(dates):
        if i > 0:
            prev[day] = dates[i - 1]
    return mctx, ictx, prev, files


def enrich(rows: list[dict[str, Any]], sym_ind: dict[str, str], mctx, ictx, prev_map) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        day = dn(r.get('entry_date'))
        sym = r.get('symbol', '')
        ind = sym_ind.get(sym, '')
        prev_day = prev_map.get(day, '')
        if not prev_day:
            continue
        m = mctx.get(prev_day)
        ii = ictx.get((prev_day, ind))
        if not m or not ii:
            continue
        nr = dict(r)
        nr.update({k: round(v, 4) if isinstance(v, float) else v for k, v in m.items()})
        nr.update({k: round(v, 4) if isinstance(v, float) else v for k, v in ii.items()})
        nr['prev_trade_date'] = prev_day
        nr['board_industry'] = ind
        nr['board_lead_rel'] = round(sf(ii.get('ind_strong5_pct')) - sf(m.get('mkt_strong5_pct')), 4)
        nr['limit_lead_rel'] = round(sf(ii.get('ind_limit_touch_pct')) - sf(m.get('mkt_limit_touch_pct')), 4)
        out.append(nr)
    return out


def v300_base_two_year(r: dict[str, Any]) -> bool:
    return (
        int(sf(r.get('confirm_k'), 0)) == 2
        and sf(r.get('mkt_up')) >= 65
        and sf(r.get('ind_up')) >= 65
        and sf(r.get('mkt_up_vol')) >= 20
        and sf(r.get('ind_up_vol')) >= 20
        and sf(r.get('stock60_vol_ratio')) >= 1.0
        and sf(r.get('stock60_ret')) >= 0.0
    )


def evaluate(rows: list[dict[str, Any]], stock_count: int, source_n: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    variants: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    universes = [
        ('raw_enriched', rows),
        ('v300_two_year_base', [r for r in rows if v300_base_two_year(r)]),
    ]
    for uname, base in universes:
        for m_lim in (0, 20, 50):
            for m_strong in (0, 10, 20):
                for ind_lim in (0, 1, 3):
                    for ind_limpct in (0, 5, 10):
                        for ind_strong in (0, 20, 40):
                            for rank_pct in (100, 33):
                                for lead_rel in (-999, 0, 5):
                                    kept = []
                                    for r in base:
                                        if sf(r.get('mkt_limit_touch_cnt')) < m_lim:
                                            continue
                                        if sf(r.get('mkt_strong5_pct')) < m_strong:
                                            continue
                                        if sf(r.get('ind_limit_touch_cnt')) < ind_lim:
                                            continue
                                        if sf(r.get('ind_limit_touch_pct')) < ind_limpct:
                                            continue
                                        if sf(r.get('ind_strong5_pct')) < ind_strong:
                                            continue
                                        if sf(r.get('ind_board_rank_pct')) > rank_pct:
                                            continue
                                        if sf(r.get('board_lead_rel')) < lead_rel:
                                            continue
                                        kept.append(r)
                                    if len(kept) < 80:
                                        continue
                                    mm = metric(kept, stock_count, source_n)
                                    if mm.get('min_year_n', 0) < 30 or mm.get('min_month_n', 0) < 10:
                                        continue
                                    mm['variant'] = f'{uname}|mlim{m_lim}|mstr{m_strong}|ilim{ind_lim}|ilimp{ind_limpct}|istr{ind_strong}|rank{rank_pct}|lead{lead_rel}'
                                    mm['config'] = {'universe': uname, 'mkt_limit_touch_cnt': m_lim, 'mkt_strong5_pct': m_strong, 'ind_limit_touch_cnt': ind_lim, 'ind_limit_touch_pct': ind_limpct, 'ind_strong5_pct': ind_strong, 'ind_board_rank_pct_max': rank_pct, 'board_lead_rel_min': lead_rel}
                                    mm['t1_violations'] = sum(1 for x in kept if str(x.get('t1_violation')).lower() == 'true')
                                    variants.append((mm, kept))
    # Prefer month stability, then year stability, then quality. This deliberately penalizes one-month/one-year pockets.
    variants.sort(key=lambda x: (x[0].get('min_month_wr', 0), x[0].get('min_year_wr', 0), x[0].get('wr', 0), x[0].get('avg', 0), x[0].get('n', 0)), reverse=True)
    return [v[0] for v in variants[:80]], variants[0][1] if variants else []


def decompose(rows: list[dict[str, Any]], stock_count: int, source_n: int) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        dims = {
            'month': str(r.get('entry_date', ''))[:6],
            'reason': str(r.get('reason', '')),
            'confirm_k': str(r.get('confirm_k', '')),
            'mkt_limit_bucket': 'M_LIM80' if sf(r.get('mkt_limit_touch_cnt')) >= 80 else 'M_LIM40' if sf(r.get('mkt_limit_touch_cnt')) >= 40 else 'M_LIM20' if sf(r.get('mkt_limit_touch_cnt')) >= 20 else 'M_LIM<20',
            'ind_rank_bucket': 'TOP20' if sf(r.get('ind_board_rank_pct')) <= 20 else 'TOP33' if sf(r.get('ind_board_rank_pct')) <= 33 else 'TOP50' if sf(r.get('ind_board_rank_pct')) <= 50 else 'REST',
            'lead_bucket': 'LEAD10' if sf(r.get('board_lead_rel')) >= 10 else 'LEAD5' if sf(r.get('board_lead_rel')) >= 5 else 'LEAD0' if sf(r.get('board_lead_rel')) >= 0 else 'LAG',
        }
        for k, v in dims.items():
            groups[(k, v)].append(r)
    out = []
    for (dim, val), rs in groups.items():
        if len(rs) >= 50:
            out.append({'dimension': dim, 'value': val, **metric(rs, stock_count, source_n)})
    out.sort(key=lambda x: (x.get('min_month_wr', 0), x.get('min_year_wr', 0), x.get('wr', 0), x.get('avg', 0)), reverse=True)
    return out[:120]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    v300 = json.loads(V300_LATEST.read_text())
    source_path = Path(v300['artifacts']['enriched_rows'])
    rows = read_rows(source_path)
    source_n = int(v300.get('source_n') or len(rows))
    stock_count = len({r['symbol'] for r in rows})
    sym_ind = {r['symbol']: r.get('industry', '') for r in json.loads(INDMAP.read_text()) if r.get('symbol')}
    mctx, ictx, prev_map, daily_files = build_board_context(sym_ind)
    enriched = enrich(rows, sym_ind, mctx, ictx, prev_map)
    top, best_rows = evaluate(enriched, stock_count, source_n)

    enriched_path = OUT / 'v301_enriched_rows.csv'
    best_path = OUT / 'v301_best_rows.csv'
    write_rows(enriched_path, enriched)
    write_rows(best_path, best_rows)

    base_rows = [r for r in enriched if v300_base_two_year(r)]
    summary = {
        'version': 'V301_PREVDAY_BOARD_LEADERSHIP_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'hypothesis': 'Previous-day market/industry limit-up and strong-board leadership can identify real sector-led continuation missed by 60m volume thresholds.',
        'source': str(source_path),
        'source_n': source_n,
        'daily_files': daily_files,
        'raw_v300_enriched': metric(rows, stock_count, source_n),
        'board_enriched_rows': metric(enriched, stock_count, source_n),
        'v300_two_year_base_before_board': metric(base_rows, stock_count, source_n),
        'best_variant': top[0] if top else None,
        'top_variants': top[:30],
        'best_decomposition': decompose(best_rows, stock_count, source_n) if best_rows else [],
        't1_violations_enriched': sum(1 for r in enriched if str(r.get('t1_violation')).lower() == 'true'),
        't1_violations_best': sum(1 for r in best_rows if str(r.get('t1_violation')).lower() == 'true'),
        'artifacts': {'enriched_rows': str(enriched_path), 'best_rows': str(best_path), 'summary': str(OUT / 'v301_summary.json')},
    }
    (OUT / 'v301_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({'latest': str(LATEST), 'board_enriched': summary['board_enriched_rows'], 'base_before': summary['v300_two_year_base_before_board'], 'best': summary['best_variant'], 'top10': top[:10], 't1_best': summary['t1_violations_best']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
