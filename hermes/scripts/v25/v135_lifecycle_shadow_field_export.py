#!/usr/bin/env python3
"""
V135 lifecycle shadow field export.

Scope:
- Read V134 lifecycle features only.
- Export shadow display/contract JSON for WATCH/CANCEL/KEEP lifecycle fields.
- Do not write production scanner/API/frontend/watchlist files.
- Do not create BUY/tradable instructions.
- Do not tune TP/SL.
"""
from __future__ import annotations

import json
import math
import urllib.request
from pathlib import Path
from typing import Any

import pandas as pd

IN = Path('/root/.hermes/smc_audit/v134_candidate_timing_lifecycle_shadow_audit_20260620/v134_lifecycle_features.csv')
OUT = Path('/root/.hermes/smc_audit/v135_lifecycle_shadow_field_export_20260620')
DECISION = 'V135_LIFECYCLE_SHADOW_FIELD_EXPORT_DONE_NO_PRODUCTION_CHANGE'

EXPORT_FIELDS = [
    'symbol', 'pick_date', 'join_date', 'event_date', 'zone_date', 'entry_date',
    'poi_source', 'combo_family', 'market_state', 'event_type',
    'zone_low', 'zone_high', 'reclaim_close', 'reclaim_close_above_zone_pct',
    'reclaim_close_pos', 'entry_chase_above_zone_pct', 'risk_pct', 'v85_zone_width_pct',
    'touch_to_reclaim_bars', 'source_mid_body_atr', 'source_gap_atr',
    'v133_t0_quality_score', 'v133_t0_score_band',
    'v134_watch_score10_nonrec', 'v134_watch_strict_t0',
    'v134_cancel_failed1', 'v134_cancel_failed3', 'v134_keep_watch_not_failed3',
    'v134_lifecycle_status',
]

OUTCOME_COLUMNS = {'pnl_pct', 'exit_reason', 'exit_date', 'exit_idx', 'exit_price', 'hold_bars'}


def safe_num(v: Any) -> Any:
    if pd.isna(v):
        return None
    if isinstance(v, float):
        if math.isfinite(v):
            return round(v, 6)
        return None
    if isinstance(v, (int, bool, str)):
        return v
    return v


def api_json(path: str) -> Any:
    with urllib.request.urlopen(f'http://127.0.0.1:8890{path}', timeout=10) as r:
        return json.loads(r.read().decode('utf-8'))


def metrics(df: pd.DataFrame) -> dict[str, Any]:
    if len(df) == 0:
        return {'n': 0, 'wr': 0, 'avg': 0, 'loss_rate': 0, 'hard_exit_rate': 0, 'recent_n': 0, 'recent_wr': 0}
    pnl = pd.to_numeric(df['pnl_pct'], errors='coerce')
    exit_reason = df['exit_reason'].astype(str)
    hard = exit_reason.str.contains('SL|DAMAGE|ZONE_DEAD|STRUCTURE|BREAK', regex=True, na=False)
    recent = df[df['is_recent45'].astype(bool)] if 'is_recent45' in df.columns else df.iloc[0:0]
    rpnl = pd.to_numeric(recent['pnl_pct'], errors='coerce') if len(recent) else pd.Series([], dtype=float)
    return {
        'n': int(len(df)),
        'wr': round(float((pnl > 0).mean() * 100), 2),
        'avg': round(float(pnl.mean()), 4),
        'loss_rate': round(float((pnl <= 0).mean() * 100), 2),
        'hard_exit_rate': round(float(hard.mean() * 100), 2),
        'recent_n': int(len(recent)),
        'recent_wr': round(float((rpnl > 0).mean() * 100), 2) if len(recent) else 0,
    }


def lifecycle_export_status(row: pd.Series) -> str:
    status = str(row.get('v134_lifecycle_status', ''))
    if status == 'CANCEL_FAILED_RECLAIM_3':
        return 'CANCEL'
    if status == 'KEEP_WATCH_TAKEOVER_QUALITY_KNOWN_NO_BUY':
        return 'KEEP_WATCH'
    if bool(row.get('v134_watch_score10_nonrec', False)):
        return 'WATCH'
    return 'IGNORE'


