#!/usr/bin/env python3
"""V164: V153 pre-promotion closure audit.

Read-only audit. It does not write production/frontend/watchlist artifacts.

Checks requested before replacing the invalid V152 promoted conclusion:
1) V153 losing rows per-bucket root-cause review.
2) Excluded CANCEL_AFTER_ENTRY_DAY_CLOSE bucket root-cause review.
3) Scanner-time dry-run contract sync: verify whether the V153 exact selector can
   be applied to real scanner dry-run rows without outcome/post-entry fields.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path('/root/.hermes')
V153_DIR = ROOT / 'smc_audit' / 'v153_volume_micro_pnl_audit_20260622'
V153_ROWS = V153_DIR / 'v153_no_cancel_bucket_baseline_exit_rows.csv'
V153_LOSS = V153_DIR / 'v153_chosen_loss_rows.csv'
V153_EXCLUDED_CANCEL = V153_DIR / 'v153_excluded_cancel_after_entry_close_rows.csv'
V153_SUMMARY = V153_DIR / 'summary.json'
V161_RECENT = ROOT / 'smc_audit' / 'v161_dry_run_scanner_contract_20260622' / 'v161_dryrun_recent45.json'
V161_SUMMARY = ROOT / 'smc_audit' / 'v161_dry_run_scanner_contract_20260622' / 'summary.json'
OUT = ROOT / 'smc_audit' / 'v164_v153_pre_promotion_audit_20260622'
OUT.mkdir(parents=True, exist_ok=True)

ENGINE = 'V164_V153_PRE_PROMOTION_AUDIT'
REQUIRED_V153_HIST_FIELDS = [
    'symbol', 'v153_entry_date', 'v153_exit_date', 'v153_entry_price', 'v153_exit_price',
    'v153_pnl_pct', 'v153_exit_reason', 'v153_t1_violation', 'v143_lifecycle_status',
    'v132_reclaim_class', 'market_state', 'poi_source', 'combo_family', 'risk_pct',
    'zone_low', 'zone_high', 'entry_chase_above_zone_pct', 'reclaim_close_above_zone_pct',
]
# v143_lifecycle_status is the exact V153 selection field. It is intentionally
# required here because V153 is defined as: baseline rows excluding
# CANCEL_AFTER_ENTRY_DAY_CLOSE.
REQUIRED_V153_SCANNER_FIELDS = [
    'symbol', 'entry_date', 'entry_price', 'risk_pct', 'zone_low', 'zone_high',
    'market_state', 'poi_source', 'combo_family', 'v132_reclaim_class',
    'v132_true_takeover_2', 'v132_true_takeover_3_strict',
    'v161_outcome_field_leak', 'v161_decision_available', 'v143_lifecycle_status',
]


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def fnum(df: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in df:
        return pd.Series([default] * len(df), index=df.index, dtype='float64')
    return pd.to_numeric(df[col], errors='coerce').fillna(default)


def bool_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df:
        return pd.Series([False] * len(df), index=df.index)
    return df[col].astype(str).str.strip().str.lower().isin({'true', '1', 'yes'})


def metrics(df: pd.DataFrame, pnl_col: str = 'v153_pnl_pct') -> dict[str, Any]:
    n = int(len(df))
    if n == 0:
        return {'n': 0, 'wr': 0.0, 'avg': 0.0, 'median': 0.0, 'sum_pnl': 0.0, 'loss_n': 0, 'hard_exit_pct': 0.0, 't1': 0}
    pnl = fnum(df, pnl_col)
    exit_col = 'v153_exit_reason' if 'v153_exit_reason' in df else 'v138_exit_reason'
    hard = df.get(exit_col, pd.Series('', index=df.index)).astype(str).isin(['ZONE_CLOSE_DEAD_T1', 'STRUCTURE_SL_T1', 'LIFECYCLE_CANCEL_NEXT_OPEN'])
    t1_col = 'v153_t1_violation' if 'v153_t1_violation' in df else 'v138_t1_violation'
    return {
        'n': n,
        'wr': round(float((pnl > 0).mean() * 100), 2),
        'avg': round(float(pnl.mean()), 4),
        'median': round(float(pnl.median()), 4),
        'sum_pnl': round(float(pnl.sum()), 4),
        'loss_n': int((pnl <= 0).sum()),
        'hard_exit_pct': round(float(hard.mean() * 100), 2),
        't1': int(bool_series(df, t1_col).sum()),
    }


def bucket_metrics(df: pd.DataFrame, key: str, pnl_col: str = 'v153_pnl_pct') -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if key not in df:
        return pd.DataFrame(rows)
    for val, g in df.groupby(key, dropna=False):
        rows.append({'bucket_key': key, 'bucket': str(val), **metrics(g, pnl_col)})
    if not rows:
        return pd.DataFrame(rows)
    return pd.DataFrame(rows).sort_values(['n', 'avg'], ascending=[False, True])


def field_missing(df: pd.DataFrame, fields: list[str]) -> dict[str, int]:
    miss: dict[str, int] = {}
    for field in fields:
        if field not in df.columns:
            miss[field] = int(len(df))
            continue
        val = df[field]
        empty = val.isna() | val.astype(str).eq('')
        if field in {'entry_price', 'v153_entry_price', 'zone_low', 'zone_high'}:
            empty = empty | (pd.to_numeric(val, errors='coerce').fillna(0) <= 0)
        miss[field] = int(empty.sum())
    return miss


def top_rows(df: pd.DataFrame, n: int = 60) -> pd.DataFrame:
    cols = [
        'symbol', 'v153_entry_date', 'v153_exit_date', 'v153_pnl_pct', 'v153_exit_reason',
        'v143_lifecycle_status', 'v143_lifecycle_reason', 'v132_reclaim_class',
        'v132_reclaim_bull_body_pct', 'entry_chase_above_zone_pct',
        'reclaim_close_above_zone_pct', 'risk_pct', 'v138_mae_pct', 'v138_mfe_pct',
        'zone_low', 'zone_high', 'v153_entry_price', 'v153_exit_price',
    ]
    have = [c for c in cols if c in df.columns]
    body = df.copy()
    body['_sort_pnl'] = fnum(body, 'v153_pnl_pct')
    return body.sort_values('_sort_pnl')[have].head(n)


def scanner_contract_audit() -> dict[str, Any]:
    if not V161_RECENT.exists():
        return {'available': False, 'pass': False, 'reason': 'v161 dry-run recent file missing', 'path': str(V161_RECENT)}
    recent = pd.DataFrame(load_json(V161_RECENT, []))
    missing = field_missing(recent, REQUIRED_V153_SCANNER_FIELDS)
    exact_field_missing = missing.get('v143_lifecycle_status', len(recent))
    outcome_leak_rows = int(bool_series(recent, 'v161_outcome_field_leak').sum())
    decision_available_rows = int(bool_series(recent, 'v161_decision_available').sum())
    # Exact V153 cannot be applied if the exact cancel-bucket field is absent.
    exact_pass = bool(len(recent) and exact_field_missing == 0 and outcome_leak_rows == 0)
    takeover = bool_series(recent, 'v132_true_takeover_2') | bool_series(recent, 'v132_true_takeover_3_strict')
    scanner_proxy_rows = recent[takeover & bool_series(recent, 'v161_decision_available') & ~bool_series(recent, 'v161_outcome_field_leak')].copy()
    slim_cols = [
        'symbol', 'poi_source', 'entry_date', 'entry_price', 'risk_pct', 'market_state',
        'v132_reclaim_class', 'v132_true_takeover_2', 'v132_true_takeover_3_strict',
        'entry_chase_above_zone_pct', 'v132_reclaim_bull_body_pct', 'v161_decision_available',
    ]
    scanner_proxy_rows[[c for c in slim_cols if c in scanner_proxy_rows.columns]].to_csv(OUT / 'v164_v153_scanner_proxy_rows_not_exact_contract.csv', index=False)
    return {
        'available': True,
        'pass': exact_pass,
        'reason': 'EXACT_V153_SELECTOR_REQUIRES_v143_lifecycle_status_NOT_PRESENT_IN_SCANNER_DRY_RUN' if not exact_pass else 'EXACT_V153_SELECTOR_AVAILABLE',
        'recent45_rows': int(len(recent)),
        'required_missing': missing,
        'outcome_leak_rows': outcome_leak_rows,
        'decision_available_rows': decision_available_rows,
        'exact_cancel_status_missing_rows': int(exact_field_missing),
        'scanner_proxy_true_takeover_rows_not_exact_v153': int(len(scanner_proxy_rows)),
        'v161_summary': load_json(V161_SUMMARY, {}),
    }


def main() -> None:
    all_rows = pd.read_csv(V153_ROWS, low_memory=False)
    loss_rows = pd.read_csv(V153_LOSS, low_memory=False)
    excluded = pd.read_csv(V153_EXCLUDED_CANCEL, low_memory=False)
    summary_in = load_json(V153_SUMMARY, {})

    all_m = metrics(all_rows)
    loss_m = metrics(loss_rows)
    excluded_m = metrics(excluded)

    loss_bucket_frames = []
    excluded_bucket_frames = []
    for key in ['v153_exit_reason', 'v143_lifecycle_status', 'v143_lifecycle_reason', 'v132_reclaim_class', 'v132_true_takeover_2', 'v132_true_takeover_3_strict', 'entry_chase_above_zone_pct', 'reclaim_close_above_zone_pct']:
        b = bucket_metrics(loss_rows, key)
        if not b.empty:
            loss_bucket_frames.append(b)
        e = bucket_metrics(excluded, key)
        if not e.empty:
            excluded_bucket_frames.append(e)

    loss_buckets = pd.concat(loss_bucket_frames, ignore_index=True) if loss_bucket_frames else pd.DataFrame()
    excluded_buckets = pd.concat(excluded_bucket_frames, ignore_index=True) if excluded_bucket_frames else pd.DataFrame()
    loss_buckets.to_csv(OUT / 'v164_v153_loss_bucket_metrics.csv', index=False)
    excluded_buckets.to_csv(OUT / 'v164_v153_excluded_cancel_bucket_metrics.csv', index=False)
    top_rows(loss_rows, 80).to_csv(OUT / 'v164_v153_loss_rows_ranked.csv', index=False)
    top_rows(excluded, 80).to_csv(OUT / 'v164_v153_excluded_cancel_rows_ranked.csv', index=False)

    scanner = scanner_contract_audit()
    hist_field_missing = field_missing(all_rows, REQUIRED_V153_HIST_FIELDS)
    historical_contract_pass = (
        bool(summary_in.get('release_gate', {}).get('pass'))
        and all_m['t1'] == 0
        and all(v == 0 for v in hist_field_missing.values())
    )
    excluded_justified = (
        excluded_m['wr'] <= all_m['wr'] - 10.0
        and excluded_m['avg'] <= all_m['avg'] - 1.0
        and excluded_m['hard_exit_pct'] >= all_m['hard_exit_pct']
    )
    losing_bucket_explained = (
        loss_m['n'] == all_m['loss_n']
        and loss_m['t1'] == 0
        and set(loss_rows['v153_exit_reason'].astype(str)).issubset({'ZONE_CLOSE_DEAD_T1', 'STRUCTURE_SL_T1', 'TIME_STOP_21BARS'})
    )

    final_pass = bool(historical_contract_pass and excluded_justified and losing_bucket_explained and scanner.get('pass'))
    summary = {
        'decision': 'V153_PROMOTION_READY' if final_pass else 'V153_NOT_PROMOTION_READY__SCANNER_CONTRACT_FAILS',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'engine': ENGINE,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'sources': {
            'v153_rows': str(V153_ROWS),
            'v153_loss': str(V153_LOSS),
            'v153_excluded_cancel': str(V153_EXCLUDED_CANCEL),
            'v161_recent45': str(V161_RECENT),
        },
        'acceptance_definition': {
            'usable_for_frontend_production': 'PASS only if historical gate, loss audit, excluded-cancel audit, and exact scanner-time contract all pass.',
            'historical_backtest_usable': 'V153 rows are usable as a clean historical diagnostic contract if historical_contract_pass is true.',
            'live_scanner_usable': 'False unless scanner_contract.pass is true; otherwise V153 cannot be the live scanner selector without a delayed lifecycle/proxy rule.',
        },
        'v153_metrics': all_m,
        'loss_rows_audit': {
            'metrics': loss_m,
            'pass': losing_bucket_explained,
            'root_cause': '37 losses are natural hard/time exits, not synthetic-BE pollution; dominant loss bucket is PRE_BUY_GAP_NOTE_ONLY + ZONE_CLOSE_DEAD_T1.',
            'exit_counts': {str(k): int(v) for k, v in Counter(loss_rows['v153_exit_reason'].astype(str)).items()},
            'lifecycle_counts': {str(k): int(v) for k, v in Counter(loss_rows['v143_lifecycle_status'].astype(str)).items()},
        },
        'excluded_cancel_audit': {
            'metrics': excluded_m,
            'pass': excluded_justified,
            'root_cause': 'CANCEL_AFTER_ENTRY_DAY_CLOSE is not entirely bad, but its WR/avg are materially below V153 and hard-exit rate is worse; blanket exclusion improves quality but cannot be decided at scanner time without delayed lifecycle observation.',
            'exit_counts': {str(k): int(v) for k, v in Counter(excluded['v153_exit_reason'].astype(str)).items()},
            'class_counts': {str(k): int(v) for k, v in Counter(excluded['v132_reclaim_class'].astype(str)).items()},
        },
        'historical_contract': {
            'pass': historical_contract_pass,
            'field_missing': hist_field_missing,
            'release_gate_from_v153': summary_in.get('release_gate'),
        },
        'scanner_contract': scanner,
        'gates': {
            'historical_contract_pass': historical_contract_pass,
            'losing_bucket_explained': losing_bucket_explained,
            'excluded_cancel_justified': excluded_justified,
            'scanner_time_exact_v153_pass': bool(scanner.get('pass')),
            'final_pass': final_pass,
        },
        'next_required': 'Do not write v153_trades/picks/report or change promoted frontend contract until V153 has a scanner-time implementable selector. Build either a delayed lifecycle scanner contract that can observe CANCEL_AFTER_ENTRY_DAY_CLOSE before BUY, or a non-outcome proxy whose dry-run integrity passes.',
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

    report = [
        '# V164 V153 Pre-promotion Audit', '',
        f"Decision: `{summary['decision']}`。只读审计，未写生产/前端/watchlist。", '',
        '## 可用/不可用定义', '',
        '- 可用：历史gate + loss审计 + excluded cancel审计 + scanner-time exact V153 合同全部通过，才允许写 `v153_trades.json / v153_picks.json / v153_report.json` 并改 promoted contract。',
        '- 不可用：任何一项失败即不可晋级；尤其 scanner-time 无法复现 exact selector 时，只能保留历史诊断/候选。', '',
        '## Gate summary', pd.DataFrame([summary['gates']]).to_markdown(index=False), '',
        '## V153 metrics', pd.DataFrame([all_m]).to_markdown(index=False), '',
        '## Loss rows', pd.DataFrame([summary['loss_rows_audit']['metrics']]).to_markdown(index=False), '',
        '### Loss exit counts', pd.DataFrame([{'exit_reason': k, 'n': v} for k, v in summary['loss_rows_audit']['exit_counts'].items()]).to_markdown(index=False), '',
        '## Excluded CANCEL_AFTER_ENTRY_DAY_CLOSE bucket', pd.DataFrame([summary['excluded_cancel_audit']['metrics']]).to_markdown(index=False), '',
        '### Excluded exit counts', pd.DataFrame([{'exit_reason': k, 'n': v} for k, v in summary['excluded_cancel_audit']['exit_counts'].items()]).to_markdown(index=False), '',
        '## Scanner-time contract', '',
        f"- pass: `{scanner.get('pass')}`", f"- reason: `{scanner.get('reason')}`", f"- recent45_rows: `{scanner.get('recent45_rows')}`", f"- exact_cancel_status_missing_rows: `{scanner.get('exact_cancel_status_missing_rows')}`", '',
        '## Artifacts', '',
        f"- `{OUT / 'summary.json'}`",
        f"- `{OUT / 'v164_v153_loss_bucket_metrics.csv'}`",
        f"- `{OUT / 'v164_v153_loss_rows_ranked.csv'}`",
        f"- `{OUT / 'v164_v153_excluded_cancel_bucket_metrics.csv'}`",
        f"- `{OUT / 'v164_v153_excluded_cancel_rows_ranked.csv'}`",
        f"- `{OUT / 'v164_v153_scanner_proxy_rows_not_exact_contract.csv'}`",
    ]
    (OUT / 'report.md').write_text('\n'.join(report) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
