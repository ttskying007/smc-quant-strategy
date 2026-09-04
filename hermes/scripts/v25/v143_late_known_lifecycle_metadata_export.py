#!/usr/bin/env python3
"""V143 read-only late-known lifecycle metadata export.

Continues V141/V142: buy-time filters did not improve enough, so export the
late-known V140 signals only as watch/cancel lifecycle metadata. No production,
API, frontend, watchlist, or TP/SL changes.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path('/root/.hermes')
IN = ROOT / 'smc_audit' / 'v141_v140_lead_timing_availability_20260621' / 'v141_timing_availability_rows.csv'
OUT = ROOT / 'smc_audit' / 'v143_late_known_lifecycle_metadata_export_20260621'
OUT.mkdir(parents=True, exist_ok=True)

OUTCOME_FIELDS = {
    'pnl_pct','exit_reason','exit_date','exit_idx','exit_price','hold_bars',
    'v138_pnl_pct','v138_exit_reason','v138_exit_idx','v138_exit_price',
    'v138_hold_bars','v138_mfe_pct','v138_mae_pct','mfe_5_pct','mae_5_pct'
}


def bool_s(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().eq('true')


def num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors='coerce')


def metrics(df: pd.DataFrame) -> dict[str, Any]:
    n = int(len(df))
    if n == 0:
        return {'n': 0, 'wr': 0.0, 'avg': 0.0, 'loss': 0.0, 'hard_exit': 0.0, 'recent_n': 0, 'recent_wr': 0.0}
    pnl = num(df['v138_pnl_pct'])
    hard = df['v138_exit_reason'].astype(str).isin(['ZONE_CLOSE_DEAD_T1', 'STRUCTURE_SL_T1'])
    recent = df[bool_s(df['is_recent45'])] if 'is_recent45' in df else df.iloc[0:0]
    rp = num(recent['v138_pnl_pct']) if len(recent) else pd.Series(dtype=float)
    return {
        'n': n,
        'wr': round(float((pnl > 0).mean() * 100), 2),
        'avg': round(float(pnl.mean()), 4),
        'loss': round(float((pnl <= 0).mean() * 100), 2),
        'hard_exit': round(float(hard.mean() * 100), 2),
        'recent_n': int(len(recent)),
        'recent_wr': round(float((rp > 0).mean() * 100), 2) if len(recent) else 0.0,
    }


def production_probe() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for ep in ['/api/summary', '/api/picks/contract']:
        try:
            with urllib.request.urlopen('http://127.0.0.1:8890' + ep, timeout=8) as r:
                out[ep] = json.loads(r.read().decode('utf-8'))
        except Exception as e:
            out[ep] = {'error': repr(e)}
    return out


def lifecycle_status(row: pd.Series) -> str:
    timing = str(row.get('v141_earliest_lead_timing', 'NONE'))
    no_ft = str(row.get('v140_no_entry_follow_through_le_1pct', '')).lower() == 'true'
    retest = str(row.get('v140_entry_day_retests_zone_high', '')).lower() == 'true'
    close_fail = str(row.get('v140_entry_day_closes_below_zone_high', '')).lower() == 'true'
    early_zone_fail = str(row.get('v140_early_zone_fail_0_2', '')).lower() == 'true'
    if timing == 'PRE_BUY_AT_NEXT_OPEN':
        return 'PRE_BUY_GAP_NOTE_ONLY'
    if close_fail or no_ft or early_zone_fail:
        return 'CANCEL_AFTER_ENTRY_DAY_CLOSE'
    if retest or timing == 'ENTRY_DAY_AFTER_OPEN':
        return 'INTRADAY_RISK_NOTE_ONLY'
    return 'KEEP_WATCH_NO_LATE_FAILURE'


def reason(row: pd.Series) -> str:
    reasons = []
    if str(row.get('v140_no_entry_follow_through_le_1pct', '')).lower() == 'true':
        reasons.append('NO_ENTRY_FOLLOW_THROUGH_LE_1PCT')
    if str(row.get('v140_entry_day_closes_below_zone_high', '')).lower() == 'true':
        reasons.append('ENTRY_DAY_CLOSES_BELOW_ZONE_HIGH')
    if str(row.get('v140_early_zone_fail_0_2', '')).lower() == 'true':
        reasons.append('EARLY_ZONE_FAIL_0_2')
    if str(row.get('v140_entry_day_retests_zone_high', '')).lower() == 'true':
        reasons.append('ENTRY_DAY_RETESTS_ZONE_HIGH')
    if str(row.get('v141_earliest_lead_timing', '')) == 'PRE_BUY_AT_NEXT_OPEN':
        reasons.append('PRE_BUY_ENTRY_GAP_ONLY')
    return '|'.join(reasons) if reasons else 'NONE'


def main() -> None:
    df = pd.read_csv(IN, low_memory=False)
    df = df[bool_s(df['valid_backtest'])].copy() if 'valid_backtest' in df else df.copy()
    df['v143_lifecycle_status'] = df.apply(lifecycle_status, axis=1)
    df['v143_lifecycle_reason'] = df.apply(reason, axis=1)
    df['v143_tradable'] = False
    df['v143_buy_signal'] = False
    df['v143_failed_or_late_signal_is_buy_signal'] = False
    df['v143_action'] = df['v143_lifecycle_status'].map({
        'CANCEL_AFTER_ENTRY_DAY_CLOSE': 'WATCH_CANCEL_OR_NEXT_CYCLE_DOWNGRADE_ONLY',
        'INTRADAY_RISK_NOTE_ONLY': 'RISK_NOTE_ONLY_NO_ORIGINAL_BUY_CANCEL',
        'PRE_BUY_GAP_NOTE_ONLY': 'PRE_BUY_NOTE_ONLY_NO_FILTER_PROMOTION',
        'KEEP_WATCH_NO_LATE_FAILURE': 'KEEP_WATCH_METADATA_ONLY',
    }).fillna('WATCH_METADATA_ONLY')

    export_cols = [c for c in [
        'symbol','entry_date','pick_date','join_date','event_date','poi_source','combo_family','market_state',
        'zone_low','zone_high','entry_price','reclaim_close','reclaim_idx','entry_idx','is_recent45',
        'v140_entry_above_zone_high_pct','v140_entry_above_reclaim_close_pct',
        'v140_entry_day_retests_zone_high','v140_entry_day_closes_below_zone_high',
        'v140_no_entry_follow_through_le_1pct','v140_early_zone_fail_0_2',
        'v141_earliest_lead_timing','v141_pre_buy_cancel_available',
        'v141_intraday_cancel_only','v141_close_or_later_only',
        'v143_lifecycle_status','v143_lifecycle_reason','v143_action',
        'v143_tradable','v143_buy_signal','v143_failed_or_late_signal_is_buy_signal'
    ] if c in df.columns]
    export = df[export_cols].copy()
    leak = sorted(set(export.columns) & OUTCOME_FIELDS)
    export.to_json(OUT / 'v143_lifecycle_metadata_all.json', orient='records', force_ascii=False, indent=2)
    export[bool_s(export['is_recent45'])].to_json(OUT / 'v143_lifecycle_metadata_recent45.json', orient='records', force_ascii=False, indent=2)
    sort_cols = [c for c in ['symbol','entry_date','v143_lifecycle_status'] if c in export.columns]
    latest = export.sort_values(sort_cols).drop_duplicates(['symbol','poi_source'], keep='last')
    latest.to_json(OUT / 'v143_lifecycle_metadata_latest_per_symbol.json', orient='records', force_ascii=False, indent=2)

    status_rows = []
    for status, part in df.groupby('v143_lifecycle_status', dropna=False):
        status_rows.append({'status': status, **metrics(part)})
    status_df = pd.DataFrame(status_rows).sort_values('n', ascending=False)
    status_df.to_csv(OUT / 'v143_status_metrics.csv', index=False)

    prod = production_probe()
    summary = {
        'decision': 'V143_LATE_KNOWN_LIFECYCLE_METADATA_EXPORT_DONE_NO_PRODUCTION_CHANGE',
        'production_write': False,
        'input': str(IN),
        'out': str(OUT),
        'baseline': metrics(df),
        'status_metrics': status_df.to_dict(orient='records'),
        'export_rows': int(len(export)),
        'recent45_export_rows': int(bool_s(export['is_recent45']).sum()),
        'latest_per_symbol_rows': int(len(latest)),
        'latest_duplicate_symbol_poi': int(latest.duplicated(['symbol','poi_source']).sum()),
        'outcome_field_leaks': leak,
        'tradable_true_count': int(export['v143_tradable'].astype(bool).sum()),
        'buy_signal_true_count': int(export['v143_buy_signal'].astype(bool).sum()),
        't1_violation_count': int(bool_s(df['v138_t1_violation']).sum()) if 'v138_t1_violation' in df else -1,
        'production_probe': {
            'summary_engine': prod.get('/api/summary', {}).get('engine'),
            'summary_total_trades': prod.get('/api/summary', {}).get('total_trades'),
            'summary_win_rate': prod.get('/api/summary', {}).get('win_rate'),
            'tradable_active_pick_count': prod.get('/api/picks/contract', {}).get('tradable_active_pick_count'),
            'watch_only_count': prod.get('/api/picks/contract', {}).get('watch_only_count'),
            'raw_pick_file_count': prod.get('/api/picks/contract', {}).get('raw_pick_file_count'),
        },
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    md = []
    md.append('# V143 late-known lifecycle metadata export（只读）')
    md.append('')
    md.append(f"Decision: `{summary['decision']}`。只写 `{OUT}`；未改生产/API/frontend/watchlist/TP/SL。")
    md.append('')
    md.append('## 1. Baseline')
    md.append(pd.DataFrame([summary['baseline']]).to_markdown(index=False))
    md.append('')
    md.append('## 2. Lifecycle status')
    md.append(status_df.to_markdown(index=False))
    md.append('')
    md.append('## 3. Export contract validation')
    md.append(f"- export all/recent/latest: `{summary['export_rows']}` / `{summary['recent45_export_rows']}` / `{summary['latest_per_symbol_rows']}`")
    md.append(f"- duplicate latest symbol+poi: `{summary['latest_duplicate_symbol_poi']}`")
    md.append(f"- outcome field leaks: `{len(leak)}` {leak}")
    md.append(f"- tradable true / buy signal true: `{summary['tradable_true_count']}` / `{summary['buy_signal_true_count']}`")
    md.append(f"- T+1 violation: `{summary['t1_violation_count']}`")
    md.append(f"- production: `{summary['production_probe']}`")
    md.append('')
    md.append('## 4. Conclusion')
    md.append('V140/V141 的 close/intraday 才知道信号只能作为 watch/cancel/next-cycle downgrade 元数据；不作为原始买入过滤器，也不作为 BUY。')
    (OUT / 'report.md').write_text('\n'.join(md), encoding='utf-8')


if __name__ == '__main__':
    main()
