#!/usr/bin/env python3
"""V275 no-write: temporal sequence signature audit for high-volume SMC opportunities.

Purpose:
- User concern: current production volume is too low; if primitive SMC indicators are OK,
  the remaining bottleneck is chronological combinations + parameters.
- V272/V274 tested a broad BOS->Demand->Retest surface and stock-DNA persistence.
- V275 decomposes the chronological ordering itself: prior SSL sweep timing, whether SSL
  occurs before/after the demand zone, demand-zone age, retest delay, risk/chase buckets,
  and their outcome/volume tradeoffs.

Inputs are read-only historical candidate rows from V262; no production/frontend/watchlist writes.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

BASE = Path('/root/.hermes')
KDIR = BASE / 'kline_cache'
SRC = BASE / 'smc_audit/v262_fresh_bos_retest_generator_no_write_20260702_100027/v262_all_fresh_candidates.csv'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = BASE / f'smc_audit/v275_temporal_sequence_signature_audit_no_write_{TS}'
LATEST = BASE / 'smc_audit/v275_temporal_sequence_signature_audit_latest.json'


def fnum(x: Any, d: float = math.nan) -> float:
    try:
        if x is None or x == '':
            return d
        v = float(x)
        return v if not math.isnan(v) else d
    except Exception:
        return d


def date_s(b: dict[str, Any]) -> str:
    return str(b.get('t', b.get('date', ''))).replace('.0', '')[:8]


def path_for_symbol(symbol: str) -> Path:
    code, exch = symbol.split('.')
    return KDIR / f'{code}_{exch}_daily_750.json'


def load_bars(symbol: str, cache: dict[str, list[dict[str, Any]] | None]) -> list[dict[str, Any]] | None:
    if symbol in cache:
        return cache[symbol]
    p = path_for_symbol(symbol)
    try:
        bars = json.loads(p.read_text())
    except Exception:
        bars = None
    cache[symbol] = bars
    return bars


def find_last_ssl(bars: list[dict[str, Any]], event_i: int, win: int = 40) -> int | None:
    """Last source-safe SSL sweep before event: low pierces prior20 low and close reclaims it."""
    start = max(20, event_i - win)
    out = None
    for i in range(start, event_i):
        prev = bars[i - 20:i]
        if not prev:
            continue
        pl = min(fnum(x.get('l')) for x in prev)
        lo = fnum(bars[i].get('l')); cl = fnum(bars[i].get('c'))
        if not math.isnan(pl) and lo < pl and cl > pl:
            out = i
    return out


def bkt_num(x: float, cuts: list[float], labels: list[str]) -> str:
    if math.isnan(x):
        return 'NA'
    for c, lab in zip(cuts, labels):
        if x <= c:
            return lab
    return labels[-1]


def metrics(df: pd.DataFrame) -> dict[str, Any]:
    if len(df) == 0:
        return {'n': 0}
    pnl = pd.to_numeric(df['pnl_pct'], errors='coerce')
    years = df['entry_date_s'].astype(str).str[:4]
    yc = years.value_counts().sort_index().to_dict()
    ywr = {str(y): round(float((pnl[years == y] > 0).mean() * 100), 2) for y in sorted(years.dropna().unique())}
    return {
        'n': int(len(df)),
        'wr': round(float((pnl > 0).mean() * 100), 4),
        'avg': round(float(pnl.mean()), 4),
        'median': round(float(pnl.median()), 4),
        'loss': int((pnl <= 0).sum()),
        'micro': round(float(((pnl > 0) & (pnl < 1)).mean() * 100), 4),
        'min_year_n': int(min(yc.values()) if yc else 0),
        'year_counts': {str(k): int(v) for k, v in yc.items()},
        'year_wr': ywr,
        'all_year_wr_min': round(float(min(ywr.values()) if ywr else 0), 2),
        'symbols': int(df['symbol'].nunique()),
        'per_stock_3y': round(float(len(df) / max(df['symbol'].nunique(), 1)), 4),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(SRC, low_memory=False)
    df = df[pd.to_numeric(df['pnl_pct'], errors='coerce').notna()].copy()
    df['entry_date_s'] = df['entry_date_s'].astype(str).str.replace('.0', '', regex=False).str[:8]
    # Keep the modern complete window used by current SMC audits.
    df = df[df['entry_date_s'].str[:4].isin(['2023', '2024', '2025', '2026'])].copy()

    cache: dict[str, list[dict[str, Any]] | None] = {}
    ssl_idx = []
    for r in df[['symbol', 'event_idx']].itertuples(index=False):
        bars = load_bars(str(r.symbol), cache)
        if bars is None:
            ssl_idx.append(None)
            continue
        idx = find_last_ssl(bars, int(r.event_idx), 40)
        ssl_idx.append(idx)
    df['v275_ssl_idx'] = ssl_idx
    df['v275_has_ssl40'] = df['v275_ssl_idx'].notna()
    df['v275_ssl_age'] = pd.to_numeric(df['event_idx'], errors='coerce') - pd.to_numeric(df['v275_ssl_idx'], errors='coerce')
    df['v275_zone_age'] = pd.to_numeric(df['event_idx'], errors='coerce') - pd.to_numeric(df['zone_idx'], errors='coerce')
    df['v275_ssl_vs_zone'] = 'NO_SSL'
    df.loc[df['v275_has_ssl40'] & (pd.to_numeric(df['v275_ssl_idx']) < pd.to_numeric(df['zone_idx'])), 'v275_ssl_vs_zone'] = 'SSL_BEFORE_ZONE'
    df.loc[df['v275_has_ssl40'] & (pd.to_numeric(df['v275_ssl_idx']) == pd.to_numeric(df['zone_idx'])), 'v275_ssl_vs_zone'] = 'SSL_ON_ZONE'
    df.loc[df['v275_has_ssl40'] & (pd.to_numeric(df['v275_ssl_idx']) > pd.to_numeric(df['zone_idx'])), 'v275_ssl_vs_zone'] = 'SSL_AFTER_ZONE_BEFORE_BOS'
    df['v275_ssl_age_bucket'] = [bkt_num(fnum(x), [3, 8, 20, 40], ['0_3', '4_8', '9_20', '21_40', 'GT40_NO']) for x in df['v275_ssl_age']]
    df.loc[~df['v275_has_ssl40'], 'v275_ssl_age_bucket'] = 'NO_SSL'
    df['v275_zone_age_bucket'] = [bkt_num(fnum(x), [1, 2, 5, 8], ['1', '2', '3_5', '6_8', 'GT8']) for x in df['v275_zone_age']]
    df['v275_retest_delay_bucket'] = [bkt_num(fnum(x), [2, 5, 8], ['1_2', '3_5', '6_8', 'GT8']) for x in df['event_to_reclaim_bars']]
    df['v275_risk_bucket'] = [bkt_num(fnum(x), [2.5, 4, 6, 8, 12], ['0_2_5', '2_5_4', '4_6', '6_8', '8_12', 'GT12']) for x in df['risk_pct']]
    df['v275_chase_bucket'] = [bkt_num(fnum(x), [0.5, 1.5, 2.5, 4], ['0_0_5', '0_5_1_5', '1_5_2_5', '2_5_4', 'GT4']) for x in df['entry_chase_above_zone_pct']]
    df['v275_break_bucket'] = [bkt_num(fnum(x), [0.2, 0.8, 1.5, 3], ['0_0_2', '0_2_0_8', '0_8_1_5', '1_5_3', 'GT3']) for x in df['raw_event_break20_pct']]
    df['v275_timeline_signature'] = (
        df['v275_ssl_vs_zone'].astype(str) + '|' +
        'ZONE_AGE_' + df['v275_zone_age_bucket'].astype(str) + '|' +
        'RETEST_' + df['v275_retest_delay_bucket'].astype(str)
    )

    baseline = metrics(df)
    dimensions = [
        'v275_ssl_vs_zone', 'v275_ssl_age_bucket', 'v275_zone_age_bucket', 'v275_retest_delay_bucket',
        'v275_risk_bucket', 'v275_chase_bucket', 'v275_break_bucket', 'exit_reason', 'v275_timeline_signature'
    ]
    group_tables = {}
    for dim in dimensions:
        rows = []
        for val, g in df.groupby(dim, dropna=False):
            m = metrics(g)
            rows.append({'dimension': dim, 'value': str(val), **m})
        tab = pd.DataFrame(rows).sort_values(['wr', 'avg', 'n'], ascending=[False, False, False])
        tab.to_csv(OUT / f'{dim}_metrics.csv', index=False)
        group_tables[dim] = tab.head(20).to_dict(orient='records')

    # Two/three-dimensional surfaces focused on chronological sequence, not outcome-leaky stock selection.
    surfaces = []
    combos = [
        ['v275_ssl_vs_zone', 'v275_retest_delay_bucket'],
        ['v275_ssl_vs_zone', 'v275_zone_age_bucket'],
        ['v275_ssl_vs_zone', 'v275_zone_age_bucket', 'v275_retest_delay_bucket'],
        ['v275_ssl_vs_zone', 'v275_retest_delay_bucket', 'v275_risk_bucket'],
        ['v275_ssl_vs_zone', 'v275_retest_delay_bucket', 'v275_chase_bucket'],
        ['v275_timeline_signature', 'v275_risk_bucket'],
    ]
    for cols in combos:
        for key, g in df.groupby(cols, dropna=False):
            if len(g) < 300:
                continue
            m = metrics(g)
            rec = {'surface': '+'.join(cols), 'key': '|'.join(map(str, key if isinstance(key, tuple) else (key,))), **m}
            surfaces.append(rec)
    surfaces_df = pd.DataFrame(surfaces).sort_values(['wr', 'avg', 'n'], ascending=[False, False, False])
    surfaces_df.to_csv(OUT / 'v275_chronological_surfaces.csv', index=False)

    # Non-leaky conclusion check: high-volume buckets that improve over raw but still fail production-grade quality.
    high_volume = surfaces_df[surfaces_df['n'] >= 1000].head(30).to_dict(orient='records') if len(surfaces_df) else []
    best_quality = surfaces_df.head(30).to_dict(orient='records') if len(surfaces_df) else []
    volume_ceiling = df.groupby('symbol').size().describe(percentiles=[.25, .5, .75, .9, .95]).to_dict()

    summary = {
        'version': 'V275_TEMPORAL_SEQUENCE_SIGNATURE_AUDIT_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'out_dir': str(OUT),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'input': str(SRC),
        'rows': int(len(df)),
        'baseline_raw_v262_2023_2026': baseline,
        'stock_opportunity_density_raw_v262': {k: (round(float(v), 4) if isinstance(v, float) else int(v)) for k, v in volume_ceiling.items()},
        'top_by_dimension': group_tables,
        'best_chronological_surfaces': best_quality,
        'best_high_volume_surfaces_n_ge_1000': high_volume,
        'artifacts': {
            'chronological_surfaces': str(OUT / 'v275_chronological_surfaces.csv'),
            'dimension_metric_csvs': [str(OUT / f'{d}_metrics.csv') for d in dimensions],
            'enriched_rows': str(OUT / 'v275_enriched_rows.csv.gz'),
        },
        'decision': 'NO_PRODUCTION_WRITE__TEMPORAL_COMBO_PARAM_AUDIT_ONLY',
    }
    df.to_csv(OUT / 'v275_enriched_rows.csv.gz', index=False, compression='gzip')
    (OUT / 'v275_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:12000])


if __name__ == '__main__':
    main()
