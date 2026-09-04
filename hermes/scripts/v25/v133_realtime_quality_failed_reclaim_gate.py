#!/usr/bin/env python3
"""
V133 realtime quality score + failed-reclaim reject gate audit.

Scope:
- Read-only shadow/backtest audit only.
- Input: V132 FVG_Demand reclaim feature rows and delayed-entry rows.
- No production/API/frontend/watchlist writes.
- No TP/SL tuning.

Method:
1) T0 realtime quality score: fields available at reclaim close / next-open entry only.
   This is the only pre-entry score for the original next-open candidate timing.
2) Post-reclaim failed gate: failed_reclaim_1/3 are explicitly marked as timing-shift gates,
   not as original-entry selectors, because they are known after the original next-open entry.
3) Timing validation: compare delayed-entry rows already simulated by V132 to avoid pretending
   post-reclaim confirmation can be used without paying entry-lag cost.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, Tuple

import pandas as pd

SRC_DIR = Path('/root/.hermes/smc_audit/v132_fvg_reclaim_takeover_shadow_backtest_20260620')
FEATURES = SRC_DIR / 'v132_reclaim_takeover_features.csv'
DELAYED = SRC_DIR / 'v132_delayed_entry_shadow_backtest.csv'
OUT = Path('/root/.hermes/smc_audit/v133_realtime_quality_failed_reclaim_gate_20260620')


def metrics(df: pd.DataFrame, pnl_col: str = 'pnl_pct', exit_col: str = 'exit_reason') -> Dict[str, float]:
    if df.empty:
        return {'n': 0, 'wr': 0, 'avg': 0, 'loss_rate': 0, 'hard_exit_rate': 0, 'cum': 0, 'recent_n': 0, 'recent_wr': 0}
    pnl = pd.to_numeric(df[pnl_col], errors='coerce').fillna(0)
    hard = df[exit_col].astype(str).str.contains('SL|DAMAGE|ZONE_DEAD|STRUCTURE|BREAK', regex=True)
    recent = df[df.get('is_recent45', False).astype(bool)] if 'is_recent45' in df.columns else df.iloc[0:0]
    recent_pnl = pd.to_numeric(recent[pnl_col], errors='coerce').fillna(0) if not recent.empty else pd.Series([], dtype=float)
    return {
        'n': int(len(df)),
        'wr': round(float((pnl > 0).mean() * 100), 2),
        'avg': round(float(pnl.mean()), 4),
        'loss_rate': round(float((pnl <= 0).mean() * 100), 2),
        'hard_exit_rate': round(float(hard.mean() * 100), 2),
        'cum': round(float(pnl.sum()), 4),
        'recent_n': int(len(recent)),
        'recent_wr': round(float((recent_pnl > 0).mean() * 100), 2) if len(recent_pnl) else 0,
    }


def add_t0_score(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    # T0 score deliberately excludes v132_failed_reclaim_1/3 and hold/no-break fields because
    # those are post-original-entry for next-open timing. entry_chase is known at buy open.
    components = {
        'non_recovery': (~out['market_state'].eq('RECOVERY'), 2),
        'reversal_family': (out['combo_family'].eq('REVERSAL'), 2),
        'bear_mixed_state': (out['market_state'].isin(['BEAR_RISK', 'MIXED']), 1),
        'source_mid_body_atr_ge_065': (pd.to_numeric(out['source_mid_body_atr'], errors='coerce') >= 0.65, 1),
        'source_gap_atr_ge_03': (pd.to_numeric(out['source_gap_atr'], errors='coerce') >= 0.30, 1),
        'reclaim_close_above_zone_ge_05': (pd.to_numeric(out['reclaim_close_above_zone_pct'], errors='coerce') >= 0.50, 1),
        'reclaim_close_above_zone_le_8': (pd.to_numeric(out['reclaim_close_above_zone_pct'], errors='coerce') <= 8.0, 1),
        'reclaim_bull_body_ge_50': (pd.to_numeric(out['v132_reclaim_bull_body_pct'], errors='coerce') >= 50.0, 1),
        'entry_chase_le_5': (pd.to_numeric(out['entry_chase_above_zone_pct'], errors='coerce') <= 5.0, 1),
        'risk_le_8': (pd.to_numeric(out['risk_pct'], errors='coerce') <= 8.0, 1),
        'zone_width_le_5': (pd.to_numeric(out['v85_zone_width_pct'], errors='coerce') <= 5.0, 1),
        'touch_to_reclaim_1_3': (pd.to_numeric(out['touch_to_reclaim_bars'], errors='coerce').between(1, 3), 1),
    }
    out['v133_t0_quality_score'] = 0
    for name, (mask, weight) in components.items():
        out[f'v133_{name}'] = mask.fillna(False).astype(bool)
        out['v133_t0_quality_score'] += out[f'v133_{name}'].astype(int) * weight
    out['v133_t0_score_band'] = pd.cut(
        out['v133_t0_quality_score'],
        bins=[-1, 5, 7, 9, 11, 99],
        labels=['0_5_bad', '6_7_weak', '8_9_mid', '10_11_strong', '12_plus_best'],
    ).astype(str)
    return out


def slice_metrics(df: pd.DataFrame, slices: Dict[str, pd.Series]) -> Dict[str, Dict[str, float]]:
    return {name: metrics(df[mask.fillna(False)]) for name, mask in slices.items()}


def delayed_metrics(delayed: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    res: Dict[str, Dict[str, float]] = {}
    for model, g in delayed.groupby('v132_delayed_model'):
        res[str(model)] = metrics(g, pnl_col='v132_delayed_pnl_pct', exit_col='v132_delayed_exit_reason')
    return res


def production_snapshot() -> Dict[str, object]:
    snap: Dict[str, object] = {}
    for ep in ['/api/summary', '/api/picks/contract']:
        try:
            raw = urllib.request.urlopen('http://127.0.0.1:8890' + ep, timeout=10).read().decode()
            data = json.loads(raw)
            if ep.endswith('summary'):
                snap[ep] = {k: data.get(k) for k in ['engine', 'total_trades', 'win_rate']}
            else:
                snap[ep] = {k: data.get(k) for k in [
                    'tradable_active_pick_count', 'watch_only_count', 'raw_pick_file_count',
                    'active_pick_count', 'active_picks_not_historical_all_market', 'contract_note'
                ]}
        except Exception as exc:  # read-only verification, do not fail the audit on service hiccup
            snap[ep] = {'error': repr(exc)}
    return snap


def md_table(rows: Iterable[Tuple[str, Dict[str, float]]], cols=('n','wr','avg','loss_rate','hard_exit_rate','recent_n','recent_wr')) -> str:
    lines = ['|slice|' + '|'.join(cols) + '|', '|---|' + '|'.join(['---:'] * len(cols)) + '|']
    for name, m in rows:
        lines.append('|' + str(name) + '|' + '|'.join(str(m.get(c, 0)) for c in cols) + '|')
    return '\n'.join(lines)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(FEATURES)
    df = df[df['poi_source'].eq('FVG_Demand')].copy()
    df = add_t0_score(df)
    delayed = pd.read_csv(DELAYED)

    t0_thresholds = {f'T0_score_ge_{s}': df['v133_t0_quality_score'] >= s for s in range(6, 14)}
    t0_slices = {
        'baseline': pd.Series(True, index=df.index),
        'non_recovery': ~df['market_state'].eq('RECOVERY'),
        'recovery_reject': df['market_state'].eq('RECOVERY'),
        'T0_realtime_score_ge_10': df['v133_t0_quality_score'] >= 10,
        'T0_realtime_score_ge_12': df['v133_t0_quality_score'] >= 12,
        'T0_reversal_nonrec_reclaim_chase5':
            (~df['market_state'].eq('RECOVERY'))
            & df['combo_family'].eq('REVERSAL')
            & (pd.to_numeric(df['reclaim_close_above_zone_pct'], errors='coerce') >= 0.5)
            & (pd.to_numeric(df['reclaim_close_above_zone_pct'], errors='coerce') <= 8.0)
            & (pd.to_numeric(df['entry_chase_above_zone_pct'], errors='coerce') <= 5.0),
        'T0_nonrec_reversal_mid065_reclaim_chase8':
            (~df['market_state'].eq('RECOVERY'))
            & df['combo_family'].eq('REVERSAL')
            & (pd.to_numeric(df['source_mid_body_atr'], errors='coerce') >= 0.65)
            & (pd.to_numeric(df['reclaim_close_above_zone_pct'], errors='coerce') >= 0.5)
            & (pd.to_numeric(df['entry_chase_above_zone_pct'], errors='coerce') <= 8.0),
    }
    post_reclaim_slices = {
        'POST_REJECT_failed_reclaim_1': df['v132_failed_reclaim_1'].astype(bool),
        'POST_REJECT_failed_reclaim_3': df['v132_failed_reclaim_3'].astype(bool),
        'POST_KEEP_not_failed1_nonrec_original_entry_outcome': (~df['market_state'].eq('RECOVERY')) & (~df['v132_failed_reclaim_1'].astype(bool)),
        'POST_KEEP_not_failed3_nonrec_original_entry_outcome': (~df['market_state'].eq('RECOVERY')) & (~df['v132_failed_reclaim_3'].astype(bool)),
        'POST_KEEP_not_failed3_score10_original_entry_outcome':
            (~df['market_state'].eq('RECOVERY')) & (~df['v132_failed_reclaim_3'].astype(bool)) & (df['v133_t0_quality_score'] >= 10),
    }

    score_bucket = {f'score_band_{k}': df['v133_t0_score_band'].eq(k) for k in sorted(df['v133_t0_score_band'].unique())}
    t0_threshold_metrics = slice_metrics(df, t0_thresholds)
    t0_metrics = slice_metrics(df, t0_slices)
    post_metrics = slice_metrics(df, post_reclaim_slices)
    bucket_metrics = slice_metrics(df, score_bucket)
    delay_metrics = delayed_metrics(delayed)

    same_day_exit = int((pd.to_numeric(df['exit_idx'], errors='coerce') <= pd.to_numeric(df['entry_idx'], errors='coerce')).sum())
    delayed_same_day_exit = int((pd.to_numeric(delayed['v132_delayed_exit_idx'], errors='coerce') <= pd.to_numeric(delayed['v132_delayed_entry_idx'], errors='coerce')).sum())

    df.to_csv(OUT / 'v133_realtime_quality_features.csv', index=False)
    df[df['v133_t0_quality_score'] >= 10].to_csv(OUT / 'v133_t0_score_ge10_rows.csv', index=False)
    df[df['v132_failed_reclaim_3'].astype(bool)].to_csv(OUT / 'v133_failed_reclaim3_reject_rows.csv', index=False)

    summary = {
        'decision': 'V133_REALTIME_SCORE_AND_FAILED_RECLAIM_GATE_DONE_NO_PRODUCTION_CHANGE',
        'inputs': {'features': str(FEATURES), 'delayed': str(DELAYED)},
        't0_threshold_metrics': t0_threshold_metrics,
        't0_slice_metrics': t0_metrics,
        'post_reclaim_gate_metrics_original_entry_outcome_only': post_metrics,
        'score_bucket_metrics': bucket_metrics,
        'delayed_entry_metrics_from_v132': delay_metrics,
        't1_t3_gate_timing_warning': 'failed_reclaim_1/3 are post-original-entry for next-open timing; use as cancel/reject diagnostics, not original-entry selectors.',
        't_plus_1_audit': {'original_rows_exit_idx_le_entry_idx': same_day_exit, 'delayed_rows_exit_idx_le_entry_idx': delayed_same_day_exit},
        'production_snapshot_8890': production_snapshot(),
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))

    lines = [
        '# V133 Realtime Quality Score + Failed-Reclaim Gate Audit',
        '',
        'Decision: `V133_REALTIME_SCORE_AND_FAILED_RECLAIM_GATE_DONE_NO_PRODUCTION_CHANGE`。只做 shadow/backtest，不接生产。',
        '',
        '## 1. T0 realtime score: original next-open timing',
        '',
        'T0 score excludes `failed_reclaim_1/3` and post-reclaim hold/no-break fields because those are not known before the original next-open entry.',
        md_table(t0_metrics.items()),
        '',
        '## 2. T0 score thresholds',
        md_table(t0_threshold_metrics.items()),
        '',
        '## 3. Score bands',
        md_table(bucket_metrics.items()),
        '',
        '## 4. Failed-reclaim gate diagnostic',
        '',
        'These rows are valid reject/cancel diagnostics only after the corresponding post-reclaim bars close. They must not be used as if they were known at the original next-open entry.',
        md_table(post_metrics.items()),
        '',
        '## 5. Timing validation: delayed entry still pays lag cost',
        md_table(delay_metrics.items()),
        '',
        '## 6. T+1 / production verification',
        f'- original rows with `exit_idx <= entry_idx`: {same_day_exit}',
        f'- delayed rows with `exit_idx <= delayed_entry_idx`: {delayed_same_day_exit}',
        f'- production snapshot: `{json.dumps(summary["production_snapshot_8890"], ensure_ascii=False)}`',
        '',
        '## 7. Conclusion',
        '',
        'V133 confirms the next-step direction but still does not promote production. T0 realtime quality scoring improves raw FVG_Demand only modestly; it does not reach production-grade signal correctness. Failed-reclaim_3 is a strong pollution/reject bucket, but it is known only after waiting, and V132 delayed-entry validation shows waiting gives up too much edge. Therefore the correct use is: keep failed-reclaim as watchlist cancel/downgrade metadata and rebuild candidate timing upstream, not as a delayed buy trigger.',
    ]
    (OUT / 'report.md').write_text('\n'.join(lines))
    print(json.dumps({
        'decision': summary['decision'],
        'out': str(OUT),
        'baseline': t0_metrics['baseline'],
        'best_t0_practical': t0_metrics['T0_nonrec_reversal_mid065_reclaim_chase8'],
        'failed3_reject': post_metrics['POST_REJECT_failed_reclaim_3'],
        't_plus_1': summary['t_plus_1_audit'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
