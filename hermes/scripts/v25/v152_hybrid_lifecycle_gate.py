#!/usr/bin/env python3
"""V152 reproducible hybrid lifecycle gate backtest.

Input: V150 executed rows.
Rule:
- Start from BE_SL_50BP_SKIP_PBG rows (same selected universe as V150 best, n=127).
- For CANCEL_AFTER_ENTRY_DAY_CLOSE rows that would be converted to BE_SL by V150,
  keep original V138 baseline if v138_entry_above_reclaim_close_pct >= threshold.
- Otherwise keep V150 BE-SL result.
- PRE_BUY_GAP rows remain skipped because source variant is SKIP_PBG.

This recreates /root/.hermes/smc_audit/v152_hybrid_lifecycle_gate_backtest_20260622.
No production/frontend/API/watchlist writes.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path('/root/.hermes')
IN = ROOT / 'smc_audit' / 'v150_lifecycle_sl_adjust_backtest_20260621' / 'v150_executed_rows.csv'
OUT = ROOT / 'smc_audit' / 'v152_hybrid_lifecycle_gate_backtest_20260622'
OUT.mkdir(parents=True, exist_ok=True)


def bseries(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().eq('true')


def metrics(df: pd.DataFrame, pnl_col: str = 'v152_pnl_pct') -> dict[str, Any]:
    n = int(len(df))
    if n == 0:
        return {'n': 0, 'wr': 0.0, 'avg': 0.0, 'median': 0.0, 'loss': 0.0, 'hard_exit': 0.0, 'recent_n': 0, 'recent_wr': 0.0, 't1': 0}
    pnl = pd.to_numeric(df[pnl_col], errors='coerce').fillna(0.0)
    recent = df[bseries(df['is_recent45'])] if 'is_recent45' in df else df.iloc[0:0]
    rp = pd.to_numeric(recent[pnl_col], errors='coerce').fillna(0.0) if len(recent) else pd.Series(dtype=float)
    exit_hard = df['v152_exit_reason'].astype(str).isin(['ZONE_CLOSE_DEAD_T1', 'STRUCTURE_SL_T1', 'LIFECYCLE_CANCEL_NEXT_OPEN'])
    action_hard = df.get('v152_lifecycle_action', pd.Series([''] * n)).astype(str).str.startswith('BE_SL_HIT')
    hard = exit_hard | action_hard
    return {
        'n': n,
        'wr': round(float((pnl > 0).mean() * 100), 2),
        'avg': round(float(pnl.mean()), 4),
        'median': round(float(pnl.median()), 4),
        'loss': round(float((pnl <= 0).mean() * 100), 2),
        'hard_exit': round(float(hard.mean() * 100), 2),
        'recent_n': int(len(recent)),
        'recent_wr': round(float((rp > 0).mean() * 100), 2) if len(recent) else 0.0,
        't1': int(df.get('v152_t1_violation', pd.Series([False] * n)).astype(bool).sum()),
    }


def as_v152(row: pd.Series, threshold: float) -> dict[str, Any]:
    out = row.to_dict()
    keep_baseline = (
        str(row.get('v143_lifecycle_status')) == 'CANCEL_AFTER_ENTRY_DAY_CLOSE'
        and str(row.get('v150_lifecycle_action')).startswith('BE_SL')
        and float(row.get('v138_entry_above_reclaim_close_pct', -999.0)) >= threshold
    )
    if keep_baseline:
        out.update({
            'v152_entry_idx': row.get('v138_entry_idx'),
            'v152_entry_date': row.get('v138_entry_date'),
            'v152_entry_price': row.get('v138_entry_price'),
            'v152_exit_idx': row.get('v138_exit_idx'),
            'v152_exit_date': row.get('v138_exit_date'),
            'v152_exit_price': row.get('v138_exit_price'),
            'v152_exit_reason': row.get('v138_exit_reason'),
            'v152_pnl_pct': row.get('v138_pnl_pct'),
            'v152_t1_violation': bool(row.get('v138_t1_violation', False)),
            'v152_lifecycle_action': 'BASELINE',
            'v152_rule': f'KEEP_BASELINE_ENTRY_ABOVE_RECLAIM_GE_{threshold}',
        })
    else:
        out.update({
            'v152_entry_idx': row.get('v138_entry_idx'),
            'v152_entry_date': row.get('v138_entry_date'),
            'v152_entry_price': row.get('v138_entry_price'),
            'v152_exit_idx': row.get('v150_exit_idx', row.get('v138_exit_idx')),
            'v152_exit_date': row.get('v150_exit_date', row.get('v138_exit_date')),
            'v152_exit_price': row.get('v150_exit_price', row.get('v138_exit_price')),
            'v152_exit_reason': row.get('v150_exit_reason', row.get('v138_exit_reason')),
            'v152_pnl_pct': row.get('v150_pnl_pct', row.get('v138_pnl_pct')),
            'v152_t1_violation': bool(row.get('v150_t1_violation', row.get('v138_t1_violation', False))),
            'v152_lifecycle_action': row.get('v150_lifecycle_action'),
            'v152_rule': f'KEEP_V150_BE_SL_UNLESS_ENTRY_ABOVE_RECLAIM_GE_{threshold}',
        })
    out['v152_threshold_entry_above_reclaim_pct'] = threshold
    out['v152_variant'] = f'SKIP_PBG_BE_SL50_CANCEL_EXCEPT_ENTRY_ABOVE_RECLAIM_GE_{threshold:g}'
    return out


def group_metrics(df: pd.DataFrame, key: str) -> dict[str, dict[str, Any]]:
    return {str(k): metrics(v) for k, v in df.groupby(key, dropna=False)}


def main() -> None:
    df = pd.read_csv(IN, low_memory=False)
    baseline_src = df[df['v150_variant'].eq('BASELINE_V138_RECLAIM_NEXT_OPEN')].copy()
    base = baseline_src.copy()
    base['v152_pnl_pct'] = base['v138_pnl_pct']
    base['v152_exit_reason'] = base['v138_exit_reason']
    base['v152_t1_violation'] = base['v138_t1_violation']

    src = df[df['v150_variant'].eq('BE_SL_50BP_SKIP_PBG')].copy()
    thresholds = [0.1577, 0.2322, 0.2505, 0.01152, 0.0, -0.1849, -0.3673]

    rows = []
    variant_rows = []
    all_variant_frames = []
    for th in thresholds:
        part = pd.DataFrame([as_v152(r, th) for _, r in src.iterrows()])
        all_variant_frames.append(part)
        kept_cancel_n = int((part['v152_lifecycle_action'].eq('BASELINE') & part['v143_lifecycle_status'].eq('CANCEL_AFTER_ENTRY_DAY_CLOSE')).sum())
        variant_rows.append({'variant': part['v152_variant'].iloc[0], 'threshold': th, 'kept_cancel_n': kept_cancel_n, **metrics(part)})

    variant_df = pd.DataFrame(variant_rows).sort_values(['wr', 'avg'], ascending=[False, False])
    all_df = pd.concat(all_variant_frames, ignore_index=True)
    all_df.to_csv(OUT / 'v152_all_rows.csv', index=False)
    variant_df.to_csv(OUT / 'v152_variant_metrics.csv', index=False)

    best_variant = str(variant_df.iloc[0]['variant'])
    best = all_df[all_df['v152_variant'].eq(best_variant)].copy()
    best.to_csv(OUT / 'v152_best_rows.csv', index=False)

    v150_best = src.copy()
    v150_best['v152_pnl_pct'] = v150_best['v150_pnl_pct']
    v150_best['v152_exit_reason'] = v150_best['v150_exit_reason']
    v150_best['v152_t1_violation'] = v150_best['v150_t1_violation']
    v150_best['v152_lifecycle_action'] = v150_best['v150_lifecycle_action']

    base_m = metrics(base)
    v150_m = metrics(v150_best)
    best_m = metrics(best)
    release_gate = {
        'pass': bool(best_m['n'] >= 120 and best_m['wr'] >= base_m['wr'] + 2.0 and best_m['avg'] >= base_m['avg'] - 0.25 and best_m['t1'] == 0),
        'checks': {
            'n_ge_120': best_m['n'] >= 120,
            'wr_improve_ge_2pp': best_m['wr'] >= base_m['wr'] + 2.0,
            'avg_within_minus_0_25pp': best_m['avg'] >= base_m['avg'] - 0.25,
            't1_zero': best_m['t1'] == 0,
        },
    }
    summary = {
        'decision': 'V152_HYBRID_GATE_PROMOTABLE' if release_gate['pass'] else 'V152_HYBRID_GATE_RESEARCH_ONLY',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'production_write': False,
        'source_v150': str(IN),
        'out': str(OUT),
        'baseline_v138': base_m,
        'v150_best_skip_pbg_be_sl50': v150_m,
        'variant_metrics': variant_df.to_dict(orient='records'),
        'best_variant': best_variant,
        'best_threshold_entry_above_reclaim_pct': float(variant_df.iloc[0]['threshold']),
        'best_metrics': best_m,
        'best_status_summary': group_metrics(best, 'v143_lifecycle_status'),
        'best_action_summary': group_metrics(best, 'v152_lifecycle_action'),
        'release_gate': release_gate,
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

    report = [
        '# V152 Hybrid Lifecycle Gate Backtest', '',
        f"Decision: `{summary['decision']}`。只读回测，不改生产。", '',
        '规则：跳过 PRE_BUY_GAP_NOTE_ONLY；CANCEL_AFTER_ENTRY_DAY_CLOSE 默认用 V150 的 +50bp BE-SL；但如果 `entry_above_reclaim_close_pct >= threshold`，说明买入相对 reclaim close 已经有上行动能，保留 baseline，不强制 BE-SL。', '',
        '## Variant metrics', variant_df.to_markdown(index=False), '',
        '## Baseline vs best',
        pd.DataFrame([
            {'name': 'BASELINE_V138', **base_m},
            {'name': 'V150_SKIP_PBG_BE_SL50', **v150_m},
            {'name': 'V152_BEST', **best_m},
        ]).to_markdown(index=False), '',
        '## Release gate', '```json', json.dumps(release_gate, ensure_ascii=False, indent=2), '```'
    ]
    (OUT / 'report.md').write_text('\n'.join(report), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
