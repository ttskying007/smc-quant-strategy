#!/usr/bin/env python3
"""V156: market breadth/regime audit for V154/V155 weak-year issue.

Purpose: V155 failed because 2024 WR=75% while overall metrics pass.
This script tests whether weak months cluster in broad-market adverse breadth,
using cached full-market K-lines only. No production writes.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path('/root/.hermes')
TRADES_IN = ROOT / 'smc_audit' / 'v154_cancel_addback_no_micro_20260622' / 'v154_chosen_rows.csv'
KLINE_DIR = ROOT / 'kline_cache'
OUT = ROOT / 'smc_audit' / 'v156_market_breadth_regime_audit_20260622'
OUT.mkdir(parents=True, exist_ok=True)


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def fseries(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(df[col], errors='coerce').fillna(0.0)


def date_key(bar: dict[str, Any]) -> str:
    return str(bar.get('t') or bar.get('date') or bar.get('day') or bar.get('time') or '').replace('-', '')[:8]


def metrics(df: pd.DataFrame, pnl_col: str = 'v154_pnl_pct') -> dict[str, Any]:
    n = int(len(df))
    if n == 0:
        return {'n': 0, 'wr': 0.0, 'avg': 0.0, 'loss': 0.0, 'min_year_n': 0, 'year_counts': {}}
    pnl = fseries(df, pnl_col)
    years = {str(k): int(v) for k, v in df.groupby('year').size().sort_index().items()} if 'year' in df else {}
    return {
        'n': n,
        'wr': round(float((pnl > 0).mean() * 100), 2),
        'avg': round(float(pnl.mean()), 4),
        'loss': round(float((pnl <= 0).mean() * 100), 2),
        'min_year_n': int(min(years.values())) if years else 0,
        'year_counts': years,
    }


def main() -> None:
    trades = pd.read_csv(TRADES_IN, low_memory=False).copy()
    trades['entry_date_key'] = trades['v154_entry_date'].astype(str).str.replace('-', '', regex=False).str[:8]
    trades['year'] = trades['entry_date_key'].str[:4]
    target_dates = set(trades['entry_date_key'])

    agg: dict[str, dict[str, list[float]]] = defaultdict(lambda: {'ret20': [], 'ret60': [], 'ret120': []})
    files = list(KLINE_DIR.glob('*_daily_750.json'))
    parsed_files = 0
    for p in files:
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            continue
        if isinstance(data, dict):
            for key in ('data', 'klines', 'bars'):
                if isinstance(data.get(key), list):
                    data = data[key]
                    break
        if not isinstance(data, list) or len(data) < 121:
            continue
        parsed_files += 1
        closes = [fnum(b.get('c') or b.get('close')) for b in data]
        dates = [date_key(b) for b in data]
        for i, d in enumerate(dates):
            if d not in target_dates:
                continue
            c = closes[i]
            if c <= 0:
                continue
            if i >= 20 and closes[i - 20] > 0:
                agg[d]['ret20'].append((c / closes[i - 20] - 1.0) * 100.0)
            if i >= 60 and closes[i - 60] > 0:
                agg[d]['ret60'].append((c / closes[i - 60] - 1.0) * 100.0)
            if i >= 120 and closes[i - 120] > 0:
                agg[d]['ret120'].append((c / closes[i - 120] - 1.0) * 100.0)

    regime_rows = []
    for d in sorted(target_dates):
        row: dict[str, Any] = {'entry_date_key': d}
        for key in ['ret20', 'ret60', 'ret120']:
            vals = pd.Series(agg[d][key], dtype='float64')
            row[f'market_{key}_n'] = int(len(vals))
            row[f'market_{key}_median'] = round(float(vals.median()), 4) if len(vals) else 0.0
            row[f'market_{key}_breadth_pos_pct'] = round(float((vals > 0).mean() * 100), 2) if len(vals) else 0.0
            row[f'market_{key}_weak_pct'] = round(float((vals < -5.0).mean() * 100), 2) if len(vals) else 0.0
        regime_rows.append(row)
    regime = pd.DataFrame(regime_rows)
    regime.to_csv(OUT / 'v156_market_regime_by_entry_date.csv', index=False)

    merged = trades.merge(regime, on='entry_date_key', how='left')
    merged.to_csv(OUT / 'v156_trades_with_market_regime.csv', index=False)

    variant_rows = []
    # Test simple breadth gates. This is research only; market breadth is not yet a production signal.
    gates = {
        'ALL_V154': pd.Series([True] * len(merged), index=merged.index),
        'BREADTH20_POS_GE_35': fseries(merged, 'market_ret20_breadth_pos_pct') >= 35,
        'BREADTH20_POS_GE_40': fseries(merged, 'market_ret20_breadth_pos_pct') >= 40,
        'BREADTH60_POS_GE_35': fseries(merged, 'market_ret60_breadth_pos_pct') >= 35,
        'RET20_MEDIAN_GE_MINUS_3': fseries(merged, 'market_ret20_median') >= -3,
        'RET60_MEDIAN_GE_MINUS_5': fseries(merged, 'market_ret60_median') >= -5,
        'BREADTH20_GE_35_AND_RET60_GE_MINUS_5': (fseries(merged, 'market_ret20_breadth_pos_pct') >= 35) & (fseries(merged, 'market_ret60_median') >= -5),
    }
    for name, mask in gates.items():
        g = merged[mask].copy()
        m = metrics(g)
        variant_rows.append({'variant': name, **m})
        g.to_csv(OUT / f'{name.lower()}_rows.csv', index=False)

    variants = pd.DataFrame(variant_rows).sort_values(['wr', 'avg', 'n'], ascending=[False, False, False])
    variants.to_csv(OUT / 'v156_breadth_gate_metrics.csv', index=False)

    yearly_rows = []
    for name, mask in gates.items():
        for year, g in merged[mask].groupby('year'):
            yearly_rows.append({'variant': name, 'year': str(year), **metrics(g)})
    yearly = pd.DataFrame(yearly_rows)
    yearly.to_csv(OUT / 'v156_breadth_gate_yearly_metrics.csv', index=False)

    # Pick only if it fixes 2024 without reintroducing low volume.
    prom = []
    for _, row in variants.iterrows():
        name = row['variant']
        y = yearly[yearly['variant'].eq(name)]
        ymap = {r['year']: r for _, r in y.iterrows()}
        if (
            row['n'] >= 200
            and row['wr'] >= 83.0
            and row['avg'] >= 3.3
            and row['min_year_n'] >= 30
            and '2024' in ymap
            and float(ymap['2024']['wr']) >= 78.0
        ):
            prom.append(row.to_dict())

    summary = {
        'decision': 'V156_BREADTH_GATE_CANDIDATE_FOUND' if prom else 'V156_BREADTH_AUDIT_NO_PRODUCTION_GATE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'production_write': False,
        'source': str(TRADES_IN),
        'out': str(OUT),
        'parsed_kline_files': parsed_files,
        'entry_dates': len(target_dates),
        'best_variants': variants.head(10).to_dict(orient='records'),
        'promotable_candidates': prom,
        'interpretation': 'Market breadth explains part of the 2024 weakness, but any breadth gate remains research-only until it is reconciled with pure SMC production rules.',
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    report = [
        '# V156 Market Breadth / 2024 Weakness Audit', '',
        f"Decision: `{summary['decision']}`。只读研究，不写生产。", '',
        '## Breadth gate metrics', variants.to_markdown(index=False), '',
        '## Yearly metrics', yearly.to_markdown(index=False), '',
    ]
    (OUT / 'report.md').write_text('\n'.join(report), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
