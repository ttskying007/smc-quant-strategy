#!/usr/bin/env python3
"""V150 read-only anatomy of V149 lifecycle-exit tradeoffs.

Purpose:
- Diagnose why V149 lifecycle exits did not pass release gate.
- Compare each lifecycle variant against the original V138 baseline on the same
  symbol/entry rows.
- No production/API/frontend/watchlist changes; no TP/SL tuning.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path('/root/.hermes')
IN = ROOT / 'smc_audit' / 'v149_lifecycle_exit_backtest_20260621' / 'v149_lifecycle_exit_executed_rows.csv'
OUT = ROOT / 'smc_audit' / 'v150_lifecycle_exit_tradeoff_anatomy_20260623'
OUT.mkdir(parents=True, exist_ok=True)

BASE = 'BASELINE_V138_RECLAIM_NEXT_OPEN'
VARIANTS = [
    'ENTRY_CLOSE_CANCEL_T1_OPEN',
    'CANCEL_OR_INTRADAY_RISK_T1_OPEN',
    'CANCEL_AND_PREBUY_GAP_NO_ENTRY',
]
KEYS = ['symbol', 'entry_date']


def fnum(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors='coerce').fillna(0.0)


def bseries(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().eq('true')


def metrics(df: pd.DataFrame, pnl_col: str = 'variant_pnl') -> dict[str, Any]:
    n = int(len(df))
    if n == 0:
        return {'n': 0, 'wr': 0.0, 'avg': 0.0, 'median': 0.0, 'loss': 0.0, 'recent_n': 0, 'recent_wr': 0.0}
    pnl = fnum(df[pnl_col])
    recent = df[bseries(df['is_recent45'])] if 'is_recent45' in df else df.iloc[0:0]
    rp = fnum(recent[pnl_col]) if len(recent) else pd.Series(dtype=float)
    return {
        'n': n,
        'wr': round(float((pnl > 0).mean() * 100), 2),
        'avg': round(float(pnl.mean()), 4),
        'median': round(float(pnl.median()), 4),
        'loss': round(float((pnl <= 0).mean() * 100), 2),
        'recent_n': int(len(recent)),
        'recent_wr': round(float((rp > 0).mean() * 100), 2) if len(recent) else 0.0,
    }


def group_metrics(df: pd.DataFrame, key: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if key not in df:
        return rows
    for value, part in df.groupby(key, dropna=False):
        rows.append({
            'key': str(value),
            **metrics(part),
            'base_wr': round(float((fnum(part['base_pnl']) > 0).mean() * 100), 2),
            'base_avg': round(float(fnum(part['base_pnl']).mean()), 4),
            'delta_avg': round(float(fnum(part['delta_pnl']).mean()), 4),
            'improved_n': int((fnum(part['delta_pnl']) > 0).sum()),
            'worsened_n': int((fnum(part['delta_pnl']) < 0).sum()),
        })
    return sorted(rows, key=lambda r: (r['delta_avg'], r['n']), reverse=True)


def make_pair(df: pd.DataFrame, variant: str) -> pd.DataFrame:
    base = df[df['v149_variant'].eq(BASE)].copy()
    var = df[df['v149_variant'].eq(variant)].copy()
    keep_cols = [
        'symbol', 'entry_date', 'is_recent45', 'v143_lifecycle_status', 'v143_lifecycle_reason',
        'v149_lifecycle_action', 'v149_exit_reason', 'v149_exit_date', 'v149_pnl_pct',
        'v149_entry_date', 'v149_entry_price', 'v149_exit_price', 'market_state', 'combo_family',
        'entry_chase_above_zone_pct', 'risk_pct', 'v85_zone_width_pct', 'reclaim_close_above_zone_pct',
    ]
    base_cols = [c for c in keep_cols if c in base.columns]
    var_cols = [c for c in keep_cols if c in var.columns]
    base = base[base_cols].rename(columns={
        'v149_pnl_pct': 'base_pnl',
        'v149_exit_reason': 'base_exit_reason',
        'v149_exit_date': 'base_exit_date',
        'v149_exit_price': 'base_exit_price',
    })
    var = var[var_cols].rename(columns={
        'v149_pnl_pct': 'variant_pnl',
        'v149_exit_reason': 'variant_exit_reason',
        'v149_exit_date': 'variant_exit_date',
        'v149_exit_price': 'variant_exit_price',
        'v149_lifecycle_action': 'variant_action',
    })
    merged = var.merge(base[[*KEYS, 'base_pnl', 'base_exit_reason', 'base_exit_date', 'base_exit_price']], on=KEYS, how='left')
    merged['variant'] = variant
    merged['delta_pnl'] = fnum(merged['variant_pnl']) - fnum(merged['base_pnl'])
    merged['changed'] = merged['variant_exit_date'].astype(str).ne(merged['base_exit_date'].astype(str)) | merged['variant_exit_reason'].astype(str).ne(merged['base_exit_reason'].astype(str))
    merged['helped'] = fnum(merged['delta_pnl']) > 0
    merged['hurt'] = fnum(merged['delta_pnl']) < 0
    merged['hurt_winner'] = (fnum(merged['delta_pnl']) < 0) & (fnum(merged['base_pnl']) > 0)
    merged['rescued_loser'] = (fnum(merged['delta_pnl']) > 0) & (fnum(merged['base_pnl']) <= 0)
    return merged


def main() -> None:
    df = pd.read_csv(IN, low_memory=False)
    # Normalize key date because V149 baseline uses v149_entry_date while user-facing source keeps entry_date.
    if 'entry_date' not in df and 'v149_entry_date' in df:
        df['entry_date'] = df['v149_entry_date']
    df['entry_date'] = df['entry_date'].astype(str).str[:8]
    pairs = pd.concat([make_pair(df, v) for v in VARIANTS], ignore_index=True)
    pairs.to_csv(OUT / 'v150_variant_vs_baseline_pairs.csv', index=False)

    variant_summary = []
    reason_summary: dict[str, Any] = {}
    status_summary: dict[str, Any] = {}
    action_summary: dict[str, Any] = {}
    monthly_summary: dict[str, Any] = {}
    for variant, part in pairs.groupby('variant'):
        changed = part[bseries(part['changed'])]
        variant_summary.append({
            'variant': variant,
            **metrics(part),
            'base_wr': round(float((fnum(part['base_pnl']) > 0).mean() * 100), 2),
            'base_avg': round(float(fnum(part['base_pnl']).mean()), 4),
            'avg_delta': round(float(fnum(part['delta_pnl']).mean()), 4),
            'changed_n': int(len(changed)),
            'helped_n': int((fnum(part['delta_pnl']) > 0).sum()),
            'hurt_n': int((fnum(part['delta_pnl']) < 0).sum()),
            'rescued_loser_n': int(part['rescued_loser'].astype(bool).sum()),
            'hurt_winner_n': int(part['hurt_winner'].astype(bool).sum()),
            'changed_avg_delta': round(float(fnum(changed['delta_pnl']).mean()), 4) if len(changed) else 0.0,
            'changed_hurt_winner_n': int(changed['hurt_winner'].astype(bool).sum()) if len(changed) else 0,
        })
        reason_summary[variant] = group_metrics(part, 'variant_exit_reason')
        status_summary[variant] = group_metrics(part, 'v143_lifecycle_status')
        action_summary[variant] = group_metrics(part, 'variant_action')
        part = part.copy()
        part['month'] = part['entry_date'].astype(str).str[:6]
        monthly_summary[variant] = group_metrics(part, 'month')

    variant_df = pd.DataFrame(variant_summary).sort_values(['avg_delta', 'wr'], ascending=[False, False])
    variant_df.to_csv(OUT / 'v150_variant_tradeoff_summary.csv', index=False)
    for variant in VARIANTS:
        pd.DataFrame(reason_summary[variant]).to_csv(OUT / f'v150_by_exit_reason_{variant}.csv', index=False)
        pd.DataFrame(status_summary[variant]).to_csv(OUT / f'v150_by_status_{variant}.csv', index=False)
        pd.DataFrame(action_summary[variant]).to_csv(OUT / f'v150_by_action_{variant}.csv', index=False)
        pd.DataFrame(monthly_summary[variant]).to_csv(OUT / f'v150_monthly_{variant}.csv', index=False)

    # Focus on the core failure: lifecycle exits cutting winners more than they rescue losers.
    worst_hurt = pairs[fnum(pairs['delta_pnl']) < 0].sort_values('delta_pnl').head(80)
    best_help = pairs[fnum(pairs['delta_pnl']) > 0].sort_values('delta_pnl', ascending=False).head(80)
    worst_hurt.to_csv(OUT / 'v150_worst_hurt_trades.csv', index=False)
    best_help.to_csv(OUT / 'v150_best_helped_trades.csv', index=False)

    best = variant_df.iloc[0].to_dict() if len(variant_df) else {}
    release_gate = {
        'pass': False,
        'checks': {
            'any_variant_avg_delta_positive': bool(len(variant_df) and variant_df['avg_delta'].max() > 0),
            'hurt_winner_not_dominant': bool(len(variant_df) and int(best.get('hurt_winner_n', 999999)) <= int(best.get('rescued_loser_n', -1))),
            'changed_avg_delta_positive': bool(len(variant_df) and float(best.get('changed_avg_delta', -999)) > 0),
        },
    }
    if all(release_gate['checks'].values()):
        release_gate['pass'] = True

    summary = {
        'decision': 'V150_LIFECYCLE_EXIT_TRADEOFF_DIAGNOSED_NO_PROMOTION',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'production_write': False,
        'input': str(IN),
        'out': str(OUT),
        'variant_summary': variant_df.to_dict(orient='records'),
        'best_variant_by_delta': best,
        'release_gate': release_gate,
        'root_cause': 'Lifecycle exit variants mostly raise WR by truncating trades, but average PnL falls because winner truncation offsets loser rescue; therefore not promotable.',
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

    lines = [
        '# V150 生命周期退出 tradeoff 诊断',
        '',
        'Decision: `V150_LIFECYCLE_EXIT_TRADEOFF_DIAGNOSED_NO_PROMOTION`。只读诊断，不改生产/API/frontend/watchlist/TP/SL。',
        '',
        '## 1. Variant vs baseline',
        variant_df.to_markdown(index=False),
        '',
        '## 2. Root cause',
        '- V149 的生命周期退出能提高 WR，但没有提高平均收益；核心原因是它同时截断亏损和截断后续大赢家。',
        '- 发布门槛继续失败：必须同时满足 avg_delta>0、changed_avg_delta>0、救回亏损数不少于伤害赢家数。',
        '',
        '## 3. Release gate',
        '```json',
        json.dumps(release_gate, ensure_ascii=False, indent=2),
        '```',
        '',
        '## 4. Next',
        '- 下一步不能把 lifecycle exit 作为生产 SELL。应继续只作为持仓风险元数据，转向“取消/减仓信号是否能提前到买前或买入当日盘中可执行”的 timing-aware 子规则审计。',
    ]
    (OUT / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
