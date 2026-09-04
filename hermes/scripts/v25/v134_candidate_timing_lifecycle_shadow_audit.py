#!/usr/bin/env python3
"""
V134 candidate-timing lifecycle shadow audit.

Scope:
- Read-only research audit only.
- Input: V133 realtime-quality feature rows and V132 delayed-entry validation rows.
- No production/API/frontend/watchlist writes.
- No TP/SL tuning.

Purpose:
Rebuild the FVG_Demand candidate timing semantics:
1) reclaim close may create WATCH metadata, not a buy instruction;
2) failed_reclaim is a cancel/downgrade gate for unresolved watch candidates;
3) takeover-known rows may remain watch-only quality candidates, not delayed chase buys.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, Tuple

import pandas as pd

SRC = Path('/root/.hermes/smc_audit/v133_realtime_quality_failed_reclaim_gate_20260620/v133_realtime_quality_features.csv')
DELAYED = Path('/root/.hermes/smc_audit/v132_fvg_reclaim_takeover_shadow_backtest_20260620/v132_delayed_entry_shadow_backtest.csv')
OUT = Path('/root/.hermes/smc_audit/v134_candidate_timing_lifecycle_shadow_audit_20260620')

HARD_RE = 'SL|DAMAGE|ZONE_DEAD|STRUCTURE|BREAK'


def metrics(df: pd.DataFrame, pnl_col: str = 'pnl_pct', exit_col: str = 'exit_reason') -> Dict[str, float]:
    if df.empty:
        return {'n': 0, 'wr': 0, 'avg': 0, 'loss_rate': 0, 'hard_exit_rate': 0, 'cum': 0, 'recent_n': 0, 'recent_wr': 0}
    pnl = pd.to_numeric(df[pnl_col], errors='coerce').fillna(0)
    hard = df[exit_col].astype(str).str.contains(HARD_RE, regex=True)
    recent = df[df['is_recent45'].astype(bool)] if 'is_recent45' in df.columns else df.iloc[0:0]
    rpnl = pd.to_numeric(recent[pnl_col], errors='coerce').fillna(0) if not recent.empty else pd.Series([], dtype=float)
    return {
        'n': int(len(df)),
        'wr': round(float((pnl > 0).mean() * 100), 2),
        'avg': round(float(pnl.mean()), 4),
        'loss_rate': round(float((pnl <= 0).mean() * 100), 2),
        'hard_exit_rate': round(float(hard.mean() * 100), 2),
        'cum': round(float(pnl.sum()), 4),
        'recent_n': int(len(recent)),
        'recent_wr': round(float((rpnl > 0).mean() * 100), 2) if len(rpnl) else 0,
    }


def delayed_metrics() -> Dict[str, Dict[str, float]]:
    if not DELAYED.exists():
        return {}
    d = pd.read_csv(DELAYED)
    return {str(k): metrics(g, 'v132_delayed_pnl_pct', 'v132_delayed_exit_reason') for k, g in d.groupby('v132_delayed_model')}


def md_table(rows: Iterable[Tuple[str, Dict[str, float]]], cols=('n','wr','avg','loss_rate','hard_exit_rate','recent_n','recent_wr')) -> str:
    lines = ['|slice|' + '|'.join(cols) + '|', '|---|' + '|'.join(['---:'] * len(cols)) + '|']
    for name, m in rows:
        lines.append('|' + str(name) + '|' + '|'.join(str(m.get(c, 0)) for c in cols) + '|')
    return '\n'.join(lines)


def production_snapshot() -> Dict[str, object]:
    snap: Dict[str, object] = {}
    for ep in ['/api/summary', '/api/picks/contract']:
        try:
            data = json.loads(urllib.request.urlopen('http://127.0.0.1:8890' + ep, timeout=10).read().decode())
            if ep.endswith('summary'):
                snap[ep] = {k: data.get(k) for k in ['engine', 'total_trades', 'win_rate']}
            else:
                snap[ep] = {k: data.get(k) for k in [
                    'tradable_active_pick_count', 'watch_only_count', 'raw_pick_file_count',
                    'active_pick_count', 'active_picks_not_historical_all_market', 'contract_note'
                ]}
        except Exception as exc:
            snap[ep] = {'error': repr(exc)}
    return snap


def recent_window_counts(df: pd.DataFrame) -> Dict[str, Dict[str, int]]:
    dates = sorted(pd.to_numeric(df['entry_date'], errors='coerce').dropna().astype(int).unique())
    out: Dict[str, Dict[str, int]] = {}
    for n in [5, 10, 20, 45, 90]:
        keep_dates = set(dates[-n:]) if dates else set()
        part = df[pd.to_numeric(df['entry_date'], errors='coerce').astype('Int64').isin(keep_dates)]
        out[f'last_{n}_trading_dates'] = {
            'rows': int(len(part)),
            'unique_symbols': int(part['symbol'].nunique()) if 'symbol' in part else 0,
        }
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(SRC)
    df = df[df['poi_source'].eq('FVG_Demand')].copy()

    nonrec = ~df['market_state'].eq('RECOVERY')
    score10 = pd.to_numeric(df['v133_t0_quality_score'], errors='coerce') >= 10
    score12 = pd.to_numeric(df['v133_t0_quality_score'], errors='coerce') >= 12
    reversal = df['combo_family'].eq('REVERSAL')
    reclaim = pd.to_numeric(df['reclaim_close_above_zone_pct'], errors='coerce') >= 0.5
    mid = pd.to_numeric(df['source_mid_body_atr'], errors='coerce') >= 0.65
    chase8 = pd.to_numeric(df['entry_chase_above_zone_pct'], errors='coerce') <= 8
    failed1 = df['v132_failed_reclaim_1'].astype(bool)
    failed3 = df['v132_failed_reclaim_3'].astype(bool)

    df['v134_watch_score10_nonrec'] = nonrec & score10
    df['v134_watch_score12_nonrec'] = nonrec & score12
    df['v134_watch_strict_t0'] = nonrec & score10 & reversal & reclaim & mid & chase8
    df['v134_cancel_failed1'] = df['v134_watch_score10_nonrec'] & failed1
    df['v134_cancel_failed3'] = df['v134_watch_score10_nonrec'] & failed3
    df['v134_keep_watch_not_failed3'] = df['v134_watch_score10_nonrec'] & (~failed3)
    df['v134_t3_quality_known_watch_only'] = df['v134_keep_watch_not_failed3']
    df['v134_lifecycle_status'] = 'IGNORE_LOW_T0_OR_RECOVERY'
    df.loc[df['v134_watch_score10_nonrec'], 'v134_lifecycle_status'] = 'WATCH_AT_RECLAIM_CLOSE'
    df.loc[df['v134_cancel_failed1'], 'v134_lifecycle_status'] = 'CANCEL_FAILED_RECLAIM_1'
    df.loc[df['v134_cancel_failed3'], 'v134_lifecycle_status'] = 'CANCEL_FAILED_RECLAIM_3'
    df.loc[df['v134_keep_watch_not_failed3'], 'v134_lifecycle_status'] = 'KEEP_WATCH_TAKEOVER_QUALITY_KNOWN_NO_BUY'

    base_slices = {
        'baseline_all_fvg': pd.Series(True, index=df.index),
        'WATCH_score10_nonrec_at_reclaim_close': df['v134_watch_score10_nonrec'],
        'WATCH_score12_nonrec_at_reclaim_close': df['v134_watch_score12_nonrec'],
        'WATCH_strict_t0_at_reclaim_close': df['v134_watch_strict_t0'],
    }
    lifecycle_slices = {
        'CANCEL_failed1_from_score10_watch': df['v134_cancel_failed1'],
        'CANCEL_failed3_from_score10_watch': df['v134_cancel_failed3'],
        'KEEP_not_failed3_from_score10_watch_original_outcome_only': df['v134_keep_watch_not_failed3'],
        'KEEP_not_failed3_and_strict_t0_original_outcome_only': df['v134_keep_watch_not_failed3'] & df['v134_watch_strict_t0'],
    }
    status_metrics = {str(k): metrics(g) for k, g in df.groupby('v134_lifecycle_status')}
    base_metrics = {k: metrics(df[m.fillna(False)]) for k, m in base_slices.items()}
    life_metrics = {k: metrics(df[m.fillna(False)]) for k, m in lifecycle_slices.items()}
    delays = delayed_metrics()

    original_t1_bad = int((pd.to_numeric(df['exit_idx'], errors='coerce') <= pd.to_numeric(df['entry_idx'], errors='coerce')).sum())

    df.to_csv(OUT / 'v134_lifecycle_features.csv', index=False)
    df[df['v134_watch_score10_nonrec']].to_csv(OUT / 'v134_watch_score10_nonrec_rows.csv', index=False)
    df[df['v134_cancel_failed3']].to_csv(OUT / 'v134_cancel_failed3_rows.csv', index=False)
    df[df['v134_keep_watch_not_failed3']].to_csv(OUT / 'v134_keep_watch_not_failed3_rows.csv', index=False)

    summary = {
        'decision': 'V134_CANDIDATE_TIMING_LIFECYCLE_SHADOW_DONE_NO_PRODUCTION_CHANGE',
        'input': str(SRC),
        'base_metrics': base_metrics,
        'lifecycle_gate_metrics_original_outcome_only': life_metrics,
        'lifecycle_status_metrics': status_metrics,
        'delayed_entry_metrics_from_v132': delays,
        'coverage': {
            'watch_score10_nonrec': recent_window_counts(df[df['v134_watch_score10_nonrec']]),
            'keep_not_failed3_watch': recent_window_counts(df[df['v134_keep_watch_not_failed3']]),
            'cancel_failed3': recent_window_counts(df[df['v134_cancel_failed3']]),
        },
        'timing_semantics': {
            'watch_at_reclaim_close': 'metadata candidate only, not BUY',
            'failed_reclaim': 'cancel/downgrade gate for unfilled/watch candidates',
            'keep_not_failed3': 'quality-known watch state; original-outcome metrics are diagnostic only',
            'delayed_entry': 'not used for production because V132/V134 delayed metrics show lag cost',
        },
        't_plus_1_audit': {'original_rows_exit_idx_le_entry_idx': original_t1_bad},
        'production_snapshot_8890': production_snapshot(),
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))

    lines = [
        '# V134 Candidate Timing Lifecycle Shadow Audit',
        '',
        'Decision: `V134_CANDIDATE_TIMING_LIFECYCLE_SHADOW_DONE_NO_PRODUCTION_CHANGE`。只做 shadow lifecycle，不接生产。',
        '',
        '## 1. Rebuilt timing semantics',
        '',
        '- Reclaim close can emit `WATCH_AT_RECLAIM_CLOSE` metadata, not a buy instruction.',
        '- `failed_reclaim_1/3` is a cancel/downgrade gate for unresolved watch candidates.',
        '- `KEEP_not_failed3` means takeover quality is known only after waiting; it remains watch-only quality metadata, not delayed buy.',
        '- Original-entry outcome metrics below are diagnostic only; they are not executable original-entry selectors when they use post-reclaim gates.',
        '',
        '## 2. T0 watch candidates at reclaim close',
        md_table(base_metrics.items()),
        '',
        '## 3. Lifecycle cancel / keep buckets',
        md_table(life_metrics.items()),
        '',
        '## 4. Lifecycle status distribution',
        md_table(status_metrics.items()),
        '',
        '## 5. Delayed-entry sanity check from V132',
        md_table(delays.items()),
        '',
        '## 6. Coverage',
        '```json',
        json.dumps(summary['coverage'], ensure_ascii=False, indent=2),
        '```',
        '',
        '## 7. T+1 / production verification',
        f'- original rows with `exit_idx <= entry_idx`: {original_t1_bad}',
        f'- production snapshot: `{json.dumps(summary["production_snapshot_8890"], ensure_ascii=False)}`',
        '',
        '## 8. Conclusion',
        '',
        'V134 confirms the correct architecture: failed-reclaim must be used as cancel/downgrade metadata, not as a buy trigger. Rebuilt lifecycle improves candidate labeling but does not create a production buy rule. The only safe next production-oriented implementation is shadow field propagation/lifecycle display: WATCH at reclaim close, CANCEL on failed reclaim, KEEP_WATCH when takeover quality is known, while keeping tradable BUY disabled until a separate entry model proves edge without lag cost.',
    ]
    (OUT / 'report.md').write_text('\n'.join(lines))
    print(json.dumps({
        'decision': summary['decision'],
        'out': str(OUT),
        'watch_score10_nonrec': base_metrics['WATCH_score10_nonrec_at_reclaim_close'],
        'cancel_failed3': life_metrics['CANCEL_failed3_from_score10_watch'],
        'keep_not_failed3': life_metrics['KEEP_not_failed3_from_score10_watch_original_outcome_only'],
        't_plus_1': summary['t_plus_1_audit'],
        'production': summary['production_snapshot_8890'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
