#!/usr/bin/env python3
"""V154: add-back audit after V153.

V153 fixed the two user-raised issues by rejecting synthetic BE +0.5% exits
and restoring baseline exits, but still removed all CANCEL_AFTER_ENTRY_DAY_CLOSE
rows. V154 tests whether a structurally justified subset of that excluded
bucket can be added back to improve yearly trade count without reintroducing
synthetic +0.5% pseudo-wins.

No production/frontend/watchlist writes.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd

ROOT = Path('/root/.hermes')
IN = ROOT / 'smc_audit' / 'v150_lifecycle_sl_adjust_backtest_20260621' / 'v150_executed_rows.csv'
OUT = ROOT / 'smc_audit' / 'v154_cancel_addback_no_micro_20260622'
OUT.mkdir(parents=True, exist_ok=True)
MICRO_LO = 0.45
MICRO_HI = 0.55


def fnum(df: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in df:
        return pd.Series([default] * len(df), index=df.index, dtype='float64')
    return pd.to_numeric(df[col], errors='coerce').fillna(default)


def bseries(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df:
        return pd.Series([False] * len(df), index=df.index)
    return df[col].astype(str).str.lower().eq('true')


def prep(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out['v154_entry_date'] = out['v138_entry_date'].astype(str).str.replace('-', '', regex=False).str[:8]
    out['v154_exit_date'] = out['v138_exit_date'].astype(str).str.replace('-', '', regex=False).str[:8]
    out['v154_year'] = out['v154_entry_date'].astype(str).str[:4]
    out['v154_pnl_pct'] = fnum(out, 'v138_pnl_pct')
    out['v154_exit_reason'] = out['v138_exit_reason']
    out['v154_t1_violation'] = out['v154_entry_date'].eq(out['v154_exit_date'])
    out['v154_synthetic_be'] = False
    out['v154_micro_pnl'] = out['v154_pnl_pct'].between(MICRO_LO, MICRO_HI, inclusive='both')
    return out


def metrics(df: pd.DataFrame) -> dict[str, Any]:
    n = int(len(df))
    if n == 0:
        return {'n': 0, 'wr': 0.0, 'avg': 0.0, 'median': 0.0, 'loss': 0.0, 'micro_n': 0, 'micro_pct': 0.0, 'synthetic_be_n': 0, 'hard_exit': 0.0, 'recent_n': 0, 'recent_wr': 0.0, 't1': 0, 'min_year_n': 0, 'year_counts': {}}
    pnl = fnum(df, 'v154_pnl_pct')
    years = {str(k): int(v) for k, v in df.groupby('v154_year').size().sort_index().items()}
    hard = df['v154_exit_reason'].astype(str).isin(['ZONE_CLOSE_DEAD_T1', 'STRUCTURE_SL_T1', 'LIFECYCLE_CANCEL_NEXT_OPEN'])
    recent = df[bseries(df, 'is_recent45')]
    rp = fnum(recent, 'v154_pnl_pct') if len(recent) else pd.Series(dtype=float)
    return {
        'n': n,
        'wr': round(float((pnl > 0).mean() * 100), 2),
        'avg': round(float(pnl.mean()), 4),
        'median': round(float(pnl.median()), 4),
        'loss': round(float((pnl <= 0).mean() * 100), 2),
        'micro_n': int(df['v154_micro_pnl'].sum()),
        'micro_pct': round(float(df['v154_micro_pnl'].mean() * 100), 2),
        'synthetic_be_n': int(df['v154_synthetic_be'].sum()),
        'hard_exit': round(float(hard.mean() * 100), 2),
        'recent_n': int(len(recent)),
        'recent_wr': round(float((rp > 0).mean() * 100), 2) if len(recent) else 0.0,
        't1': int(df['v154_t1_violation'].astype(bool).sum()),
        'min_year_n': int(min(years.values())) if years else 0,
        'year_counts': years,
    }


def yearly(df: pd.DataFrame, variant: str) -> list[dict[str, Any]]:
    return [{'variant': variant, 'year': str(year), **metrics(g)} for year, g in df.groupby('v154_year')]


def main() -> None:
    src = pd.read_csv(IN, low_memory=False)
    base_all = prep(src[src['v150_variant'].eq('BASELINE_V138_RECLAIM_NEXT_OPEN')].copy())
    main = base_all[base_all['v143_lifecycle_status'].ne('CANCEL_AFTER_ENTRY_DAY_CLOSE')].copy()
    cancel = base_all[base_all['v143_lifecycle_status'].eq('CANCEL_AFTER_ENTRY_DAY_CLOSE')].copy()

    addback_rules: dict[str, pd.Series] = {
        'NO_ADD_BACK_V153': pd.Series([False] * len(cancel), index=cancel.index),
        'ADD_CANCEL_RECLAIM_POS_GE_81_7': fnum(cancel, 'v132_reclaim_close_pos_pct') >= 81.7,
        'ADD_CANCEL_SOURCE_GAP_ATR_LE_0_3919': fnum(cancel, 'source_gap_atr') <= 0.3919,
        'ADD_CANCEL_MID_BODY_ATR_LE_0_9649': fnum(cancel, 'source_mid_body_atr') <= 0.9649,
        'ADD_CANCEL_ZONE_WIDTH_LE_1_2175': fnum(cancel, 'v85_zone_width_pct') <= 1.2175,
        'ADD_CANCEL_ENTRY_ABOVE_RECLAIM_GE_0': fnum(cancel, 'v138_entry_above_reclaim_close_pct') >= 0.0,
        'ADD_CANCEL_RECLAIM_ABOVE_ZONE_LE_1_5': fnum(cancel, 'reclaim_close_above_zone_pct') <= 1.5,
    }

    metric_rows: list[dict[str, Any]] = []
    year_rows: list[dict[str, Any]] = []
    addback_rows: list[pd.DataFrame] = []
    chosen_name = ''
    chosen_df = pd.DataFrame()

    candidates: list[tuple[float, float, int, int, str, pd.DataFrame, dict[str, Any]]] = []
    for name, mask in addback_rules.items():
        add = cancel[mask].copy()
        add['v154_addback_rule'] = name
        body = pd.concat([main.assign(v154_addback_rule='MAIN_NON_CANCEL'), add], ignore_index=True)
        body['v154_variant'] = name
        m = metrics(body)
        add_m = metrics(add)
        row = {'variant': name, 'addback_n': int(len(add)), **m, 'addback_wr': add_m['wr'], 'addback_avg': add_m['avg']}
        metric_rows.append(row)
        year_rows.extend(yearly(body, name))
        body.to_csv(OUT / f'{name.lower()}_rows.csv', index=False)
        if len(add):
            addback_rows.append(add.assign(v154_variant=name))
        if (
            m['n'] >= 240
            and m['min_year_n'] >= 35
            and m['synthetic_be_n'] == 0
            and m['micro_pct'] <= 1.0
            and m['wr'] >= 82.0
            and m['avg'] >= 3.2
            and m['t1'] == 0
        ):
            # Sort by coverage first, then WR/avg; this task is specifically about low yearly volume.
            candidates.append((m['n'], m['wr'], m['avg'], m['min_year_n'], name, body, m))

    candidates.sort(key=lambda x: (x[0], x[3], x[1], x[2]), reverse=True)
    if candidates:
        _, _, _, _, chosen_name, chosen_df, chosen_m = candidates[0]
    else:
        chosen_name = 'NO_PROMOTABLE_ADD_BACK'
        chosen_df = main.copy()
        chosen_m = metrics(chosen_df)

    metric_df = pd.DataFrame(metric_rows).sort_values(['n', 'wr', 'avg'], ascending=[False, False, False])
    year_df = pd.DataFrame(year_rows)
    metric_df.to_csv(OUT / 'v154_variant_metrics.csv', index=False)
    year_df.to_csv(OUT / 'v154_yearly_metrics.csv', index=False)
    if addback_rows:
        pd.concat(addback_rows, ignore_index=True).to_csv(OUT / 'v154_all_addback_rows.csv', index=False)
    chosen_df.to_csv(OUT / 'v154_chosen_rows.csv', index=False)

    # Loss and excluded diagnostics for the chosen candidate.
    chosen_loss = chosen_df[fnum(chosen_df, 'v154_pnl_pct') <= 0].copy()
    chosen_loss.to_csv(OUT / 'v154_chosen_loss_rows.csv', index=False)
    cancel_not_added = cancel[~cancel.index.isin(chosen_df.index)].copy()
    cancel_not_added.to_csv(OUT / 'v154_cancel_not_added_rows.csv', index=False)

    base_m = metrics(base_all)
    v153_m = metrics(main)
    release_gate = {
        'pass': bool(candidates),
        'checks': {
            'n_ge_240': chosen_m['n'] >= 240,
            'min_year_n_ge_35': chosen_m['min_year_n'] >= 35,
            'synthetic_be_zero': chosen_m['synthetic_be_n'] == 0,
            'micro_pct_le_1pct': chosen_m['micro_pct'] <= 1.0,
            'wr_ge_82': chosen_m['wr'] >= 82.0,
            'avg_ge_3p2': chosen_m['avg'] >= 3.2,
            't1_zero': chosen_m['t1'] == 0,
        },
    }

    summary = {
        'decision': 'V154_ADD_BACK_CANDIDATE_PROMOTABLE_TO_STABILITY_AUDIT' if release_gate['pass'] else 'V154_RESEARCH_ONLY',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'production_write': False,
        'source': str(IN),
        'out': str(OUT),
        'baseline_all': base_m,
        'v153_no_cancel': v153_m,
        'chosen_variant': chosen_name,
        'chosen_metrics': chosen_m,
        'release_gate': release_gate,
        'variant_metrics': metric_df.to_dict(orient='records'),
        'interpretation': {
            'why_v152_rejected': 'V152 synthetic BE produced 0.5% pseudo-wins and reduced yearly volume.',
            'why_addback_rule': 'Among weak CANCEL_AFTER_ENTRY_DAY_CLOSE rows, high reclaim close position indicates the close still recovered to the upper part of the candle; this is a structural recovery subset, not a synthetic exit.',
            'next_required': 'Run rolling/monthly stability and per-loss root cause on v154_chosen_rows before any production promotion.',
        },
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

    report = [
        '# V154 Cancel Add-back / No Micro-PnL Audit', '',
        f"Decision: `{summary['decision']}`。只读研究，不写生产。", '',
        '## Variant metrics', metric_df.to_markdown(index=False), '',
        '## Yearly metrics', year_df.to_markdown(index=False), '',
        '## Release gate', '```json', json.dumps(release_gate, ensure_ascii=False, indent=2), '```'
    ]
    (OUT / 'report.md').write_text('\n'.join(report), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