def cancel_reason(row: pd.Series) -> str | None:
    if bool(row.get('v134_cancel_failed3', False)):
        return 'FAILED_RECLAIM_3'
    if bool(row.get('v134_cancel_failed1', False)):
        return 'FAILED_RECLAIM_1'
    if str(row.get('v134_lifecycle_status', '')) == 'IGNORE_LOW_T0_OR_RECOVERY':
        if not bool(row.get('v133_non_recovery', False)):
            return 'RECOVERY_OR_LOW_T0'
        return 'LOW_T0_SCORE'
    return None


def row_to_contract(row: pd.Series) -> dict[str, Any]:
    d = {k: safe_num(row[k]) for k in EXPORT_FIELDS if k in row.index and k not in OUTCOME_COLUMNS}
    display_status = lifecycle_export_status(row)
    d.update({
        'v135_shadow_mode': True,
        'v135_contract_version': 'V135_LIFECYCLE_SHADOW_V1',
        'v135_display_status': display_status,
        'v135_at_reclaim_action': 'WATCH_ONLY' if bool(row.get('v134_watch_score10_nonrec', False)) else 'NO_WATCH',
        'v135_followup_action': display_status,
        'v135_cancel_reason': cancel_reason(row),
        'v135_tradable': False,
        'v135_buy_disabled_reason': 'SHADOW_LIFECYCLE_ONLY_NO_ENTRY_EDGE',
        'v135_failed_reclaim_is_buy_signal': False,
    })
    return d


