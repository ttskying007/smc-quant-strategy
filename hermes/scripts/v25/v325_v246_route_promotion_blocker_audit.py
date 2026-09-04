#!/usr/bin/env python3
"""V325 no-write: V246 route promotion blocker audit.

V246/V248 is historically stronger than V185, but previous current-shadow scripts
mixed several historical source routes and a stale strict parent rule. This audit
separates:
1) exact historical V246 selected quality;
2) source lineage buckets and which buckets are current-scanner reproducible;
3) current-script strict parent mismatch against the historical selected rows;
4) latest current direct-row availability from V322/V323.

No production/frontend/watchlist writes.
"""
from __future__ import annotations

import json, math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
SRC = AUD / 'v244_post_v243_industry_participation_probe_no_write_20260701_151619/v244_best_rows.csv'
V248 = AUD / 'v248_v246_independent_audit_latest.json'
V322 = AUD / 'v322_current_scanner_contract_recompute_latest.json'
V323 = AUD / 'v323_v322_direct_current_shadow_latest.json'
OUT = AUD / f"v325_v246_route_promotion_blocker_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
LATEST = AUD / 'v325_v246_route_promotion_blocker_latest.json'

PROD = {'n': 570, 'min_year_n': 70, 'wr': 93.0, 'avg': 7.6, 'all_year_wr_min': 91.0, 'micro': 1.0, 't1': 0}
WEAK_INDUSTRIES = {'C27医药制造业', 'C32有色金属冶炼和压延加工业'}


