#!/usr/bin/env python3
"""V159: V158 stability and threshold-fragility audit.

Read-only research only. This script does not write production/frontend/watchlist.
It validates whether the V158 non-leak lifecycle candidate is stable enough to
remain a promotion candidate by checking monthly distribution, rolling windows,
remaining loss anatomy, and threshold sensitivity around the selected rule.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path('/root/.hermes')
V158_DIR = ROOT / 'smc_audit' / 'v158_non_leak_smc_lifecycle_rebuild_20260622'
SRC = V158_DIR / 'v158_chosen_rows.csv'
BASELINE_SRC = ROOT / 'smc_audit' / 'v154_cancel_addback_no_micro_20260622' / 'v154_chosen_rows.csv'
OUT = ROOT / 'smc_audit' / 'v159_v158_stability_fragility_audit_20260622'
OUT.mkdir(parents=True, exist_ok=True)

RELEASE_WR = 82.0
RELEASE_AVG = 3.0
RELEASE_MIN_YEAR_N = 35
RELEASE_2024_WR = 78.0
MONTH_MIN_N = 3
MONTH_WR_FLOOR = 60.0
ROLLING_WINDOW = 30
ROLLING_WR_FLOOR = 70.0


def bool_s(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower().isin({'true', '1', 'yes'})


def num_s(s: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(s, errors='coerce').fillna(default)


def date_key(v: Any) -> str:
    return str(v or '').replace('-', '')[:8]


def add_time_cols(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out['entry_date_key'] = out['v154_entry_date'].map(date_key)
    out['entry_year'] = out['entry_date_key'].str[:4]
    out['entry_month'] = out['entry_date_key'].str[:6]
    return out


def metrics(df: pd.DataFrame, pnl_col: str = 'v154_pnl_pct') -> dict[str, Any]:
    n = int(len(df))
    if n == 0:
        return {'n': 0, 'wr': 0.0, 'avg': 0.0, 'median': 0.0, 'loss': 0.0, 'min_year_n': 0, 'year_counts': {}, 'year_wr': {}, 't1': 0}
    pnl = num_s(df[pnl_col])
    year_counts = {str(k): int(v) for k, v in df['entry_year'].astype(str).value_counts().sort_index().items()}
    year_wr = {}
    for y in sorted(year_counts):
        yp = pnl[df['entry_year'].astype(str).eq(y)]
        year_wr[y] = round(float((yp > 0).mean() * 100), 2) if len(yp) else 0.0
    t1_col = df.get('v154_t1_violation', pd.Series(False, index=df.index))
    return {
        'n': n,
        'wr': round(float((pnl > 0).mean() * 100), 2),
        'avg': round(float(pnl.mean()), 4),
        'median': round(float(pnl.median()), 4),
        'loss': round(float((pnl <= 0).mean() * 100), 2),
        'min_year_n': int(min(year_counts.values())) if year_counts else 0,
        'year_counts': year_counts,
        'year_wr': year_wr,
        't1': int(bool_s(t1_col).sum()),
    }


def release_pass(m: dict[str, Any]) -> bool:
    return bool(
        m['wr'] >= RELEASE_WR
        and m['avg'] >= RELEASE_AVG
        and m['min_year_n'] >= RELEASE_MIN_YEAR_N
        and float(m['year_wr'].get('2024', 0.0)) >= RELEASE_2024_WR
        and int(m.get('t1', 0)) == 0
    )


def group_metrics(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    rows = []
    for key, g in df.groupby(group_col, dropna=False):
        rows.append({group_col: key, **metrics(g)})
    return pd.DataFrame(rows).sort_values(group_col)


def rolling_metrics(df: pd.DataFrame, window: int = ROLLING_WINDOW) -> pd.DataFrame:
    ordered = df.sort_values(['entry_date_key', 'symbol']).reset_index(drop=True)
    rows = []
    for start in range(0, max(0, len(ordered) - window + 1)):
        g = ordered.iloc[start:start + window]
        m = metrics(g)
        rows.append({
            'start_rank': start + 1,
            'end_rank': start + window,
            'start_date': g['entry_date_key'].iloc[0],
            'end_date': g['entry_date_key'].iloc[-1],
            **m,
        })
    return pd.DataFrame(rows)


def loss_buckets(df: pd.DataFrame) -> pd.DataFrame:
    losses = df[num_s(df['v154_pnl_pct']) <= 0].copy()
    if losses.empty:
        return pd.DataFrame()
    chase = num_s(losses['entry_chase_above_zone_pct'])
    risk = num_s(losses['risk_pct'])
    body = num_s(losses['v132_reclaim_bull_body_pct'])
    reclaim_above = num_s(losses['reclaim_close_above_zone_pct'])
    mae = num_s(losses['v138_mae_pct'])
    mfe = num_s(losses['v138_mfe_pct'])
    losses['loss_bucket'] = 'OTHER_LOSS'
    losses.loc[risk.ge(7.0), 'loss_bucket'] = 'HIGH_RISK_GE_7'
    losses.loc[chase.ge(4.0), 'loss_bucket'] = 'ENTRY_CHASE_GE_4'
    losses.loc[body.ge(80.0), 'loss_bucket'] = 'RECLAIM_BODY_EXHAUSTION_GE_80'
    losses.loc[reclaim_above.lt(1.3), 'loss_bucket'] = 'WEAK_RECLAIM_ABOVE_LT_1_3'
    losses.loc[mfe.lt(1.0), 'loss_bucket'] = 'NO_FOLLOW_THROUGH_MFE_LT_1'
    losses.loc[mae.le(-4.0), 'loss_bucket'] = 'FAST_ADVERSE_MAE_LE_NEG4'
    rows = []
    for key, g in losses.groupby('loss_bucket'):
        rows.append({'loss_bucket': key, **metrics(g), 'symbols': ','.join(g['symbol'].astype(str).head(12))})
    return pd.DataFrame(rows).sort_values(['n', 'avg'], ascending=[False, True])


def threshold_sensitivity(base: pd.DataFrame) -> pd.DataFrame:
    strict3 = bool_s(base['v132_true_takeover_3_strict'])
    nonstrict = ~strict3
    chase = num_s(base['entry_chase_above_zone_pct'])
    body = num_s(base['v132_reclaim_bull_body_pct'])
    reclaim_above = num_s(base['reclaim_close_above_zone_pct'])
    risk = num_s(base['risk_pct'])
    pbg = base['v143_lifecycle_status'].astype(str).eq('PRE_BUY_GAP_NOTE_ONLY')

    rows = []
    for chase_max in [2.0, 2.5, 3.0, 3.5, 4.0, 5.0]:
        for body_max in [78.0, 82.0, 86.6, 88.0, 90.0, 95.0]:
            mask = (strict3 | chase.le(chase_max)) & ((~nonstrict) | body.le(body_max))
            for pbg_rule, pbg_mask in [
                ('NO_EXTRA_PBG_RULE', pd.Series(True, index=base.index)),
                ('PBG_RECLAIM_ABOVE_GE_1_3', (~pbg) | reclaim_above.ge(1.3)),
                ('RISK_LE_7_5', risk.le(7.5)),
            ]:
                g = base[mask & pbg_mask]
                m = metrics(g)
                rows.append({
                    'chase_max': chase_max,
                    'nonstrict_body_max': body_max,
                    'extra_rule': pbg_rule,
                    **m,
                    'release_pass': release_pass(m),
                })
    return pd.DataFrame(rows).sort_values(['release_pass', 'n', 'wr', 'avg'], ascending=[False, False, False, False])


def main() -> None:
    chosen = add_time_cols(pd.read_csv(SRC, low_memory=False))
    baseline = add_time_cols(pd.read_csv(BASELINE_SRC, low_memory=False))

    monthly = group_metrics(chosen, 'entry_month')
    monthly['bad_month_n_ge_3_wr_lt_60'] = monthly['n'].ge(MONTH_MIN_N) & monthly['wr'].lt(MONTH_WR_FLOOR)
    monthly['weak_month_n_ge_3_wr_lt_78'] = monthly['n'].ge(MONTH_MIN_N) & monthly['wr'].lt(RELEASE_2024_WR)
    monthly.to_csv(OUT / 'v159_monthly_metrics.csv', index=False)

    yearly = group_metrics(chosen, 'entry_year')
    yearly.to_csv(OUT / 'v159_yearly_metrics.csv', index=False)

    rolling = rolling_metrics(chosen)
    if not rolling.empty:
        rolling['rolling_bad_wr_lt_70'] = rolling['wr'].lt(ROLLING_WR_FLOOR)
    rolling.to_csv(OUT / 'v159_rolling_30_trade_metrics.csv', index=False)

    losses = chosen[num_s(chosen['v154_pnl_pct']) <= 0].copy().sort_values(['entry_date_key', 'symbol'])
    loss_cols = [c for c in [
        'symbol', 'v154_entry_date', 'v154_exit_date', 'v154_pnl_pct', 'v154_exit_reason',
        'v132_reclaim_class', 'v143_lifecycle_status', 'v141_earliest_lead_timing',
        'entry_chase_above_zone_pct', 'reclaim_close_pos', 'reclaim_close_above_zone_pct',
        'v132_reclaim_bull_body_pct', 'source_gap_atr', 'source_mid_body_atr', 'risk_pct',
        'v138_mae_pct', 'v138_mfe_pct', 'zone_low', 'zone_high', 'entry_price', 'v158_reason'
    ] if c in losses.columns]
    losses[loss_cols].to_csv(OUT / 'v159_remaining_loss_rows.csv', index=False)

    loss_bucket_df = loss_buckets(chosen)
    loss_bucket_df.to_csv(OUT / 'v159_loss_bucket_metrics.csv', index=False)

    sensitivity = threshold_sensitivity(baseline)
    sensitivity.to_csv(OUT / 'v159_threshold_sensitivity.csv', index=False)

    m_chosen = metrics(chosen)
    m_baseline = metrics(baseline)
    bad_months = monthly[monthly['bad_month_n_ge_3_wr_lt_60']].copy()
    weak_months = monthly[monthly['weak_month_n_ge_3_wr_lt_78']].copy()
    bad_roll = rolling[rolling.get('rolling_bad_wr_lt_70', pd.Series(False, index=rolling.index))].copy() if not rolling.empty else pd.DataFrame()
    robust = bool(
        release_pass(m_chosen)
        and bad_months.empty
        and len(bad_roll) == 0
    )
    decision = 'V159_V158_CANDIDATE_STABLE_ENOUGH_FOR_DRY_RUN_CONTRACT_NEXT' if robust else 'V159_V158_CANDIDATE_RESEARCH_ONLY_NEEDS_DRY_RUN_OR_RULE_HARDENING'

    summary = {
        'decision': decision,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'production_write': False,
        'source': str(SRC),
        'baseline_source': str(BASELINE_SRC),
        'out': str(OUT),
        'chosen_metrics': m_chosen,
        'baseline_metrics': m_baseline,
        'bad_month_count_n_ge_3_wr_lt_60': int(len(bad_months)),
        'weak_month_count_n_ge_3_wr_lt_78': int(len(weak_months)),
        'rolling_30_bad_count_wr_lt_70': int(len(bad_roll)),
        'worst_months_n_ge_3': monthly[monthly['n'].ge(MONTH_MIN_N)].sort_values(['wr', 'avg']).head(10).to_dict(orient='records'),
        'worst_rolling_30': rolling.sort_values(['wr', 'avg']).head(10).to_dict(orient='records') if not rolling.empty else [],
        'loss_buckets': loss_bucket_df.to_dict(orient='records'),
        'top_threshold_rules': sensitivity.head(20).to_dict(orient='records'),
        'interpretation': (
            'V159 checks V158 beyond aggregate yearly metrics. If monthly n>=3 months have WR<60 or rolling 30-trade windows have WR<70, '
            'the candidate remains research-only and next step should be dry-run scanner contract plus hardening around the residual weak bucket. '
            'No market breadth or post-entry zone-death selector is used.'
        ),
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

    report = [
        '# V159 V158 stability / fragility audit', '',
        f"Decision: `{decision}`。只读研究；未写生产/前端/watchlist。", '',
        '## 1. Baseline vs V158 chosen',
        pd.DataFrame([{'bucket': 'V154_BASELINE', **m_baseline}, {'bucket': 'V158_CHOSEN', **m_chosen}]).to_markdown(index=False), '',
        '## 2. Yearly metrics', yearly.to_markdown(index=False), '',
        '## 3. Worst months (n>=3)',
        monthly[monthly['n'].ge(MONTH_MIN_N)].sort_values(['wr', 'avg']).head(12).to_markdown(index=False), '',
        '## 4. Rolling 30-trade worst windows',
        (rolling.sort_values(['wr', 'avg']).head(12).to_markdown(index=False) if not rolling.empty else 'No rolling windows'), '',
        '## 5. Remaining loss buckets',
        (loss_bucket_df.to_markdown(index=False) if not loss_bucket_df.empty else 'No losses'), '',
        '## 6. Top threshold sensitivity rows', sensitivity.head(12).to_markdown(index=False), '',
        '## 7. Conclusion', summary['interpretation'],
    ]
    (OUT / 'report.md').write_text('\n'.join(report), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