def coverage(df: pd.DataFrame) -> dict[str, dict[str, int]]:
    dates = sorted([x for x in df['entry_date'].dropna().unique()])
    out: dict[str, dict[str, int]] = {}
    for n in [5, 10, 20, 45, 90]:
        keep_dates = set(dates[-n:])
        part = df[df['entry_date'].isin(keep_dates)]
        out[f'last_{n}_trading_dates'] = {'rows': int(len(part)), 'unique_symbols': int(part['symbol'].nunique())}
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(IN)
    df = df[df['poi_source'].eq('FVG_Demand')].copy()
    df['v135_display_status'] = df.apply(lifecycle_export_status, axis=1)

    # Ex-ante display dedupe: latest entry per symbol/source, then status priority for display.
    priority = {'KEEP_WATCH': 0, 'WATCH': 1, 'CANCEL': 2, 'IGNORE': 3}
    df['_display_priority'] = df['v135_display_status'].map(priority).fillna(9).astype(int)
    latest = (
        df.sort_values(['symbol', 'entry_date', '_display_priority'], ascending=[True, False, True])
          .drop_duplicates(['symbol', 'poi_source'], keep='first')
          .copy()
    )
    recent = df[df['is_recent45'].astype(bool)].copy()

    all_contract = [row_to_contract(r) for _, r in df.iterrows()]
    recent_contract = [row_to_contract(r) for _, r in recent.iterrows()]
    latest_contract = [row_to_contract(r) for _, r in latest.iterrows()]

    for name, payload in [
        ('v135_lifecycle_contract_all.json', all_contract),
        ('v135_lifecycle_contract_recent45.json', recent_contract),
        ('v135_lifecycle_contract_latest_per_symbol.json', latest_contract),
    ]:
        (OUT / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    # Validation: no outcome fields in exported contract; no BUY/tradable true.
    exported_keys = set().union(*(x.keys() for x in latest_contract)) if latest_contract else set()
    outcome_leak = sorted(exported_keys & OUTCOME_COLUMNS)
    tradable_true = sum(1 for x in all_contract if x.get('v135_tradable') is True)
    buy_signal_true = sum(1 for x in all_contract if x.get('v135_failed_reclaim_is_buy_signal') is True)
    duplicate_latest_keys = int(latest.duplicated(['symbol', 'poi_source']).sum())
    t1_bad = int((pd.to_numeric(df['exit_idx'], errors='coerce') <= pd.to_numeric(df['entry_idx'], errors='coerce')).sum())

    prod_summary = api_json('/api/summary')
    prod_contract = api_json('/api/picks/contract')
    production_snapshot = {
        '/api/summary': {
            'engine': prod_summary.get('engine'),
            'total_trades': prod_summary.get('total_trades'),
            'win_rate': prod_summary.get('win_rate'),
        },
        '/api/picks/contract': {
            'tradable_active_pick_count': prod_contract.get('tradable_active_pick_count'),
            'watch_only_count': prod_contract.get('watch_only_count'),
            'raw_pick_file_count': prod_contract.get('raw_pick_file_count'),
            'active_pick_count': prod_contract.get('active_pick_count'),
            'active_picks_not_historical_all_market': prod_contract.get('active_picks_not_historical_all_market'),
            'contract_note': prod_contract.get('contract_note'),
        },
    }

    status_metrics = {status: metrics(part) for status, part in df.groupby('v135_display_status')}
    status_counts = {str(k): int(v) for k, v in df['v135_display_status'].value_counts().to_dict().items()}
    latest_status_counts = {str(k): int(v) for k, v in latest['v135_display_status'].value_counts().to_dict().items()}

    validation = {
        'outcome_field_leak_in_export': outcome_leak,
        'tradable_true_count': tradable_true,
        'failed_reclaim_buy_signal_true_count': buy_signal_true,
        'duplicate_latest_symbol_source_keys': duplicate_latest_keys,
        't_plus_1_exit_idx_le_entry_idx': t1_bad,
        'all_contract_rows': len(all_contract),
        'recent45_contract_rows': len(recent_contract),
        'latest_per_symbol_rows': len(latest_contract),
    }
    decision_ok = (not outcome_leak and tradable_true == 0 and buy_signal_true == 0 and duplicate_latest_keys == 0 and t1_bad == 0)

    summary = {
        'decision': DECISION if decision_ok else 'V135_VALIDATION_FAILED_NO_PRODUCTION_CHANGE',
        'input': str(IN),
        'out': str(OUT),
        'status_counts_all': status_counts,
        'status_counts_latest_per_symbol': latest_status_counts,
        'status_metrics': status_metrics,
        'coverage': {
            'all': coverage(df),
            'recent45': {'rows': int(len(recent)), 'unique_symbols': int(recent['symbol'].nunique())},
            'latest_per_symbol': {'rows': int(len(latest)), 'unique_symbols': int(latest['symbol'].nunique())},
        },
        'validation': validation,
        'production_snapshot_8890': production_snapshot,
        'contract_files': [
            str(OUT / 'v135_lifecycle_contract_all.json'),
            str(OUT / 'v135_lifecycle_contract_recent45.json'),
            str(OUT / 'v135_lifecycle_contract_latest_per_symbol.json'),
        ],
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    lines = [
        '# V135 Lifecycle Shadow Field Export', '',
        f"Decision: `{summary['decision']}`。只导出 shadow lifecycle/display contract，不接生产。", '',
        '## 1. Contract rules', '',
        '- `WATCH_AT_RECLAIM_CLOSE` -> display/watch metadata only.',
        '- `FAILED_RECLAIM_1/3` -> `CANCEL` / downgrade metadata only.',
        '- `KEEP_WATCH` -> takeover quality known, but `v135_tradable=false`.',
        '- Export explicitly sets `v135_failed_reclaim_is_buy_signal=false` for every row.',
        '- Outcome fields are not exported into display contracts.', '',
        '## 2. Status counts', '```json', json.dumps({'all': status_counts, 'latest_per_symbol': latest_status_counts}, ensure_ascii=False, indent=2), '```', '',
        '## 3. Evaluation by lifecycle status (diagnostic only)',
        '|status|n|wr|avg|loss_rate|hard_exit_rate|recent_n|recent_wr|',
        '|---|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for status, m in status_metrics.items():
        lines.append(f"|{status}|{m['n']}|{m['wr']}|{m['avg']}|{m['loss_rate']}|{m['hard_exit_rate']}|{m['recent_n']}|{m['recent_wr']}|")
    lines += [
        '', '## 4. Coverage', '```json', json.dumps(summary['coverage'], ensure_ascii=False, indent=2), '```', '',
        '## 5. Validation', '```json', json.dumps(validation, ensure_ascii=False, indent=2), '```', '',
        '## 6. Production snapshot', '```json', json.dumps(production_snapshot, ensure_ascii=False, indent=2), '```', '',
        '## 7. Conclusion', '',
        'V135 closes the shadow field-contract layer: lifecycle data can be propagated as display/watch/cancel metadata without creating any BUY/tradable instruction. This still does not solve entry edge. The next non-production step should be UI/API dry-run mapping only, or a separate no-lag entry model; do not promote failed-reclaim or KEEP_WATCH into buy signals.',
    ]
    (OUT / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({
        'decision': summary['decision'],
        'out': str(OUT),
        'validation': validation,
        'status_counts_all': status_counts,
        'production_snapshot_8890': production_snapshot,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
