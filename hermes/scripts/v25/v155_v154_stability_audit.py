#!/usr/bin/env python3
"""V155: monthly/yearly/rolling stability audit for V154 chosen rows.

No production writes.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path('/root/.hermes')
IN = ROOT / 'smc_audit' / 'v154_cancel_addback_no_micro_20260622' / 'v154_chosen_rows.csv'
OUT = ROOT / 'smc_audit' / 'v155_v154_stability_audit_20260622'
OUT.mkdir(parents=True, exist_ok=True)


def fnum(df: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in df:
        return pd.Series([default] * len(df), index=df.index, dtype='float64')
    return pd.to_numeric(df[col], errors='coerce').fillna(default)


def metrics(df: pd.DataFrame) -> dict[str, Any]:
    n = int(len(df))
    if n == 0:
        return {'n': 0, 'wr': 0.0, 'avg': 0.0, 'median': 0.0, 'loss': 0.0, 'micro_n': 0, 'synthetic_be_n': 0, 't1': 0}
    pnl = fnum(df, 'v154_pnl_pct')
    return {
        'n': n,
        'wr': round(float((pnl > 0).mean() * 100), 2),
        'avg': round(float(pnl.mean()), 4),
        'median': round(float(pnl.median()), 4),
        'loss': round(float((pnl <= 0).mean() * 100), 2),
        'micro_n': int(pnl.between(0.45, 0.55, inclusive='both').sum()),
        'synthetic_be_n': int(df.get('v154_synthetic_be', pd.Series([False] * n)).astype(bool).sum()),
        't1': int(df.get('v154_t1_violation', pd.Series([False] * n)).astype(bool).sum()),
    }


def main() -> None:
    df = pd.read_csv(IN, low_memory=False)
    df['entry_date_dt'] = pd.to_datetime(df['v154_entry_date'].astype(str), format='%Y%m%d', errors='coerce')
    df['year'] = df['entry_date_dt'].dt.strftime('%Y')
    df['month'] = df['entry_date_dt'].dt.strftime('%Y-%m')
    df = df.sort_values('entry_date_dt').reset_index(drop=True)

    yearly = pd.DataFrame([{'year': y, **metrics(g)} for y, g in df.groupby('year')])
    monthly = pd.DataFrame([{'month': m, **metrics(g)} for m, g in df.groupby('month')])
    yearly.to_csv(OUT / 'v155_yearly_metrics.csv', index=False)
    monthly.to_csv(OUT / 'v155_monthly_metrics.csv', index=False)

    roll_rows = []
    for window in [30, 60, 90, 120]:
        tail = df.tail(window).copy()
        roll_rows.append({'window_last_n': window, **metrics(tail), 'start': str(tail['v154_entry_date'].iloc[0]) if len(tail) else '', 'end': str(tail['v154_entry_date'].iloc[-1]) if len(tail) else ''})
    rolling = pd.DataFrame(roll_rows)
    rolling.to_csv(OUT / 'v155_rolling_tail_metrics.csv', index=False)

    loss = df[fnum(df, 'v154_pnl_pct') <= 0].copy()
    loss.to_csv(OUT / 'v155_loss_rows.csv', index=False)
    loss_bucket_rows = []
    for key in ['year', 'month', 'v143_lifecycle_status', 'v141_earliest_lead_timing', 'v154_addback_rule', 'v154_exit_reason']:
        if key in df:
            for val, g in df.groupby(key, dropna=False):
                loss_bucket_rows.append({'bucket_key': key, 'bucket': str(val), **metrics(g)})
    loss_buckets = pd.DataFrame(loss_bucket_rows)
    loss_buckets.to_csv(OUT / 'v155_bucket_metrics.csv', index=False)

    weak_months = monthly[(monthly['n'] >= 3) & ((monthly['wr'] < 70.0) | (monthly['avg'] < 0.0))].copy()
    weak_months.to_csv(OUT / 'v155_weak_months.csv', index=False)

    m = metrics(df)
    release_gate = {
        'pass': bool(
            m['n'] >= 240 and m['wr'] >= 82.0 and m['avg'] >= 3.2 and m['synthetic_be_n'] == 0 and m['micro_n'] <= 2 and m['t1'] == 0
            and int((yearly['n'] >= 35).all()) == 1
            and int((yearly['wr'] >= 78.0).all()) == 1
            and int((rolling[rolling['window_last_n'].isin([30, 60, 90])]['wr'] >= 75.0).all()) == 1
        ),
        'checks': {
            'overall_n_wr_avg': m['n'] >= 240 and m['wr'] >= 82.0 and m['avg'] >= 3.2,
            'synthetic_be_zero': m['synthetic_be_n'] == 0,
            'micro_n_le_2': m['micro_n'] <= 2,
            't1_zero': m['t1'] == 0,
            'all_year_n_ge_35': bool((yearly['n'] >= 35).all()),
            'all_year_wr_ge_78': bool((yearly['wr'] >= 78.0).all()),
            'tail_30_60_90_wr_ge_75': bool((rolling[rolling['window_last_n'].isin([30, 60, 90])]['wr'] >= 75.0).all()),
        },
    }

    summary = {
        'decision': 'V155_STABILITY_PASS_READY_FOR_DRYRUN_SCANNER' if release_gate['pass'] else 'V155_STABILITY_FAIL_RESEARCH_ONLY',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'production_write': False,
        'source': str(IN),
        'out': str(OUT),
        'overall': m,
        'yearly': yearly.to_dict(orient='records'),
        'rolling_tail': rolling.to_dict(orient='records'),
        'weak_months': weak_months.to_dict(orient='records'),
        'release_gate': release_gate,
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    report = [
        '# V155 V154 Stability Audit', '',
        f"Decision: `{summary['decision']}`。只读研究，不写生产。", '',
        '## Overall', pd.DataFrame([m]).to_markdown(index=False), '',
        '## Yearly', yearly.to_markdown(index=False), '',
        '## Rolling tail', rolling.to_markdown(index=False), '',
        '## Weak months', weak_months.to_markdown(index=False) if len(weak_months) else '无 n>=3 且 WR<70 或 Avg<0 的月份。', '',
        '## Release gate', '```json', json.dumps(release_gate, ensure_ascii=False, indent=2), '```'
    ]
    (OUT / 'report.md').write_text('\n'.join(report), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