def dn(x: Any) -> str:
    s = ''.join(ch for ch in str(x or '').replace('-', '')[:10] if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def sf(x: Any, default: float | None = None) -> float | None:
    try:
        if x is None or x == '':
            return default
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def metrics(df: pd.DataFrame) -> dict[str, Any]:
    if len(df) == 0:
        return {'n': 0, 'wr': 0, 'avg': 0, 'median': 0, 'min_year_n': 0, 'year_counts': {}, 'year_wr': {}, 'all_year_wr_min': 0, 'micro_profit_pct': 0, 'loss_n': 0, 't1': 0}
    pnl = pd.to_numeric(df['pnl_pct'], errors='coerce')
    yrs = df['entry_date'].astype(str).str[:4]
    yc = yrs.value_counts().sort_index().to_dict()
    ywr = {str(y): round(float((pnl[yrs == y] > 0).mean() * 100), 2) for y in sorted(yrs.dropna().unique())}
    t1 = 0
    if 'exit_date' in df.columns:
        t1 = int(((df['exit_date'].map(dn) == df['entry_date'].map(dn)) & df['exit_date'].map(dn).ne('')).sum())
    return {
        'n': int(len(df)),
        'wr': round(float((pnl > 0).mean() * 100), 4),
        'avg': round(float(pnl.mean()), 4),
        'median': round(float(pnl.median()), 4),
        'min_year_n': int(min(yc.values()) if yc else 0),
        'year_counts': {str(k): int(v) for k, v in yc.items()},
        'year_wr': ywr,
        'all_year_wr_min': round(float(min(ywr.values()) if ywr else 0), 2),
        'micro_profit_pct': round(float(((pnl > 0) & (pnl < 1)).mean() * 100), 4),
        'loss_n': int((pnl <= 0).sum()),
        't1': t1,
    }


def pass_gate(m: dict[str, Any], g: dict[str, Any] = PROD) -> bool:
    return (
        m['n'] >= g['n'] and m['min_year_n'] >= g['min_year_n']
        and m['wr'] >= g['wr'] and m['avg'] >= g['avg']
        and m['all_year_wr_min'] >= g['all_year_wr_min']
        and m['micro_profit_pct'] <= g['micro'] and m['t1'] == g['t1']
    )


def current_strict_parent_equivalent(r: dict[str, Any]) -> bool:
    # Mirrors v246_daily_current_shadow_audit.parent_rule_pass as of this audit.
    return (
        str(r.get('market_state')) in ('ACCUMULATION', 'BEAR_RISK')
        and str(r.get('event_type')) == 'SSL_SWEEP_CHOCH_REVERSAL'
        and str(r.get('poi_source')) in ('DEMAND_OB', 'OB+FVG')
        and sf(r.get('v132_bull_count_3'), -1) >= 3
        and sf(r.get('v132_post_zone_pullback_depth_pct_3'), 999) <= 40
        and 10 <= sf(r.get('v236_all_strong1_pct'), 999) <= 55
        and 35 <= sf(r.get('v236_br_above_ma20'), -999) <= 70
        and sf(r.get('entry_chase_above_zone_pct'), 999) <= 2.5
        and sf(r.get('v244_ind_up1_pct'), 999) <= 80
    )


def load_json(p: Path, default: Any) -> Any:
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    raw = pd.read_csv(SRC, low_memory=False)
    raw['entry_date'] = raw['entry_date'].map(dn)
    raw['exit_date'] = raw['exit_date'].map(dn)

    weak = raw['v244_industry'].astype(str).isin(WEAK_INDUSTRIES)
    addback = (pd.to_numeric(raw['v244_ind_strong1_pct'], errors='coerce') >= 31.1688) | (pd.to_numeric(raw['v236_br_above_ma20'], errors='coerce') >= 46.8561)
    selected = raw[(~weak) | (weak & addback)].copy()
    selected['v325_current_strict_parent_pass'] = [current_strict_parent_equivalent(r) for r in selected.to_dict('records')]
    selected['v325_lineage'] = selected['engine'].fillna('NA').astype(str) + '|' + selected['event_type'].fillna('NA').astype(str) + '|' + selected['v228_source_bucket'].fillna('NA').astype(str)

    lineage_rows = []
    for k, g in selected.groupby('v325_lineage', dropna=False):
        if len(g) >= 5:
            lineage_rows.append({'lineage': k, **metrics(g), 'strict_parent_pass_rows': int(g['v325_current_strict_parent_pass'].sum())})
    lineage_rows = sorted(lineage_rows, key=lambda x: (x['n'], x['wr'], x['avg']), reverse=True)

    source_buckets = []
    for col in ['engine', 'event_type', 'v228_source_bucket', 'v185_source', 'v164_rule_pass']:
        if col not in selected.columns:
            continue
        for val, g in selected.groupby(selected[col].fillna('NA').astype(str), dropna=False):
            if len(g) >= 5:
                source_buckets.append({'field': col, 'value': val, **metrics(g), 'strict_parent_pass_rows': int(g['v325_current_strict_parent_pass'].sum())})
    source_buckets = sorted(source_buckets, key=lambda x: (x['field'], -x['n']))

    v164_hist = selected[selected.get('v164_rule_pass', pd.Series(index=selected.index)).astype(str) == 'True'].copy()
    non_v164_hist = selected[selected.get('v164_rule_pass', pd.Series(index=selected.index)).astype(str) != 'True'].copy()
    strict_parent_hist = selected[selected['v325_current_strict_parent_pass']].copy()

    v248 = load_json(V248, {})
    v322 = load_json(V322, {})
    v323 = load_json(V323, {})
    v322_counts = v322.get('contract_counts', {})
    v323_rows = v323.get('rows', [])

    selected.to_csv(OUT / 'v325_selected_with_route_flags.csv', index=False)
    pd.DataFrame(lineage_rows).to_csv(OUT / 'v325_lineage_metrics.csv', index=False)
    pd.DataFrame(source_buckets).to_csv(OUT / 'v325_source_bucket_metrics.csv', index=False)

    strict_m = metrics(strict_parent_hist)
    selected_m = metrics(selected)
    v164_m = metrics(v164_hist)
    non_v164_m = metrics(non_v164_hist)

    hard_facts = {
        'historical_v246_selected_pass': pass_gate(selected_m),
        'historical_v246_selected': selected_m,
        'current_strict_parent_covers_selected_rows': int(selected['v325_current_strict_parent_pass'].sum()),
        'current_strict_parent_coverage_pct': round(float(selected['v325_current_strict_parent_pass'].mean() * 100), 4),
        'strict_parent_historical_metrics': strict_m,
        'v164_reproducible_subset_metrics': v164_m,
        'non_v164_child_subset_metrics': non_v164_m,
        'v322_current_contract_counts': v322_counts,
        'v323_shadow_rows': len(v323_rows),
    }

    blockers = []
    if hard_facts['current_strict_parent_coverage_pct'] < 80:
        blockers.append('current_v246_parent_rule_does_not_reconstruct_historical_v246_route')
    if not pass_gate(v164_m):
        blockers.append('v164_reproducible_subset_alone_below_v246_production_gate')
    if len(v323_rows) < 5:
        blockers.append('latest_current_shadow_rows_too_few_for_endpoint_promotion')
    direct = v322_counts.get('direct_v164_plus_v246_industry', {})
    if direct.get('nonoverlap_actionable10_rows', 0) < 5:
        blockers.append('latest_current_nonoverlap_actionable_rows_below_minimum')

    recommendation = {
        'do_not_promote_v246_as_production_default_now': True,
        'reason': blockers,
        'next_valid_direction': 'Build exact current generators for each V246 lineage (V161/V211/V185_CHILD) or close V246 promotion; do not keep using the stale single strict parent rule as proof of no current supply.',
        'safe_current_action': 'keep V185 production; V246 remains historical research/shadow only until current lineage generators are validated.',
    }

    report = {
        'version': 'V325_V246_ROUTE_PROMOTION_BLOCKER_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'sources': {'v244_best': str(SRC), 'v248': str(V248), 'v322': str(V322), 'v323': str(V323)},
        'production_gate': PROD,
        'v248_decision': v248.get('decision'),
        'hard_facts': hard_facts,
        'lineage_top': lineage_rows[:20],
        'source_bucket_top': source_buckets[:80],
        'blockers': blockers,
        'recommendation': recommendation,
        'decision': 'V325_V246_PROMOTION_BLOCKED__CURRENT_LINEAGE_GENERATORS_REQUIRED',
        'artifacts': {
            'report': str(OUT / 'v325_report.json'),
            'selected_flags': str(OUT / 'v325_selected_with_route_flags.csv'),
            'lineage_metrics': str(OUT / 'v325_lineage_metrics.csv'),
            'source_bucket_metrics': str(OUT / 'v325_source_bucket_metrics.csv'),
            'latest': str(LATEST),
        },
    }
    json.dump(report, open(OUT / 'v325_report.json', 'w'), ensure_ascii=False, indent=2)
    json.dump(report, open(LATEST, 'w'), ensure_ascii=False, indent=2)
    print(json.dumps({
        'latest': str(LATEST),
        'decision': report['decision'],
        'hard_facts': hard_facts,
        'blockers': blockers,
        'top_lineage': lineage_rows[:5],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
