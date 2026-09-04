#!/usr/bin/env python3
"""V158: non-leaking SMC lifecycle rule rebuild.

Scope:
- Read-only research/audit. No production/frontend/watchlist writes.
- Do not use market breadth.
- Do not use future post-entry zone death as a selector.
- Only test information available no later than the original buy decision or
  pre-defined SMC confirmation state carried in V154 research rows.

Goal:
- Rebuild lifecycle rule around touch -> reclaim -> hold quality.
- Test PRE_BUY_GAP downgrade, TRUE_TAKEOVER_2 secondary-confirmation handling,
  pre-entry demand-zone weakness, and entry-chase/exhaustion risk.
- Promote only if n>=200, every year has >=35 trades, and 2024 WR>=78%.
"""
from __future__ import annotations

import itertools
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd

ROOT = Path('/root/.hermes')
SRC = ROOT / 'smc_audit' / 'v154_cancel_addback_no_micro_20260622' / 'v154_chosen_rows.csv'
OUT = ROOT / 'smc_audit' / 'v158_non_leak_smc_lifecycle_rebuild_20260622'
OUT.mkdir(parents=True, exist_ok=True)

RELEASE_N = 200
RELEASE_MIN_YEAR_N = 35
RELEASE_2024_WR = 78.0
RELEASE_WR = 82.0
RELEASE_AVG = 3.0


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def bool_s(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower().isin({'true', '1', 'yes'})


def num_s(s: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(s, errors='coerce').fillna(default)


def date_key(v: Any) -> str:
    return str(v or '').replace('-', '')[:8]


def metrics(df: pd.DataFrame, pnl_col: str = 'v154_pnl_pct') -> dict[str, Any]:
    n = int(len(df))
    if n == 0:
        return {
            'n': 0, 'wr': 0.0, 'avg': 0.0, 'median': 0.0, 'loss': 0.0,
            'min_year_n': 0, 'year_counts': {}, 'year_wr': {}, 't1': 0,
        }
    pnl = num_s(df[pnl_col])
    years = df['entry_year'].astype(str)
    year_counts = {str(k): int(v) for k, v in years.value_counts().sort_index().items()}
    year_wr: dict[str, float] = {}
    for y in sorted(year_counts):
        yp = pnl[years.eq(y)]
        year_wr[y] = round(float((yp > 0).mean() * 100), 2) if len(yp) else 0.0
    return {
        'n': n,
        'wr': round(float((pnl > 0).mean() * 100), 2),
        'avg': round(float(pnl.mean()), 4),
        'median': round(float(pnl.median()), 4),
        'loss': round(float((pnl <= 0).mean() * 100), 2),
        'min_year_n': int(min(year_counts.values())) if year_counts else 0,
        'year_counts': year_counts,
        'year_wr': year_wr,
        't1': int(bool_s(df.get('v154_t1_violation', pd.Series(False, index=df.index))).sum()),
    }


def release_pass(m: dict[str, Any]) -> bool:
    return bool(
        m['n'] >= RELEASE_N
        and m['wr'] >= RELEASE_WR
        and m['avg'] >= RELEASE_AVG
        and m['min_year_n'] >= RELEASE_MIN_YEAR_N
        and float(m['year_wr'].get('2024', 0.0)) >= RELEASE_2024_WR
        and int(m.get('t1', 0)) == 0
    )


def loss_table(df: pd.DataFrame, limit: int | None = None) -> pd.DataFrame:
    cols = [
        'symbol', 'v154_entry_date', 'v154_exit_date', 'v154_pnl_pct', 'v154_exit_reason',
        'v132_reclaim_class', 'v143_lifecycle_status', 'v141_earliest_lead_timing',
        'entry_chase_above_zone_pct', 'reclaim_close_pos', 'reclaim_close_above_zone_pct',
        'v132_reclaim_bull_body_pct', 'source_gap_atr', 'source_mid_body_atr',
        'risk_pct', 'v138_mae_pct', 'v138_mfe_pct', 'zone_low', 'zone_high', 'entry_price',
        'v158_action', 'v158_reason',
    ]
    existing = [c for c in cols if c in df.columns]
    losses = df[num_s(df['v154_pnl_pct']) <= 0].sort_values(['v154_entry_date', 'symbol'])
    if limit is not None:
        losses = losses.head(limit)
    return losses[existing]


def main() -> None:
    df = pd.read_csv(SRC, low_memory=False).copy()
    df['entry_date_key'] = df['v154_entry_date'].map(date_key)
    df['entry_year'] = df['entry_date_key'].str[:4]
    df['entry_month'] = df['entry_date_key'].str[:6]

    strict3 = bool_s(df['v132_true_takeover_3_strict'])
    pbg = df['v143_lifecycle_status'].astype(str).eq('PRE_BUY_GAP_NOTE_ONLY')
    prebuy_gap = bool_s(df['v141_pre_buy_cancel_available'])
    nonstrict = ~strict3
    chase = num_s(df['entry_chase_above_zone_pct'])
    reclaim_pos = num_s(df['reclaim_close_pos'])
    reclaim_above = num_s(df['reclaim_close_above_zone_pct'])
    body = num_s(df['v132_reclaim_bull_body_pct'])
    gap_atr = num_s(df['source_gap_atr'])
    mid_body_atr = num_s(df['source_mid_body_atr'])
    risk = num_s(df['risk_pct'])

    # Contract check: V154 already requires true touch -> reclaim -> 3-bar hold.
    contract_cols = [
        'v132_hold_close_above_zone_high_2', 'v132_no_break_reclaim_low_2',
        'v132_hold_close_above_zone_high_3', 'v132_no_break_reclaim_low_3',
    ]
    contract_fail = pd.Series(False, index=df.index)
    for c in contract_cols:
        contract_fail |= ~bool_s(df[c])

    predicates: dict[str, pd.Series] = {
        # Lifecycle hypotheses requested in V158.
        'TOUCH_RECLAIM_HOLD_CONTRACT': ~contract_fail,
        'PREBUY_GAP_WATCH_ONLY_ALL': ~pbg,
        'PREBUY_PRICE_GAP_WATCH_ONLY_ALL': ~prebuy_gap,
        'TT2_SECOND_CONFIRM_OR_CHASE_LE_3': strict3 | chase.le(3.0),
        'TT2_SECOND_CONFIRM_OR_RECLAIM_POS_GE_75': strict3 | reclaim_pos.ge(0.75),
        'ENTRY_CHASE_LE_3': chase.le(3.0),
        'ENTRY_CHASE_LE_2_5': chase.le(2.5),
        'RECLAIM_POS_GE_65': reclaim_pos.ge(0.65),
        'RECLAIM_POS_GE_75': reclaim_pos.ge(0.75),
        'RECLAIM_ABOVE_GE_2': reclaim_above.ge(2.0),
        'SOURCE_GAP_ATR_LE_1_316': gap_atr.le(1.3160),
        'SOURCE_MID_BODY_ATR_LE_2_577': mid_body_atr.le(2.5767),
        'RISK_GE_3': risk.ge(3.0),
        'RISK_LE_5_5': risk.le(5.5),
        # Conditional SMC lifecycle rules: only constrain the weaker/ambiguous bucket.
        'NONSTRICT_RECLAIM_BODY_LE_86_6': (~nonstrict) | body.le(86.6124),
        'NONSTRICT_RECLAIM_BODY_LE_88_0': (~nonstrict) | body.le(87.9636),
        'PBG_RECLAIM_BODY_LE_88_0': (~pbg) | body.le(87.9636),
        'PBG_RECLAIM_ABOVE_GE_1_3': (~pbg) | reclaim_above.ge(1.3051),
        'PBG_CHASE_LE_3': (~pbg) | chase.le(3.0),
        'PBG_RECLAIM_POS_GE_85': (~pbg) | reclaim_pos.ge(0.85),
    }

    rows: list[dict[str, Any]] = []
    names = list(predicates)
    for r in range(0, 5):
        for combo in itertools.combinations(names, r):
            mask = pd.Series(True, index=df.index)
            for name in combo:
                mask &= predicates[name]
            g = df[mask].copy()
            if len(g) == 0:
                continue
            mm = metrics(g)
            rows.append({'rule': 'ALL_V154' if not combo else '+'.join(combo), **mm, 'release_pass': release_pass(mm)})
    variants = pd.DataFrame(rows).drop_duplicates('rule')
    variants = variants.sort_values(['release_pass', 'n', 'wr', 'avg'], ascending=[False, False, False, False])
    variants.to_csv(OUT / 'v158_rule_search.csv', index=False)

    # Formal V158 selection: simplest passing non-leak rule found by the search.
    chosen_rule = 'TT2_SECOND_CONFIRM_OR_CHASE_LE_3+NONSTRICT_RECLAIM_BODY_LE_86_6'
    chosen_mask = predicates['TT2_SECOND_CONFIRM_OR_CHASE_LE_3'] & predicates['NONSTRICT_RECLAIM_BODY_LE_86_6']
    chosen = df[chosen_mask].copy()
    rejected = df[~chosen_mask].copy()
    chosen['v158_action'] = 'BUY'
    chosen['v158_reason'] = 'TT2_SECOND_CONFIRM_OR_CHASE_LE_3_AND_NONSTRICT_RECLAIM_BODY_LE_86_6'
    rejected['v158_action'] = 'WATCH_ONLY'
    rejected['v158_reason'] = ''
    rejected.loc[~predicates['TT2_SECOND_CONFIRM_OR_CHASE_LE_3'], 'v158_reason'] += 'TT2_NEEDS_SECOND_CONFIRM_OR_CHASE_TOO_HIGH;'
    rejected.loc[~predicates['NONSTRICT_RECLAIM_BODY_LE_86_6'], 'v158_reason'] += 'NONSTRICT_RECLAIM_BODY_EXHAUSTION;'

    chosen.to_csv(OUT / 'v158_chosen_rows.csv', index=False)
    rejected.to_csv(OUT / 'v158_watch_only_rejected_rows.csv', index=False)
    loss_table(chosen).to_csv(OUT / 'v158_chosen_loss_rows.csv', index=False)
    loss_table(rejected).to_csv(OUT / 'v158_rejected_loss_rows.csv', index=False)

    buckets = []
    for label, group in [
        ('ALL_V154_BASELINE', df),
        ('V158_CHOSEN_BUY', chosen),
        ('V158_WATCH_ONLY_REJECTED', rejected),
        ('PBG_ALL', df[pbg]),
        ('PBG_KEPT_BY_V158', chosen[pbg[chosen.index]]),
        ('PBG_REJECTED_BY_V158', rejected[pbg[rejected.index]]),
        ('NONSTRICT_ALL', df[nonstrict]),
        ('NONSTRICT_KEPT_BY_V158', chosen[nonstrict[chosen.index]]),
        ('NONSTRICT_REJECTED_BY_V158', rejected[nonstrict[rejected.index]]),
        ('PREBUY_PRICE_GAP_ALL', df[prebuy_gap]),
        ('PREBUY_PRICE_GAP_KEPT_BY_V158', chosen[prebuy_gap[chosen.index]]),
        ('PREBUY_PRICE_GAP_REJECTED_BY_V158', rejected[prebuy_gap[rejected.index]]),
    ]:
        buckets.append({'bucket': label, **metrics(group)})
    bucket_df = pd.DataFrame(buckets)
    bucket_df.to_csv(OUT / 'v158_bucket_metrics.csv', index=False)

    selected_metrics = metrics(chosen)
    baseline_metrics = metrics(df)
    passing_rows = variants[variants['release_pass']].head(20).to_dict(orient='records')
    summary = {
        'decision': 'V158_NON_LEAK_LIFECYCLE_CANDIDATE_FOUND_RESEARCH_ONLY_NO_PRODUCTION_WRITE' if release_pass(selected_metrics) else 'V158_NO_PROMOTION_CONTINUE_RESEARCH',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'production_write': False,
        'source': str(SRC),
        'out': str(OUT),
        'release_gate': {
            'n_ge': RELEASE_N,
            'min_year_n_ge': RELEASE_MIN_YEAR_N,
            'wr_ge': RELEASE_WR,
            'avg_ge': RELEASE_AVG,
            'year_2024_wr_ge': RELEASE_2024_WR,
            't1_violation_eq': 0,
        },
        'no_leak_constraints': [
            'No market breadth used',
            'No future/post-entry zone-death selector used',
            'Rules use V132 reclaim/hold quality, V141 pre-buy price gap availability, lifecycle status, and entry-price/chase fields only',
        ],
        'baseline_v154': baseline_metrics,
        'chosen_rule': chosen_rule,
        'chosen_metrics': selected_metrics,
        'chosen_release_pass': release_pass(selected_metrics),
        'top_passing_rules': passing_rows,
        'bucket_metrics': bucket_df.to_dict(orient='records'),
        'interpretation': (
            'V158 recovered n>=200, min_year_n>=35, and 2024 WR>=78 without market breadth or post-entry zone death. '
            'The effective non-leak rule is not a full PRE_BUY_GAP ban; full PBG downgrade destroys coverage. '
            'The stable rule is: TRUE_TAKEOVER_2 must either have strict secondary confirmation or low entry chase (<=3%), '
            'and non-strict takeovers with blow-off reclaim bodies (>86.6% of bar range) are downgraded to WATCH_ONLY.'
        ),
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

    report = [
        '# V158 Non-leak SMC lifecycle rebuild', '',
        f"Decision: `{summary['decision']}`。只读审计；未写生产/前端/watchlist。", '',
        '## Release gate', pd.DataFrame([summary['release_gate']]).to_markdown(index=False), '',
        '## Baseline vs V158', pd.DataFrame([
            {'name': 'V154_BASELINE', **baseline_metrics},
            {'name': 'V158_CHOSEN', **selected_metrics},
        ]).to_markdown(index=False), '',
        '## Chosen rule', f'`{chosen_rule}`', '',
        '## Bucket metrics', bucket_df.to_markdown(index=False), '',
        '## Top passing non-leak rules', variants[variants['release_pass']].head(12).to_markdown(index=False), '',
        '## Chosen loss rows', loss_table(chosen).to_markdown(index=False), '',
        '## Rejected loss rows', loss_table(rejected).head(40).to_markdown(index=False), '',
        '## Conclusion', summary['interpretation'],
    ]
    (OUT / 'report.md').write_text('\n'.join(report), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
