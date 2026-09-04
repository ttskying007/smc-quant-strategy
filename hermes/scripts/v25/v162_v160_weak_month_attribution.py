#!/usr/bin/env python3
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Any
import itertools
import numpy as np
import pandas as pd

ROOT = Path('/root/.hermes')
SRC = ROOT / 'smc_audit' / 'v160_v158_robust_monthly_rule_search_20260622' / 'v160_chosen_rows.csv'
OUT = ROOT / 'smc_audit' / 'v162_v160_weak_month_attribution_20260622'
OUT.mkdir(parents=True, exist_ok=True)

OUTCOME_TOKENS = ('pnl', 'exit', 'mae', 'mfe', 'won', 'hold_bars', 'synthetic', 'micro', 'invalid_reason')
SCANNER_TIME_FEATURES = [
    'poi_source', 'combo_family', 'event_type', 'market_state',
    'risk_pct', 'v85_zone_width_pct', 'entry_chase_above_zone_pct',
    'reclaim_close_above_zone_pct', 'reclaim_close_pos', 'touch_to_reclaim_bars',
    'touch_depth_zone_pct', 'source_gap_atr', 'source_mid_body_atr',
    'v132_reclaim_body_range_pct', 'v132_reclaim_bull_body_pct',
    'v132_reclaim_close_pos_pct', 'v132_reclaim_low_below_zone_high_pct',
    'v132_reclaim_class', 'v132_true_takeover_2', 'v132_true_takeover_3_strict',
    'v132_hold_close_above_zone_high_1', 'v132_hold_close_above_zone_high_2', 'v132_hold_close_above_zone_high_3',
    'v132_no_break_reclaim_low_1', 'v132_no_break_reclaim_low_2', 'v132_no_break_reclaim_low_3',
    'v132_post_zone_pullback_depth_pct_1', 'v132_post_zone_pullback_depth_pct_2', 'v132_post_zone_pullback_depth_pct_3',
]


