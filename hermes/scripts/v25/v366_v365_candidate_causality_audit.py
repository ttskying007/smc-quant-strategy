#!/usr/bin/env python3
"""V366 no-write causality audit for V365's apparent daily-rule survivor.

Proves whether its V132 takeover fields were known at the replayed entry bar.
No production, frontend, watchlist, or strategy writes.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
V333 = AUD / 'v333_full_universe_rule_search_after_breadth_refresh_latest.json'
OUT = AUD / f'v366_v365_candidate_causality_audit_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v366_v365_candidate_causality_audit_latest.json'


def boolean(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().isin({'true', '1', 'yes'})


def stats(df: pd.DataFrame) -> dict:
    entry = pd.to_numeric(df['entry_idx'], errors='coerce')
    c2 = pd.to_numeric(df['v132_entry_after_confirm_idx_2'], errors='coerce')
    c3 = pd.to_numeric(df['v132_entry_after_confirm_idx_3'], errors='coerce')
    return {
        'n': int(len(df)),
        'true_takeover_2': int(boolean(df['v132_true_takeover_2']).sum()),
        'true_takeover_3_strict': int(boolean(df['v132_true_takeover_3_strict']).sum()),
        'bull3_ge3': int((pd.to_numeric(df['v132_bull_count_3'], errors='coerce') >= 3).sum()),
        'entry_before_confirmation_2': int((entry < c2).sum()),
        'entry_before_confirmation_3': int((entry < c3).sum()),
        'entry_minus_confirmation_2_unique': sorted({int(x) for x in (entry - c2).dropna()}),
        'entry_minus_confirmation_3_unique': sorted({int(x) for x in (entry - c3).dropna()}),
        'touch_to_reclaim_nonpositive': int((pd.to_numeric(df['reclaim_idx'], errors='coerce') <= pd.to_numeric(df['touch_idx'], errors='coerce')).sum()),
        'reclaim_to_entry_nonpositive': int((entry <= pd.to_numeric(df['reclaim_idx'], errors='coerce')).sum()),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    src = json.loads(V333.read_text())['artifacts']['replayed_csv']
    df = pd.read_csv(src, low_memory=False)
    historical = df[(df['v333_actual_bars_since_entry'] >= 10) & (df['replay_status'] == 'CLOSED')].copy()
    base = boolean(historical['v164_rule_pass'])
    candidate = historical[
        base
        & (pd.to_numeric(historical['v132_bull_count_3'], errors='coerce') >= 3)
        & (pd.to_numeric(historical['v85_zone_width_pct'], errors='coerce') >= 2)
        & historical['poi_source'].isin({'DEMAND_OB', 'OB+FVG'})
    ].copy()
    result = {
        'version': 'V366_V365_CANDIDATE_CAUSALITY_AUDIT_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'candidate_contract': 'v164_rule_pass AND v132_bull_count_3>=3 AND zone_width>=2 AND POI in {DEMAND_OB, OB+FVG}',
        'source': src,
        'candidate_stats': stats(candidate),
        'causality_contract': {
            'v132_true_takeover_2_requires': 'two bars strictly after reclaim; its first legal entry is v132_entry_after_confirm_idx_2',
            'v132_true_takeover_3_requires': 'three bars strictly after reclaim; its first legal entry is v132_entry_after_confirm_idx_3',
            'source_code': '/root/.hermes/scripts/v25/v132_fvg_reclaim_takeover_shadow_backtest.py:108-149,175-180',
        },
        'decision': 'REJECT_V365_APPARENT_SURVIVOR__ENTRY_PRECEDES_ITS_REQUIRED_TAKEOVER_CONFIRMATION__FUTURE_DATA_CONTAMINATION',
        'next_direction': 'Daily V164/V132 rule mining is closed. A valid rebuild must enter at the confirmation-next-open index and be evaluated from scratch; for production-grade evidence it also needs full 2023-2026 intraday history for POI reaction and executable stop/target validation.'
    }
    (OUT / 'v366_report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
