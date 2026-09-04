#!/usr/bin/env python3
"""V261 no-write: close current-supply mismatch after V259/V260.

Purpose: V259 found a source-safe BOS continuation addback that passes historical
production metrics, but V260 proved it has zero current actionable rows.  This
script verifies whether any current-compatible variant is usable, and explains
why the current scanner supply cannot be promoted.

No production/frontend/watchlist writes.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

BASE = Path('/root/.hermes')
V259_SCRIPT = BASE / 'scripts/v25/v259_bos_continuation_source_safe_rebuild.py'
V258_CURRENT = BASE / 'smc_audit/v258_current_compatible_rich_source_mining_no_write_20260702_084130/v258_current_recent45_nonoverlap_rows.csv'
V259_FRONTIER = BASE / 'smc_audit/v259_bos_continuation_source_safe_rebuild_no_write_20260702_092638/v259_frontier.csv'
V260_SUMMARY = BASE / 'smc_audit/v260_v259_independent_audit_current_smoke_latest.json'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = BASE / f'smc_audit/v261_current_supply_mismatch_closure_no_write_{TS}'
LATEST = BASE / 'smc_audit/v261_current_supply_mismatch_closure_latest.json'

PROD_SELECTOR = {
    'event_type': 'BOS_CONTINUATION',
    'raw_prev20_range_pct_gte': 39.8518000725375,
    'raw_event_body_pct_gte': 75.0000000000003,
}


def load_v259_module():
    spec = importlib.util.spec_from_file_location('v259_source_safe', V259_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot import {V259_SCRIPT}')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def safe_value_counts(df: pd.DataFrame, col: str) -> dict[str, int]:
    if col not in df:
        return {}
    return {str(k): int(v) for k, v in df[col].value_counts(dropna=False).head(20).items()}


def add_raw_features_to_current(df: pd.DataFrame) -> pd.DataFrame:
    mod = load_v259_module()
    cur = df.copy()
    if 'entry_date_s' not in cur:
        cur['entry_date_s'] = cur['entry_date'].astype(str).str.replace('.0', '', regex=False)
    cache: dict[str, list[dict[str, Any]] | None] = {}
    rows: list[dict[str, Any]] = []
    idxs: list[Any] = []
    for idx, row in cur.iterrows():
        feat = mod.raw_features(row, cache)
        if feat is None:
            continue
        rows.append(feat)
        idxs.append(idx)
    return cur.join(pd.DataFrame(rows, index=idxs))


def current_selector_mismatch(cur: pd.DataFrame) -> dict[str, Any]:
    enriched = add_raw_features_to_current(cur)
    event_ok = enriched['event_type'].astype(str).eq(PROD_SELECTOR['event_type'])
    range_ok = pd.to_numeric(enriched['raw_prev20_range_pct'], errors='coerce').ge(PROD_SELECTOR['raw_prev20_range_pct_gte'])
    body_ok = pd.to_numeric(enriched['raw_event_body_pct'], errors='coerce').ge(PROD_SELECTOR['raw_event_body_pct_gte'])
    all_ok = event_ok & range_ok & body_ok

    fail_reasons = {
        'not_bos_continuation': int((~event_ok).sum()),
        'bos_but_prev20_range_lt_39_8518': int((event_ok & ~range_ok).sum()),
        'bos_and_range_ok_but_body_lt_75': int((event_ok & range_ok & ~body_ok).sum()),
        'selector_match_rows': int(all_ok.sum()),
    }
    partial = {
        'current_rows': int(len(enriched)),
        'raw_feature_covered_rows': int(enriched['raw_event_body_pct'].notna().sum()),
        'event_type': safe_value_counts(enriched, 'event_type'),
        'market_state': safe_value_counts(enriched, 'market_state'),
        'poi_source': safe_value_counts(enriched, 'poi_source'),
        'v132_reclaim_class': safe_value_counts(enriched, 'v132_reclaim_class'),
        'fail_reasons': fail_reasons,
        'matched_rows': enriched.loc[all_ok, ['symbol', 'entry_date', 'event_type', 'market_state', 'poi_source', 'raw_prev20_range_pct', 'raw_event_body_pct']].to_dict('records'),
    }
    enriched.to_csv(OUT / 'v261_current_rows_with_raw_features.csv', index=False)
    return partial


def frontier_current_hit_audit(frontier: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for min_hit in (1, 2, 5, 10, 20):
        s = frontier[frontier['current_recent45_hits'] >= min_hit].copy()
        if s.empty:
            out[str(min_hit)] = {'rules': 0}
            continue
        ranked = s.sort_values(
            ['combined_prod_pass', 'combined_research_pass', 'combined_wr', 'combined_avg', 'current_recent45_hits'],
            ascending=[False, False, False, False, False],
        )
        cols = [
            'event_filter', 'rule', 'current_recent45_hits', 'child_n', 'child_wr', 'child_avg',
            'combined_n', 'combined_wr', 'combined_avg', 'combined_min_year_n',
            'combined_all_year_wr_min', 'combined_weak_month_count', 'combined_micro',
            'combined_prod_pass', 'combined_research_pass',
        ]
        out[str(min_hit)] = {
            'rules': int(len(s)),
            'production_pass_count': int(s['combined_prod_pass'].fillna(False).astype(bool).sum()),
            'research_pass_count': int(s['combined_research_pass'].fillna(False).astype(bool).sum()),
            'best': ranked[cols].head(8).to_dict('records'),
        }
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cur = pd.read_csv(V258_CURRENT, low_memory=False)
    frontier = pd.read_csv(V259_FRONTIER, low_memory=False)
    v260 = json.loads(V260_SUMMARY.read_text())

    mismatch = current_selector_mismatch(cur)
    hit_audit = frontier_current_hit_audit(frontier)

    decision = 'NO_PROMOTION__CURRENT_COMPATIBLE_RULES_WITH_REAL_CURRENT_HITS_DO_NOT_PASS_PRODUCTION'
    if v260.get('production_gate_pass') and v260.get('current_actionable_rows') == 0:
        decision += '__V259_HISTORICAL_PASS_IS_SHADOW_ONLY'

    summary = {
        'version': 'V261_CURRENT_SUPPLY_MISMATCH_CLOSURE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'out_dir': str(OUT),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'inputs': {
            'v258_current': str(V258_CURRENT),
            'v259_frontier': str(V259_FRONTIER),
            'v260_summary': str(V260_SUMMARY),
        },
        'v260_gate': {
            'historical_production_gate_pass': bool(v260.get('production_gate_pass')),
            'current_recent45_hits': int(v260.get('current_recent45_hits', -1)),
            'current_actionable_rows': int(v260.get('current_actionable_rows', -1)),
            'decision': v260.get('current_decision'),
        },
        'v259_prod_selector_current_mismatch': mismatch,
        'current_hit_frontier_audit': hit_audit,
        'decision': decision,
        'next_research_direction': [
            'Stop promoting V259/V260 despite historical pass: current rows are zero.',
            'Stop mining current SSL/MIXED/BEAR rows with existing scalar fields as production supply: rules with >=5 current hits have zero research/production pass.',
            'Next valid shadow direction is a genuinely new source layer that can create BULL_CONTINUATION or equivalent strong-trend current rows, not a post-filter over V128/V230 current rows.',
        ],
    }
    (OUT / 'v261_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