def num_s(s: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(s, errors='coerce').fillna(default)


def bool_s(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower().isin({'true', '1', 'yes'})


def date_key(v: Any) -> str:
    return str(v or '').replace('-', '')[:8]


def add_time(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['entry_date_key'] = df['v154_entry_date'].map(date_key)
    df['entry_year'] = df.entry_date_key.str[:4]
    df['entry_month'] = df.entry_date_key.str[:6]
    return df


def metrics(df: pd.DataFrame) -> dict[str, Any]:
    n = len(df)
    if n == 0:
        return dict(n=0, wr=0.0, avg=0.0, median=0.0, loss=0.0, min_year_n=0, year_counts={}, year_wr={}, t1=0)
    pnl = num_s(df['v154_pnl_pct'])
    years = df.entry_year.astype(str)
    yc = {str(k): int(v) for k, v in years.value_counts().sort_index().items()}
    yw = {}
    for y in sorted(yc):
        yp = pnl[years.eq(y)]
        yw[y] = round(float((yp > 0).mean() * 100), 2)
    return dict(
        n=int(n),
        wr=round(float((pnl > 0).mean() * 100), 2),
        avg=round(float(pnl.mean()), 4),
        median=round(float(pnl.median()), 4),
        loss=round(float((pnl <= 0).mean() * 100), 2),
        min_year_n=int(min(yc.values())) if yc else 0,
        year_counts=yc,
        year_wr=yw,
        t1=int(bool_s(df.get('v154_t1_violation', pd.Series(False, index=df.index))).sum()),
    )


def monthly_metrics(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for mon, g in df.groupby('entry_month'):
        m = metrics(g)
        rows.append({'entry_month': mon, **m, 'bad60': m['n'] >= 3 and m['wr'] < 60, 'weak78': m['n'] >= 3 and m['wr'] < 78})
    return pd.DataFrame(rows).sort_values('entry_month') if rows else pd.DataFrame()


def release_gate(m: dict[str, Any], bad60: int) -> bool:
    return (
        m['n'] >= 200 and m['wr'] >= 82 and m['avg'] >= 3 and m['min_year_n'] >= 35
        and float(m['year_wr'].get('2024', 0)) >= 78 and m['t1'] == 0 and bad60 == 0
    )


def safe_numeric_features(df: pd.DataFrame) -> list[str]:
    out = []
    for c in SCANNER_TIME_FEATURES:
        if c not in df.columns or any(t in c.lower() for t in OUTCOME_TOKENS):
            continue
        s = pd.to_numeric(df[c], errors='coerce')
        if s.notna().sum() >= 180 and s.nunique(dropna=True) > 2:
            out.append(c)
    return out


def single_filter_search(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c in safe_numeric_features(df):
        s = num_s(df[c])
        qs = sorted(set(float(x) for x in s.quantile([.05, .1, .15, .2, .25, .3, .35, .4, .45, .5, .55, .6, .65, .7, .75, .8, .85, .9, .95]).dropna().values))
        for th in qs:
            for op in ('<=', '>='):
                mask = s.le(th) if op == '<=' else s.ge(th)
                g = df[mask].copy()
                if len(g) < 170:
                    continue
                md = monthly_metrics(g)
                bad60 = int(md.bad60.sum()) if not md.empty else 0
                weak78 = int(md.weak78.sum()) if not md.empty else 0
                m = metrics(g)
                rows.append({'feature': c, 'op': op, 'threshold': round(th, 4), **m, 'bad60': bad60, 'weak78': weak78, 'release_bad0': release_gate(m, bad60)})
    res = pd.DataFrame(rows)
    if not res.empty:
        res = res.sort_values(['bad60', 'weak78', 'n', 'wr', 'avg'], ascending=[True, True, False, False, False])
    return res


def compact_combo_search(df: pd.DataFrame) -> pd.DataFrame:
    preds: list[tuple[str, np.ndarray]] = []
    for c in safe_numeric_features(df):
        s = num_s(df[c])
        arr = s.values
        for q in (.2, .35, .5, .65, .8):
            th = float(s.quantile(q))
            for op in ('<=', '>='):
                mask = arr <= th if op == '<=' else arr >= th
                if int(mask.sum()) >= 170:
                    preds.append((f'{c}{op}{th:.4f}', mask))
    for c in [
        'v132_true_takeover_3_strict', 'v132_true_takeover_2',
        'v132_no_break_reclaim_low_1', 'v132_no_break_reclaim_low_2', 'v132_no_break_reclaim_low_3',
        'v132_hold_close_above_zone_high_1', 'v132_hold_close_above_zone_high_2', 'v132_hold_close_above_zone_high_3',
    ]:
        if c in df.columns:
            b = bool_s(df[c]).values
            if int(b.sum()) >= 170:
                preds.append((c + '==true', b))
    rows = []
    for r in (1, 2):
        for combo in itertools.combinations(range(len(preds)), r):
            mask = np.ones(len(df), dtype=bool)
            names = []
            for i in combo:
                mask &= preds[i][1]
                names.append(preds[i][0])
            if int(mask.sum()) < 180:
                continue
            g = df[mask].copy()
            md = monthly_metrics(g)
            bad60 = int(md.bad60.sum()) if not md.empty else 0
            weak78 = int(md.weak78.sum()) if not md.empty else 0
            m = metrics(g)
            rows.append({'rule': ' & '.join(names), **m, 'bad60': bad60, 'weak78': weak78, 'release_bad0': release_gate(m, bad60), 'robust_full': release_gate(m, bad60) and weak78 == 0})
    res = pd.DataFrame(rows)
    if not res.empty:
        res = res.sort_values(['robust_full', 'release_bad0', 'weak78', 'bad60', 'n', 'wr', 'avg'], ascending=[False, False, True, True, False, False, False])
    return res


def weak_month_row_dump(df: pd.DataFrame, md: pd.DataFrame) -> pd.DataFrame:
    weak_mons = set(md.loc[md.n.ge(3) & md.wr.lt(78), 'entry_month'].astype(str))
    cols = [
        'symbol', 'v154_entry_date', 'v154_pnl_pct', 'v154_exit_reason',
        'poi_source', 'combo_family', 'market_state', 'risk_pct', 'entry_chase_above_zone_pct',
        'reclaim_close_above_zone_pct', 'reclaim_close_pos', 'touch_to_reclaim_bars',
        'v132_reclaim_class', 'v132_reclaim_bull_body_pct', 'v132_reclaim_close_pos_pct',
        'source_gap_atr', 'source_mid_body_atr',
    ]
    cols = [c for c in cols if c in df.columns]
    return df[df.entry_month.isin(weak_mons)].sort_values(['entry_month', 'v154_pnl_pct'])[cols]


def loss_attribution(df: pd.DataFrame) -> pd.DataFrame:
    loss = df[num_s(df['v154_pnl_pct']).le(0)].copy()
    rows = []
    for col in ['v154_exit_reason', 'entry_month', 'poi_source', 'v132_reclaim_class', 'market_state']:
        if col in loss.columns:
            for k, v in loss[col].astype(str).value_counts().items():
                rows.append({'field': col, 'bucket': k, 'loss_n': int(v)})
    return pd.DataFrame(rows)


def main() -> None:
    df = add_time(pd.read_csv(SRC, low_memory=False))
    md = monthly_metrics(df)
    single = single_filter_search(df)
    combos = compact_combo_search(df)
    weak_rows = weak_month_row_dump(df, md)
    losses = loss_attribution(df)

    md.to_csv(OUT / 'v162_v160_monthly_metrics.csv', index=False)
    single.to_csv(OUT / 'v162_single_filter_search.csv', index=False)
    combos.to_csv(OUT / 'v162_compact_combo_search.csv', index=False)
    weak_rows.to_csv(OUT / 'v162_weak_month_rows.csv', index=False)
    losses.to_csv(OUT / 'v162_loss_attribution.csv', index=False)

    bad60 = int(md.bad60.sum()) if not md.empty else 0
    weak78 = int(md.weak78.sum()) if not md.empty else 0
    best_single = single.head(1).to_dict(orient='records')[0] if not single.empty else {}
    strict_single = single[single.release_bad0].head(10).to_dict(orient='records') if not single.empty else []
    strict_combos = combos[combos.release_bad0].head(10).to_dict(orient='records') if not combos.empty else []
    summary = {
        'decision': 'NO_PRODUCTION_PROMOTION__WEAK_MONTHS_NOT_FULLY_REMOVED_BY_NONLEAK_SCANNER_TIME_GATES',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'production_write': False,
        'source': str(SRC),
        'out': str(OUT),
        'base_metrics': metrics(df),
        'base_bad60': bad60,
        'base_weak78': weak78,
        'bad_months': md[md.bad60].to_dict(orient='records'),
        'weak_months': md[md.n.ge(3) & md.wr.lt(78)].to_dict(orient='records'),
        'best_single_filter': best_single,
        'release_bad0_single_filters': strict_single,
        'release_bad0_compact_combos': strict_combos,
        'robust_full_combo_count': int(combos.robust_full.sum()) if not combos.empty else 0,
        'interpretation': {
            'main_root_cause': 'V160 aggregate pass is real, but monthly robustness is fragile: one 202405 high-body strict reclaim loss creates the only WR<60 month; remaining weak months are mostly low-n FVG_Demand/BEAR_RISK clusters where 1-3 zone-dead losses flip month WR below 78.',
            'best_nonleak_gate_found': 'Applying v132_reclaim_bull_body_pct <= ~87.1 to strict and non-strict rows removes bad60 while preserving n=213/min_year_n=35, but weak78 remains 8; stricter <=81.5 improves bad60/weak count but min_year_n drops below release gate.',
            'blocker': 'No tested scanner-time non-outcome filter reaches full robustness (weak78=0) while preserving release coverage. Do not promote V160/V162 to production.',
        },
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

    report = [
        '# V162 V160 weak-month attribution',
        '',
        f"Decision: `{summary['decision']}`。只读审计；未写生产/前端/watchlist。",
        '',
        '## Base V160',
        pd.DataFrame([summary['base_metrics'] | {'bad60': bad60, 'weak78': weak78}]).to_markdown(index=False),
        '',
        '## Weak months',
        md[md.n.ge(3) & md.wr.lt(78)].to_markdown(index=False),
        '',
        '## Loss attribution',
        losses.to_markdown(index=False),
        '',
        '## Best single scanner-time filters',
        single.head(20).to_markdown(index=False) if not single.empty else 'None',
        '',
        '## Release+bad60=0 single filters',
        single[single.release_bad0].head(20).to_markdown(index=False) if not single.empty else 'None',
        '',
        '## Release+bad60=0 compact combos',
        combos[combos.release_bad0].head(20).to_markdown(index=False) if not combos.empty else 'None',
        '',
        '## Weak-month trade rows',
        weak_rows.to_markdown(index=False),
    ]
    (OUT / 'report.md').write_text('\n'.join(report), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
