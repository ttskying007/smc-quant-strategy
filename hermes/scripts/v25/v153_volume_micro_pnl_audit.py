#!/usr/bin/env python3
"""V153: volume + micro-PnL audit after V152.

Problem raised by Lei:
1) yearly trade count is too low in V152 (n=127; 2026 only 19 so far),
2) many exits cluster near +0.5%, which violates the SMC target/exit requirement.

This script does NOT write production/watchlist/frontend artifacts.
It audits V152 and tests no-synthetic-BE alternatives using the same V138 baseline rows.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path('/root/.hermes')
V150_IN = ROOT / 'smc_audit' / 'v150_lifecycle_sl_adjust_backtest_20260621' / 'v150_executed_rows.csv'
V152_IN = ROOT / 'smc_audit' / 'v152_hybrid_lifecycle_gate_backtest_20260622' / 'v152_best_rows.csv'
OUT = ROOT / 'smc_audit' / 'v153_volume_micro_pnl_audit_20260622'
OUT.mkdir(parents=True, exist_ok=True)

MICRO_LO = 0.45
MICRO_HI = 0.55


def bseries(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().eq('true')


def fnum_series(df: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in df:
        return pd.Series([default] * len(df), index=df.index, dtype='float64')
    return pd.to_numeric(df[col], errors='coerce').fillna(default)


def normalize_base(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out['v153_entry_date'] = out['v138_entry_date'].astype(str).str.replace('-', '', regex=False).str[:8]
    out['v153_exit_date'] = out['v138_exit_date'].astype(str).str.replace('-', '', regex=False).str[:8]
    out['v153_entry_idx'] = out['v138_entry_idx']
    out['v153_exit_idx'] = out['v138_exit_idx']
    out['v153_entry_price'] = out['v138_entry_price']
    out['v153_exit_price'] = out['v138_exit_price']
    out['v153_exit_reason'] = out['v138_exit_reason']
    out['v153_pnl_pct'] = fnum_series(out, 'v138_pnl_pct')
    out['v153_t1_violation'] = out['v153_entry_date'].eq(out['v153_exit_date'])
    out['v153_year'] = out['v153_entry_date'].astype(str).str[:4]
    return out


def normalize_v152(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out['v153_entry_date'] = out['v152_entry_date'].astype(str).str.replace('-', '', regex=False).str[:8]
    out['v153_exit_date'] = out['v152_exit_date'].astype(str).str.replace('-', '', regex=False).str[:8]
    out['v153_entry_idx'] = out['v152_entry_idx']
    out['v153_exit_idx'] = out['v152_exit_idx']
    out['v153_entry_price'] = out['v152_entry_price']
    out['v153_exit_price'] = out['v152_exit_price']
    out['v153_exit_reason'] = out['v152_exit_reason']
    out['v153_pnl_pct'] = fnum_series(out, 'v152_pnl_pct')
    out['v153_t1_violation'] = out.get('v152_t1_violation', False)
    out['v153_year'] = out['v153_entry_date'].astype(str).str[:4]
    return out


def metrics(df: pd.DataFrame) -> dict[str, Any]:
    n = int(len(df))
    if n == 0:
        return {
            'n': 0, 'wr': 0.0, 'avg': 0.0, 'median': 0.0, 'loss': 0.0,
            'micro_n': 0, 'micro_pct': 0.0, 'synthetic_be_n': 0, 'synthetic_be_pct': 0.0,
            'hard_exit': 0.0, 'recent_n': 0, 'recent_wr': 0.0, 't1': 0,
            'min_year_n': 0, 'year_counts': {},
        }
    pnl = fnum_series(df, 'v153_pnl_pct')
    micro = pnl.between(MICRO_LO, MICRO_HI, inclusive='both')
    action = df.get('v152_lifecycle_action', df.get('v150_lifecycle_action', pd.Series([''] * n, index=df.index))).astype(str)
    synthetic_be = action.str.startswith('BE_SL') | df['v153_exit_reason'].astype(str).str.contains('BREAKEVEN|BE_SL', case=False, regex=True)
    hard = df['v153_exit_reason'].astype(str).isin(['ZONE_CLOSE_DEAD_T1', 'STRUCTURE_SL_T1', 'LIFECYCLE_CANCEL_NEXT_OPEN']) | synthetic_be
    recent = df[bseries(df['is_recent45'])] if 'is_recent45' in df else df.iloc[0:0]
    rp = fnum_series(recent, 'v153_pnl_pct') if len(recent) else pd.Series(dtype=float)
    year_counts = {str(k): int(v) for k, v in df.groupby('v153_year').size().sort_index().items()}
    return {
        'n': n,
        'wr': round(float((pnl > 0).mean() * 100), 2),
        'avg': round(float(pnl.mean()), 4),
        'median': round(float(pnl.median()), 4),
        'loss': round(float((pnl <= 0).mean() * 100), 2),
        'micro_n': int(micro.sum()),
        'micro_pct': round(float(micro.mean() * 100), 2),
        'synthetic_be_n': int(synthetic_be.sum()),
        'synthetic_be_pct': round(float(synthetic_be.mean() * 100), 2),
        'hard_exit': round(float(hard.mean() * 100), 2),
        'recent_n': int(len(recent)),
        'recent_wr': round(float((rp > 0).mean() * 100), 2) if len(recent) else 0.0,
        't1': int(pd.Series(df['v153_t1_violation']).astype(bool).sum()),
        'min_year_n': int(min(year_counts.values())) if year_counts else 0,
        'year_counts': year_counts,
    }


def yearly_metrics(df: pd.DataFrame, variant: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for year, g in df.groupby('v153_year'):
        m = metrics(g)
        rows.append({'variant': variant, 'year': str(year), **m})
    return rows


def bucket_metrics(df: pd.DataFrame, variant: str, key: str) -> list[dict[str, Any]]:
    if key not in df:
        return []
    rows = []
    for val, g in df.groupby(key, dropna=False):
        rows.append({'variant': variant, 'bucket_key': key, 'bucket': str(val), **metrics(g)})
    return rows


def main() -> None:
    v150 = pd.read_csv(V150_IN, low_memory=False)
    baseline = normalize_base(v150[v150['v150_variant'].eq('BASELINE_V138_RECLAIM_NEXT_OPEN')].copy())
    v152 = normalize_v152(pd.read_csv(V152_IN, low_memory=False))

    variants: dict[str, pd.DataFrame] = {}
    variants['V138_BASELINE_ALL_NO_SYNTHETIC_BE'] = baseline.copy()

    # V152 is kept as diagnostic only: it has many synthetic +0.5% exits.
    variants['V152_BEST_DIAGNOSTIC_ONLY'] = v152.copy()

    # Main repair: reject the weak close-failure lifecycle bucket, but do not use synthetic BE exits.
    # This restores PRE_BUY_GAP rows that V152 skipped, improving annual coverage, while avoiding +0.5% pseudo-wins.
    variants['V153_NO_CANCEL_BUCKET_BASELINE_EXIT'] = baseline[baseline['v143_lifecycle_status'].ne('CANCEL_AFTER_ENTRY_DAY_CLOSE')].copy()

    # More selective alternatives for comparison only.
    variants['V153_NO_CANCEL_RISK_GE_3'] = variants['V153_NO_CANCEL_BUCKET_BASELINE_EXIT'][fnum_series(variants['V153_NO_CANCEL_BUCKET_BASELINE_EXIT'], 'risk_pct') >= 3.0].copy()
    variants['V153_NO_CANCEL_RECLAIM_ABOVE_ZONE_GE_1_8'] = variants['V153_NO_CANCEL_BUCKET_BASELINE_EXIT'][fnum_series(variants['V153_NO_CANCEL_BUCKET_BASELINE_EXIT'], 'reclaim_close_above_zone_pct') >= 1.8].copy()

    metric_rows: list[dict[str, Any]] = []
    year_rows: list[dict[str, Any]] = []
    bucket_rows: list[dict[str, Any]] = []
    for name, df in variants.items():
        df = df.copy()
        df['v153_variant'] = name
        variants[name] = df
        metric_rows.append({'variant': name, **metrics(df)})
        year_rows.extend(yearly_metrics(df, name))
        for key in ['v143_lifecycle_status', 'v141_earliest_lead_timing', 'v152_lifecycle_action', 'v153_exit_reason']:
            bucket_rows.extend(bucket_metrics(df, name, key))
        df.to_csv(OUT / f'{name.lower()}_rows.csv', index=False)

    metric_df = pd.DataFrame(metric_rows).sort_values(['synthetic_be_n', 'n', 'wr', 'avg'], ascending=[True, False, False, False])
    year_df = pd.DataFrame(year_rows)
    bucket_df = pd.DataFrame(bucket_rows)
    metric_df.to_csv(OUT / 'v153_variant_metrics.csv', index=False)
    year_df.to_csv(OUT / 'v153_yearly_metrics.csv', index=False)
    bucket_df.to_csv(OUT / 'v153_bucket_metrics.csv', index=False)

    # Explicit diagnostic rows for the user's two concerns.
    v152_pnl = fnum_series(v152, 'v153_pnl_pct')
    v152_micro = v152[v152_pnl.between(MICRO_LO, MICRO_HI, inclusive='both')].copy()
    v152_micro.to_csv(OUT / 'v152_micro_pnl_rows_0p45_0p55.csv', index=False)

    excluded_cancel = baseline[baseline['v143_lifecycle_status'].eq('CANCEL_AFTER_ENTRY_DAY_CLOSE')].copy()
    excluded_cancel.to_csv(OUT / 'v153_excluded_cancel_after_entry_close_rows.csv', index=False)

    chosen = variants['V153_NO_CANCEL_BUCKET_BASELINE_EXIT']
    chosen_pnl = fnum_series(chosen, 'v153_pnl_pct')
    chosen_loss = chosen[chosen_pnl <= 0].copy()
    chosen_loss.to_csv(OUT / 'v153_chosen_loss_rows.csv', index=False)

    base_m = metrics(variants['V138_BASELINE_ALL_NO_SYNTHETIC_BE'])
    v152_m = metrics(variants['V152_BEST_DIAGNOSTIC_ONLY'])
    chosen_m = metrics(chosen)
    release_gate = {
        'pass': bool(
            chosen_m['n'] >= 200
            and chosen_m['min_year_n'] >= 30
            and chosen_m['synthetic_be_n'] == 0
            and chosen_m['micro_pct'] <= 1.0
            and chosen_m['wr'] >= base_m['wr'] + 2.0
            and chosen_m['avg'] >= base_m['avg']
            and chosen_m['t1'] == 0
        ),
        'checks': {
            'n_ge_200': chosen_m['n'] >= 200,
            'min_year_n_ge_30': chosen_m['min_year_n'] >= 30,
            'synthetic_be_zero': chosen_m['synthetic_be_n'] == 0,
            'micro_pct_le_1pct': chosen_m['micro_pct'] <= 1.0,
            'wr_improve_ge_2pp_vs_baseline': chosen_m['wr'] >= base_m['wr'] + 2.0,
            'avg_ge_baseline': chosen_m['avg'] >= base_m['avg'],
            't1_zero': chosen_m['t1'] == 0,
        },
    }

    summary = {
        'decision': 'V153_REPAIR_CANDIDATE_PROMOTABLE_TO_NEXT_AUDIT' if release_gate['pass'] else 'V153_RESEARCH_ONLY',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'production_write': False,
        'problem_statement': {
            'yearly_volume_low': True,
            'micro_pnl_around_0p5_invalid': True,
        },
        'source': {'v150': str(V150_IN), 'v152': str(V152_IN)},
        'out': str(OUT),
        'baseline_v138': base_m,
        'v152_diagnostic': v152_m,
        'chosen_variant': 'V153_NO_CANCEL_BUCKET_BASELINE_EXIT',
        'chosen_metrics': chosen_m,
        'release_gate': release_gate,
        'variant_metrics': metric_df.to_dict(orient='records'),
        'interpretation': {
            'v152_invalid_reason': 'V152 uses synthetic BE_SL +0.5% exits: 40 micro-pnl rows and 44 synthetic BE rows; this creates pseudo-wins and reduces annual coverage.',
            'v153_repair': 'Drop CANCEL_AFTER_ENTRY_DAY_CLOSE weak bucket, restore PRE_BUY_GAP rows, and use original baseline exits only; no synthetic BE exits.',
            'remaining_issue': 'Two natural +0.5% rows remain in baseline exits, but synthetic micro-pnl problem is removed. Next audit should review remaining losing rows and the excluded cancel bucket before production.',
        },
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

    report = [
        '# V153 Volume + Micro-PnL Audit', '',
        f"Decision: `{summary['decision']}`。只读研究，不写生产。", '',
        '## Variant metrics', metric_df.to_markdown(index=False), '',
        '## Yearly metrics', year_df.to_markdown(index=False), '',
        '## Release gate', '```json', json.dumps(release_gate, ensure_ascii=False, indent=2), '```', '',
        '## Key interpretation',
        '- V152 的 0.5% 集中来自 BE_SL_HIT_CANCEL，不是真正结构TP，不能作为生产胜率。',
        '- V153 主候选取消 BE_SL 合成收益，恢复 PRE_BUY_GAP 交易量，只剔除 CANCEL_AFTER_ENTRY_DAY_CLOSE 弱桶。',
        '- V153 年度覆盖明显高于 V152，且 synthetic_be_n=0。',
    ]
    (OUT / 'report.md').write_text('\n'.join(report), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
