#!/usr/bin/env python3
"""V562 no-write integrity audit for V300/V301 research rows.

Purpose: establish whether earlier large-N 60m diffusion claims represent unique,
executable candidate identities or repeated parameterized rows from the upstream
V299 grid.  This is an audit only: it does not create, select, or promote a
strategy.  The one displayed V300 rule is reconstructed from its published
pre-entry fields; outcomes are read only after the row set is frozen.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

BASE = Path('/root/.hermes')
AUDIT = BASE / 'smc_audit'
SOURCE = AUDIT / 'v300_entry60_volume_diffusion_no_write_20260703_142439/v300_enriched_rows.csv'
LATEST = AUDIT / 'v562_v300_candidate_identity_audit_latest.json'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v562_v300_candidate_identity_audit_no_write_{TS}'

# This is the published V300 high-WR, 2026-only configuration.  All fields are
# available at the first-60m decision; none is an exit/outcome field.
RULE_FIELDS = {
    'confirm_k', 'mkt_up', 'ind_up', 'mkt_up_vol', 'ind_up_vol',
    'stock60_vol_ratio', 'stock60_ret',
}
OUTCOME_FIELDS = {'exit_date', 'exit', 'reason', 'pnl', 'hold'}


def f(x: Any, default: float = math.nan) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def is_v300_published_rule(r: dict[str, str]) -> bool:
    return (
        int(f(r.get('confirm_k'), 0)) == 1
        and f(r.get('mkt_up')) >= 50
        and f(r.get('ind_up')) >= 50
        and f(r.get('mkt_up_vol')) >= 35
        and f(r.get('ind_up_vol')) >= 20
        and f(r.get('stock60_vol_ratio')) >= 1.3
        and f(r.get('stock60_ret')) >= 0
    )


def raw_metrics(rows: list[dict[str, str]]) -> dict[str, Any]:
    n = len(rows)
    pnls = [f(r.get('pnl')) for r in rows]
    good = [p for p in pnls if not math.isnan(p)]
    wins = [p for p in good if p > 0]
    losses = [p for p in good if p <= 0]
    pos_sum, neg_sum = sum(wins), sum(losses)
    months: dict[str, list[float]] = defaultdict(list)
    years: dict[str, list[float]] = defaultdict(list)
    for r, p in zip(rows, pnls):
        if math.isnan(p):
            continue
        d = str(r.get('entry_date') or '')
        months[d[:6]].append(p)
        years[d[:4]].append(p)
    def stat(vals: list[float]) -> dict[str, float | int]:
        w = [v for v in vals if v > 0]
        l = [v for v in vals if v <= 0]
        return {
            'n': len(vals),
            'wr_pct': round(100 * len(w) / len(vals), 4) if vals else 0.0,
            'avg_net_pct': round(sum(vals) / len(vals), 4) if vals else 0.0,
            'pf': round(sum(w) / abs(sum(l)), 4) if sum(l) else None,
        }
    return {
        'n': n,
        'symbols': len({r.get('symbol') for r in rows}),
        'wr_pct': round(100 * len(wins) / len(good), 4) if good else 0.0,
        'avg_net_pct': round(sum(good) / len(good), 4) if good else 0.0,
        'profit_factor': round(pos_sum / abs(neg_sum), 4) if neg_sum else None,
        'payoff': round((pos_sum / len(wins)) / abs(neg_sum / len(losses)), 4) if wins and losses else None,
        't1_violations': sum(str(r.get('t1_violation')).lower() == 'true' or str(r.get('exit_date') or '') <= str(r.get('entry_date') or '') for r in rows),
        'yearly': {k: stat(v) for k, v in sorted(years.items())},
        'monthly': {k: stat(v) for k, v in sorted(months.items())},
    }


def dedupe(rows: list[dict[str, str]], key: Callable[[dict[str, str]], tuple], chooser: Callable[[dict[str, str]], tuple]) -> list[dict[str, str]]:
    groups: dict[tuple, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        groups[key(r)].append(r)
    return [min(v, key=chooser) for _, v in sorted(groups.items())]


def summarize_scope(name: str, rows: list[dict[str, str]]) -> dict[str, Any]:
    execution_key = lambda r: (r['symbol'], r['signal_date'], r['entry_date'], r['confirm_k'], r['entry'], r['sl'])
    event_k_key = lambda r: (r['symbol'], r['signal_date'], r['entry_date'], r['confirm_k'])
    event_key = lambda r: (r['symbol'], r['signal_date'], r['entry_date'])
    # Deterministic, pre-entry-only tie-break.  This is an integrity lower-bound
    # diagnostic, never a strategy selector or an outcome-based optimization.
    choose = lambda r: (
        f(r.get('risk_after_confirm'), 1e9), f(r.get('entry'), 1e9),
        int(f(r.get('acc_len'), 1e9)), int(f(r.get('hold_req'), 1e9)),
        int(f(r.get('man_wait'), 1e9)), int(f(r.get('reclaim_delay'), 1e9)),
        int(f(r.get('takeover_delay'), 1e9)),
    )
    exact = dedupe(rows, execution_key, choose)
    per_k = dedupe(rows, event_k_key, choose)
    per_event = dedupe(rows, event_key, choose)
    event_counts = Counter(event_key(r) for r in rows)
    exec_counts = Counter(execution_key(r) for r in rows)
    return {
        'scope': name,
        'raw_rows': raw_metrics(rows),
        'exact_execution_identity': raw_metrics(exact),
        'one_row_per_event_and_confirm_k_diagnostic': raw_metrics(per_k),
        'one_row_per_event_diagnostic': raw_metrics(per_event),
        'duplication': {
            'raw_rows': len(rows),
            'unique_execution_identities': len(exact),
            'unique_event_confirm_identities': len(per_k),
            'unique_event_identities': len(per_event),
            'rows_per_execution_identity': round(len(rows) / len(exact), 4) if exact else None,
            'rows_per_event_confirm_identity': round(len(rows) / len(per_k), 4) if per_k else None,
            'rows_per_event_identity': round(len(rows) / len(per_event), 4) if per_event else None,
            'max_rows_one_event': max(event_counts.values(), default=0),
            'max_rows_one_execution_identity': max(exec_counts.values(), default=0),
            'events_with_multiple_rows_pct': round(100 * sum(v > 1 for v in event_counts.values()) / len(event_counts), 4) if event_counts else 0.0,
        },
    }


def main() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError(SOURCE)
    with SOURCE.open(newline='') as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise RuntimeError('empty V300 source')
    present = set(rows[0])
    if not RULE_FIELDS <= present:
        raise RuntimeError(f'missing published rule fields: {sorted(RULE_FIELDS-present)}')
    if not OUTCOME_FIELDS <= present:
        raise RuntimeError(f'missing outcome audit fields: {sorted(OUTCOME_FIELDS-present)}')
    frozen = [r for r in rows if is_v300_published_rule(r)]
    report = {
        'version': 'V562_V300_CANDIDATE_IDENTITY_AUDIT_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'purpose': 'Separate source-grid row count from unique executable candidate identities before any reuse of V300/V301 evidence.',
        'writes': {'production': False, 'frontend': False, 'watchlist': False, 'positions': False},
        'source': str(SOURCE),
        'published_rule_contract': {
            'name': 'V300 k1_mup50_iup50_muv35_iuv20_svol1.3_sret0.0_raw',
            'fields': sorted(RULE_FIELDS),
            'rule': 'confirm_k==1; mkt_up>=50; ind_up>=50; mkt_up_vol>=35; ind_up_vol>=20; stock60_vol_ratio>=1.3; stock60_ret>=0',
            'outcome_fields_used_for_selection': False,
        },
        'scopes': {
            'all_v300_executable_rows': summarize_scope('all_v300_executable_rows', rows),
            'published_rule_rows': summarize_scope('published_rule_rows', frozen),
        },
        'invariants': {
            'source_fields_present': True,
            'production_write': False,
            'frontend_write': False,
            'watchlist_write': False,
            'selection_field_outcome_intersection': sorted(RULE_FIELDS & OUTCOME_FIELDS),
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / 'v562_report.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({
        'status': 'PASS', 'latest': str(LATEST),
        'all_raw': report['scopes']['all_v300_executable_rows']['raw_rows']['n'],
        'all_unique_event': report['scopes']['all_v300_executable_rows']['duplication']['unique_event_identities'],
        'rule_raw': report['scopes']['published_rule_rows']['raw_rows']['n'],
        'rule_unique_event': report['scopes']['published_rule_rows']['duplication']['unique_event_identities'],
        'rule_unique_event_metrics': report['scopes']['published_rule_rows']['one_row_per_event_diagnostic'],
        't1': report['scopes']['published_rule_rows']['one_row_per_event_diagnostic']['t1_violations'],
    }, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
