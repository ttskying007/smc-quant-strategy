#!/usr/bin/env python3
"""V149 lifecycle-aware exit backtest for V141/V143 shadow metadata.

Purpose:
- Execute the next iteration after V140-V148: test whether late-known lifecycle
  metadata improves executable position management.
- This is a full read-only backtest over the V141 no-MIXED RECLAIM universe.
- No production/API/frontend/watchlist/morning-push changes.

Key constraint:
- A-share T+1 is enforced: no same-day exit. Entry-day close signals can only
  trigger next-trading-day open exits.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path('/root/.hermes')
IN = ROOT / 'smc_audit' / 'v141_v140_lead_timing_availability_20260621' / 'v141_timing_availability_rows.csv'
OUT = ROOT / 'smc_audit' / 'v149_lifecycle_exit_backtest_20260621'
KLINE_DIR = ROOT / 'kline_cache'
OUT.mkdir(parents=True, exist_ok=True)


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return default
        return float(v)
    except Exception:
        return default


def bseries(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().eq('true')


def pct(a: float, b: float) -> float:
    return 0.0 if a <= 0 or b <= 0 else (a / b - 1.0) * 100.0


def date_key(v: Any) -> str:
    return str(v or '').replace('-', '')[:8]


def bar_date(bar: dict[str, Any]) -> str:
    return date_key(bar.get('t') or bar.get('date') or bar.get('day') or bar.get('time'))


def load_bars(symbol: str) -> list[dict[str, Any]]:
    stem = symbol.replace('.', '_')
    for suffix in ('daily_750', 'daily_300'):
        p = KLINE_DIR / f'{stem}_{suffix}.json'
        if p.exists():
            data = json.loads(p.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                for key in ('data', 'klines', 'bars'):
                    if isinstance(data.get(key), list):
                        data = data[key]
                        break
            return data if isinstance(data, list) else []
    return []


def bar_val(b: dict[str, Any], key: str) -> float:
    return fnum(b.get(key))


def metrics(df: pd.DataFrame, pnl_col: str = 'v149_pnl_pct') -> dict[str, Any]:
    n = int(len(df))
    if n == 0:
        return {'n': 0, 'wr': 0.0, 'avg': 0.0, 'median': 0.0, 'loss': 0.0, 'hard_exit': 0.0, 'recent_n': 0, 'recent_wr': 0.0, 't1': 0}
    pnl = pd.to_numeric(df[pnl_col], errors='coerce').fillna(0.0)
    recent = df[bseries(df['is_recent45'])] if 'is_recent45' in df else df.iloc[0:0]
    rp = pd.to_numeric(recent[pnl_col], errors='coerce').fillna(0.0) if len(recent) else pd.Series(dtype=float)
    hard = df['v149_exit_reason'].astype(str).isin(['ZONE_CLOSE_DEAD_T1', 'STRUCTURE_SL_T1', 'LIFECYCLE_CANCEL_NEXT_OPEN'])
    return {
        'n': n,
        'wr': round(float((pnl > 0).mean() * 100), 2),
        'avg': round(float(pnl.mean()), 4),
        'median': round(float(pnl.median()), 4),
        'loss': round(float((pnl <= 0).mean() * 100), 2),
        'hard_exit': round(float(hard.mean() * 100), 2),
        'recent_n': int(len(recent)),
        'recent_wr': round(float((rp > 0).mean() * 100), 2) if len(recent) else 0.0,
        't1': int(df['v149_t1_violation'].astype(bool).sum()) if 'v149_t1_violation' in df else -1,
    }


def original_baseline_row(row: pd.Series) -> dict[str, Any]:
    status, reason = lifecycle_status(row)
    out = row.to_dict()
    out.update({
        'v149_variant': 'BASELINE_V138_RECLAIM_NEXT_OPEN',
        'v149_entry_idx': int(fnum(row.get('v138_entry_idx'), -1)),
        'v149_entry_date': date_key(row.get('v138_entry_date')),
        'v149_entry_price': fnum(row.get('v138_entry_price')),
        'v149_exit_idx': int(fnum(row.get('v138_exit_idx'), -1)),
        'v149_exit_date': date_key(row.get('v138_exit_date')),
        'v149_exit_price': fnum(row.get('v138_exit_price')),
        'v149_exit_reason': str(row.get('v138_exit_reason')),
        'v149_pnl_pct': fnum(row.get('v138_pnl_pct')),
        'v149_t1_violation': date_key(row.get('v138_entry_date')) == date_key(row.get('v138_exit_date')),
        'v149_lifecycle_action': 'BASELINE',
        'v143_lifecycle_status': status,
        'v143_lifecycle_reason': reason,
    })
    return out


def lifecycle_status(row: pd.Series) -> tuple[str, str]:
    """Derive the same lifecycle metadata as V143 from V140/V141 fields."""
    timing = str(row.get('v141_earliest_lead_timing', 'NONE'))
    no_ft = str(row.get('v140_no_entry_follow_through_le_1pct', '')).lower() == 'true'
    retest = str(row.get('v140_entry_day_retests_zone_high', '')).lower() == 'true'
    close_fail = str(row.get('v140_entry_day_closes_below_zone_high', '')).lower() == 'true'
    early_zone_fail = str(row.get('v140_early_zone_fail_0_2', '')).lower() == 'true'
    if timing == 'PRE_BUY_AT_NEXT_OPEN':
        status = 'PRE_BUY_GAP_NOTE_ONLY'
    elif close_fail or no_ft or early_zone_fail:
        status = 'CANCEL_AFTER_ENTRY_DAY_CLOSE'
    elif retest or timing == 'ENTRY_DAY_AFTER_OPEN':
        status = 'INTRADAY_RISK_NOTE_ONLY'
    else:
        status = 'KEEP_WATCH_NO_LATE_FAILURE'
    reasons: list[str] = []
    if no_ft:
        reasons.append('NO_ENTRY_FOLLOW_THROUGH_LE_1PCT')
    if close_fail:
        reasons.append('ENTRY_DAY_CLOSES_BELOW_ZONE_HIGH')
    if early_zone_fail:
        reasons.append('EARLY_ZONE_FAIL_0_2')
    if retest:
        reasons.append('ENTRY_DAY_RETESTS_ZONE_HIGH')
    if timing == 'PRE_BUY_AT_NEXT_OPEN':
        reasons.append('PRE_BUY_ENTRY_GAP_ONLY')
    return status, ('|'.join(reasons) if reasons else 'NONE')


def lifecycle_exit_row(row: pd.Series, variant: str) -> dict[str, Any]:
    out = original_baseline_row(row)
    out['v149_variant'] = variant
    symbol = str(row.get('symbol'))
    bars = load_bars(symbol)
    entry_idx = int(fnum(row.get('v138_entry_idx'), -1))
    baseline_exit_idx = int(fnum(row.get('v138_exit_idx'), -1))
    entry_price = fnum(row.get('v138_entry_price'))
    status, reason = lifecycle_status(row)
    out['v143_lifecycle_status'] = status
    out['v143_lifecycle_reason'] = reason
    if not bars or entry_idx < 0 or entry_idx >= len(bars):
        out['v149_missing_kline'] = True
        return out

    cancel = False
    action = 'KEEP_BASELINE_EXIT'
    cancel_idx = -1
    if variant == 'ENTRY_CLOSE_CANCEL_T1_OPEN':
        cancel = status == 'CANCEL_AFTER_ENTRY_DAY_CLOSE'
        cancel_idx = entry_idx + 1
        action = 'ENTRY_CLOSE_CANCEL_SELL_NEXT_OPEN' if cancel else action
    elif variant == 'CANCEL_OR_INTRADAY_RISK_T1_OPEN':
        cancel = status in {'CANCEL_AFTER_ENTRY_DAY_CLOSE', 'INTRADAY_RISK_NOTE_ONLY'}
        cancel_idx = entry_idx + 1
        action = 'CANCEL_OR_RISK_SELL_NEXT_OPEN' if cancel else action
    elif variant == 'CANCEL_AND_PREBUY_GAP_NO_ENTRY':
        # This variant combines a no-lag pre-buy gap skip with entry-close cancel.
        # It is included to verify whether the already-rejected V142 pre-buy signal
        # becomes useful when combined with lifecycle exits.
        if status == 'PRE_BUY_GAP_NOTE_ONLY':
            out['v149_skip_trade'] = True
            out['v149_lifecycle_action'] = 'SKIP_PRE_BUY_GAP_NOTE_ONLY'
            return out
        cancel = status == 'CANCEL_AFTER_ENTRY_DAY_CLOSE'
        cancel_idx = entry_idx + 1
        action = 'ENTRY_CLOSE_CANCEL_SELL_NEXT_OPEN' if cancel else action
    else:
        raise ValueError(variant)

    if cancel and 0 <= cancel_idx < len(bars) and (baseline_exit_idx < 0 or cancel_idx < baseline_exit_idx):
        exit_price = bar_val(bars[cancel_idx], 'o')
        out.update({
            'v149_exit_idx': cancel_idx,
            'v149_exit_date': bar_date(bars[cancel_idx]),
            'v149_exit_price': round(exit_price, 6),
            'v149_exit_reason': 'LIFECYCLE_CANCEL_NEXT_OPEN',
            'v149_pnl_pct': round(pct(exit_price, entry_price), 4),
            'v149_lifecycle_action': action,
            'v149_cancel_source_status': status,
            'v149_cancel_source_reason': reason,
        })
    else:
        out['v149_lifecycle_action'] = action
    out['v149_t1_violation'] = out['v149_entry_date'] == out['v149_exit_date']
    out['v149_missing_kline'] = False
    return out


def by_group(df: pd.DataFrame, key: str) -> dict[str, dict[str, Any]]:
    return {str(k): metrics(v) for k, v in df.groupby(key, dropna=False)}


def monthly(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    x['month'] = x['v149_entry_date'].astype(str).str[:6]
    rows = []
    for m, part in x.groupby('month', dropna=False):
        rows.append({'month': m, **metrics(part)})
    return pd.DataFrame(rows).sort_values('month')


def main() -> None:
    df = pd.read_csv(IN, low_memory=False)
    if 'valid_backtest' in df:
        df = df[bseries(df['valid_backtest'])].copy()
    # V141 input is already the full no-MIXED RECLAIM universe (273 rows), but
    # keep the invariant explicit for audit repeatability.
    rows = [original_baseline_row(r) for _, r in df.iterrows()]
    variants = ['ENTRY_CLOSE_CANCEL_T1_OPEN', 'CANCEL_OR_INTRADAY_RISK_T1_OPEN', 'CANCEL_AND_PREBUY_GAP_NO_ENTRY']
    for variant in variants:
        rows.extend(lifecycle_exit_row(r, variant) for _, r in df.iterrows())
    all_df = pd.DataFrame(rows)
    skip_series = all_df['v149_skip_trade'] if 'v149_skip_trade' in all_df.columns else pd.Series(False, index=all_df.index)
    executed_df = all_df[~skip_series.fillna(False).astype(bool)].copy()

    all_df.to_csv(OUT / 'v149_lifecycle_exit_all_rows.csv', index=False)
    executed_df.to_csv(OUT / 'v149_lifecycle_exit_executed_rows.csv', index=False)

    variant_rows = []
    for variant, part in executed_df.groupby('v149_variant', dropna=False):
        variant_rows.append({'variant': variant, **metrics(part)})
    variant_df = pd.DataFrame(variant_rows).sort_values(['wr', 'avg'], ascending=[False, False])
    variant_df.to_csv(OUT / 'v149_variant_metrics.csv', index=False)

    for variant, part in executed_df.groupby('v149_variant', dropna=False):
        monthly(part).to_csv(OUT / f'v149_monthly_{variant}.csv', index=False)

    baseline = executed_df[executed_df['v149_variant'].eq('BASELINE_V138_RECLAIM_NEXT_OPEN')]
    best_name = str(variant_df.iloc[0]['variant']) if len(variant_df) else ''
    best = executed_df[executed_df['v149_variant'].eq(best_name)] if best_name else executed_df.iloc[0:0]
    changed = best[best['v149_lifecycle_action'].astype(str).ne('KEEP_BASELINE_EXIT') & best['v149_lifecycle_action'].astype(str).ne('BASELINE')]
    changed.to_csv(OUT / 'v149_best_changed_trades.csv', index=False)

    status_summary = {}
    if len(best):
        status_summary = by_group(best, 'v143_lifecycle_status') if 'v143_lifecycle_status' in best else {}
    exit_summary = by_group(best, 'v149_exit_reason') if len(best) else {}

    base_m = metrics(baseline)
    best_m = metrics(best)
    release_pass = bool(
        best_name != 'BASELINE_V138_RECLAIM_NEXT_OPEN'
        and best_m['n'] >= 120
        and best_m['wr'] >= base_m['wr'] + 2.0
        and best_m['avg'] >= base_m['avg'] + 0.25
        and best_m['hard_exit'] <= base_m['hard_exit'] - 2.0
        and best_m['t1'] == 0
    )
    summary = {
        'decision': 'V149_LIFECYCLE_EXIT_PROMOTABLE_SHADOW' if release_pass else 'V149_LIFECYCLE_EXIT_RESEARCH_ONLY_NOT_PROMOTED',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'production_write': False,
        'input': str(IN),
        'out': str(OUT),
        'baseline': base_m,
        'variant_metrics': variant_df.to_dict(orient='records'),
        'best_variant': best_name,
        'best_metrics': best_m,
        'best_changed_trades': int(len(changed)),
        'best_status_summary': status_summary,
        'best_exit_summary': exit_summary,
        'release_gate': {
            'pass': release_pass,
            'checks': {
                'not_baseline': best_name != 'BASELINE_V138_RECLAIM_NEXT_OPEN',
                'n_ge_120': best_m['n'] >= 120,
                'wr_improve_ge_2pp': best_m['wr'] >= base_m['wr'] + 2.0,
                'avg_improve_ge_0_25pp': best_m['avg'] >= base_m['avg'] + 0.25,
                'hard_exit_reduce_ge_2pp': best_m['hard_exit'] <= base_m['hard_exit'] - 2.0,
                't1_zero': best_m['t1'] == 0,
            },
        },
        't1_violation_total': int(executed_df['v149_t1_violation'].astype(bool).sum()),
        'missing_kline_total': int(executed_df.get('v149_missing_kline', False).fillna(False).astype(bool).sum()),
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

    lines = [
        '# V149 生命周期退出全量回测',
        '',
        f"Decision: `{summary['decision']}`。只读回测，不改生产/API/frontend/watchlist/TP/SL。",
        '',
        '## 1. Variant metrics',
        variant_df.to_markdown(index=False),
        '',
        '## 2. Release gate',
        '```json',
        json.dumps(summary['release_gate'], ensure_ascii=False, indent=2),
        '```',
        '',
        '## 3. Best variant exit/status summary',
        '### Exit reason',
        pd.DataFrame([{'key': k, **v} for k, v in exit_summary.items()]).to_markdown(index=False) if exit_summary else '无',
        '',
        '### Lifecycle status',
        pd.DataFrame([{'key': k, **v} for k, v in status_summary.items()]).to_markdown(index=False) if status_summary else '无',
        '',
        '## 4. 结论',
        '- Entry-day close / intraday lifecycle 信号严格按 T+1 顺延到下一交易日开盘执行；同日卖出违规为 0。',
        '- 若 release gate 未通过，生命周期信号继续保持 watch/cancel 元数据，不晋级 BUY/SELL 生产逻辑。',
    ]
    (OUT / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
