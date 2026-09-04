#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path('/root/.hermes')
V160_BACKTEST = ROOT / 'smc_audit' / 'v160_v158_robust_monthly_rule_search_20260622' / 'v160_chosen_rows.csv'
V161_BUY_RECENT = ROOT / 'smc_audit' / 'v161_dry_run_scanner_contract_20260622' / 'v161_v160_buy_recent45.json'
V161_ALL_RECENT = ROOT / 'smc_audit' / 'v161_dry_run_scanner_contract_20260622' / 'v161_dryrun_recent45.json'
OUT = ROOT / 'smc_audit' / 'v163_scanner_rule_integrity_audit_20260622'
OUT.mkdir(parents=True, exist_ok=True)

ENGINE = 'V163_SCANNER_RULE_INTEGRITY_AUDIT'
BODY_RELEASE_MAX = 87.1077


def num_s(s: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(s, errors='coerce').fillna(default)


def bool_s(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower().isin({'true', '1', 'yes'})


def load_json_df(path: Path) -> pd.DataFrame:
    with path.open() as f:
        return pd.DataFrame(json.load(f))


def classify_integrity(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    cls = df.get('v132_reclaim_class', pd.Series('', index=df.index)).astype(str)
    tt2 = bool_s(df.get('v132_true_takeover_2', pd.Series(False, index=df.index)))
    tt3 = bool_s(df.get('v132_true_takeover_3_strict', pd.Series(False, index=df.index)))
    body = num_s(df.get('v132_reclaim_bull_body_pct', pd.Series(999.0, index=df.index)), 999.0)
    df['v163_true_takeover_2_or_3'] = tt2 | tt3
    df['v163_release_body_pass'] = body <= BODY_RELEASE_MAX
    df['v163_integrity_fail_reason'] = ''
    df.loc[~df['v163_true_takeover_2_or_3'], 'v163_integrity_fail_reason'] = 'NOT_TRUE_TAKEOVER_2_OR_3'
    df.loc[df['v163_true_takeover_2_or_3'] & ~df['v163_release_body_pass'], 'v163_integrity_fail_reason'] = 'BODY_GT_87_1077'
    df.loc[df['v163_true_takeover_2_or_3'] & df['v163_release_body_pass'], 'v163_integrity_fail_reason'] = 'PASS'
    df['v163_rule_pass'] = df['v163_integrity_fail_reason'].eq('PASS')
    df['v163_action'] = df['v163_rule_pass'].map(lambda x: 'BUY' if x else 'WATCH_ONLY')
    df['v163_engine'] = ENGINE
    return df


def vc(series: pd.Series, limit: int = 30) -> dict[str, int]:
    return {str(k): int(v) for k, v in series.value_counts(dropna=False).head(limit).items()}


def slim_rows(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        'symbol', 'poi_source', 'combo_family', 'event_type', 'entry_date', 'entry_price',
        'bars_since_entry', 'market_state', 'risk_pct', 'entry_chase_above_zone_pct',
        'reclaim_close_above_zone_pct', 'reclaim_close_pos', 'touch_to_reclaim_bars',
        'v132_reclaim_class', 'v132_reclaim_bull_body_pct', 'v132_reclaim_close_pos_pct',
        'v132_true_takeover_2', 'v132_true_takeover_3_strict',
        'v160_dry_action', 'v160_dry_reason', 'v163_action', 'v163_integrity_fail_reason',
    ]
    return df[[c for c in cols if c in df.columns]].copy()


def main() -> None:
    back = pd.read_csv(V160_BACKTEST, low_memory=False)
    buy = load_json_df(V161_BUY_RECENT)
    recent = load_json_df(V161_ALL_RECENT)
    buy = classify_integrity(buy)
    recent = classify_integrity(recent)

    back_cls = back.get('v132_reclaim_class', pd.Series('', index=back.index)).astype(str)
    back_tt23 = bool_s(back.get('v132_true_takeover_2', pd.Series(False, index=back.index))) | bool_s(back.get('v132_true_takeover_3_strict', pd.Series(False, index=back.index)))
    buy_cls = buy.get('v132_reclaim_class', pd.Series('', index=buy.index)).astype(str)

    pass_recent = buy[buy['v163_rule_pass']].copy()
    fail_recent = buy[~buy['v163_rule_pass']].copy()
    latest_date = str(pass_recent['entry_date'].max()) if not pass_recent.empty and 'entry_date' in pass_recent.columns else ''
    latest_pass = pass_recent[pass_recent['entry_date'].astype(str).eq(latest_date)].copy() if latest_date else pass_recent.iloc[0:0].copy()

    summary: dict[str, Any] = {
        'decision': 'V160_DRY_RUN_RULE_HAS_SCANNER_INTEGRITY_BUG__DO_NOT_PROMOTE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'engine': ENGINE,
        'sources': {
            'v160_backtest': str(V160_BACKTEST),
            'v161_v160_buy_recent45': str(V161_BUY_RECENT),
            'v161_all_recent45': str(V161_ALL_RECENT),
        },
        'root_cause': {
            'apply_v160_missing_precondition': 'Rule uses (strict3 OR chase<=3.5) AND body<=86.6; it never requires TRUE_TAKEOVER_2/TRUE_TAKEOVER_3_STRICT. In historical V154/V160 rows this was hidden because the source was already takeover-clean. In real scanner dry-run rows it lets FAILED/RECOVERY/UNCLEAR reclaim classes become BUY.',
            'required_precondition': 'v132_true_takeover_2 OR v132_true_takeover_3_strict',
            'release_body_cap_from_v162': BODY_RELEASE_MAX,
        },
        'historical_v160_backtest': {
            'rows': int(len(back)),
            'true_takeover_2_or_3_rows': int(back_tt23.sum()),
            'non_takeover_rows': int((~back_tt23).sum()),
            'class_counts': vc(back_cls),
        },
        'scanner_v161_v160_buy_recent45': {
            'rows': int(len(buy)),
            'class_counts': vc(buy_cls),
            'failed_recovery_unclear_rows': int(buy_cls.str.contains('FAILED|RECOVERY|UNCLEAR', regex=True).sum()),
            'true_takeover_2_or_3_rows': int(buy['v163_true_takeover_2_or_3'].sum()),
            'v163_integrity_pass_rows': int(buy['v163_rule_pass'].sum()),
            'v163_integrity_reject_rows': int((~buy['v163_rule_pass']).sum()),
            'reject_reasons': vc(buy['v163_integrity_fail_reason']),
            'poi_counts_before': vc(buy.get('poi_source', pd.Series('', index=buy.index))),
            'poi_counts_after': vc(pass_recent.get('poi_source', pd.Series('', index=pass_recent.index))),
            'entry_date_counts_after_tail': {str(k): int(v) for k, v in pass_recent.get('entry_date', pd.Series(dtype=str)).astype(str).value_counts().sort_index().tail(30).items()},
            'latest_pass_entry_date': latest_date,
            'latest_pass_rows': int(len(latest_pass)),
        },
        'all_recent45_context': {
            'rows': int(len(recent)),
            'v160_buy_rows': int((recent.get('v160_dry_action', pd.Series('', index=recent.index)).astype(str) == 'BUY').sum()),
            'v163_pass_rows': int(recent['v163_rule_pass'].sum()),
            'v163_pass_class_counts': vc(recent.loc[recent['v163_rule_pass'], 'v132_reclaim_class']),
        },
    }

    slim_rows(pass_recent).to_csv(OUT / 'v163_recent45_integrity_pass.csv', index=False)
    slim_rows(fail_recent).to_csv(OUT / 'v163_recent45_integrity_reject.csv', index=False)
    slim_rows(latest_pass).to_csv(OUT / 'v163_latest_integrity_pass.csv', index=False)
    with (OUT / 'summary.json').open('w') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    report = []
    report.append('# V163 Scanner Rule Integrity Audit')
    report.append('')
    report.append('Decision: `V160_DRY_RUN_RULE_HAS_SCANNER_INTEGRITY_BUG__DO_NOT_PROMOTE`。只读审计；未写生产/前端/watchlist。')
    report.append('')
    report.append('## Root cause')
    report.append('')
    report.append('- V160 dry-run selector only checks `(strict3 OR entry_chase<=3.5) AND body<=86.6`.')
    report.append('- It does **not** require `TRUE_TAKEOVER_2/TRUE_TAKEOVER_3_STRICT`.')
    report.append('- Historical V160 backtest rows were already takeover-clean, so the bug was hidden there.')
    report.append('- Real scanner rows are not takeover-clean; therefore `FAILED_RECLAIM_* / RECOVERY_SEPARATE / UNCLEAR_RECLAIM` leaked into BUY.')
    report.append('')
    report.append('## Key counts')
    rows = [
        {'scope': 'historical_v160_backtest', 'rows': summary['historical_v160_backtest']['rows'], 'non_takeover_rows': summary['historical_v160_backtest']['non_takeover_rows'], 'v163_pass_rows': ''},
        {'scope': 'scanner_v161_v160_buy_recent45', 'rows': summary['scanner_v161_v160_buy_recent45']['rows'], 'non_takeover_or_body_reject': summary['scanner_v161_v160_buy_recent45']['v163_integrity_reject_rows'], 'v163_pass_rows': summary['scanner_v161_v160_buy_recent45']['v163_integrity_pass_rows']},
        {'scope': 'all_recent45_context', 'rows': summary['all_recent45_context']['rows'], 'v160_buy_rows': summary['all_recent45_context']['v160_buy_rows'], 'v163_pass_rows': summary['all_recent45_context']['v163_pass_rows']},
    ]
    report.append(pd.DataFrame(rows).to_markdown(index=False))
    report.append('')
    report.append('## Scanner V160 BUY class leakage')
    report.append(pd.DataFrame([{'class': k, 'n': v} for k, v in summary['scanner_v161_v160_buy_recent45']['class_counts'].items()]).to_markdown(index=False))
    report.append('')
    report.append('## V163 integrity rule')
    report.append('')
    report.append('```text')
    report.append('(v132_true_takeover_2 OR v132_true_takeover_3_strict)')
    report.append(f'AND v132_reclaim_bull_body_pct <= {BODY_RELEASE_MAX}')
    report.append('```')
    report.append('')
    report.append('## Latest pass rows')
    report.append('')
    if latest_pass.empty:
        report.append('None')
    else:
        report.append(slim_rows(latest_pass).to_markdown(index=False))
    report.append('')
    report.append('## Artifacts')
    report.append('')
    report.append(f'- `{OUT / "summary.json"}`')
    report.append(f'- `{OUT / "v163_recent45_integrity_pass.csv"}`')
    report.append(f'- `{OUT / "v163_recent45_integrity_reject.csv"}`')
    report.append(f'- `{OUT / "v163_latest_integrity_pass.csv"}`')
    (OUT / 'report.md').write_text('\n'.join(report) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
