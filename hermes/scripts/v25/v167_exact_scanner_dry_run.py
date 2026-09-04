#!/usr/bin/env python3
"""V167: exact scanner-time dry-run for the V166 production-usable slice.

Read-only. No production/frontend/watchlist writes.

Rule discovered in V166:
- market_state == BEAR_RISK
- poi_source == DEMAND_OB
- v132_reclaim_class == TRUE_TAKEOVER_3_STRICT
- v132_reclaim_bull_body_pct <= 65
Execution contract for backtest evaluation only:
- TP = 1.5R, max_hold = 10 bars, SL = zone_low - 1.0% buffer

This script validates whether the rule is implementable from V164 scanner-time
fields, produces current/recent dry-run BUY rows, and keeps all writes in audit
folder only.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
IN = ROOT / 'smc_audit' / 'v164_corrected_scanner_dry_run_20260622' / 'v164_dryrun_rows.json'
V166_ROWS = ROOT / 'smc_audit' / 'v166_v164_slice_variant_search_20260623' / 'v166_best_production_slice_rows.csv'
OUT = ROOT / 'smc_audit' / 'v167_exact_scanner_dry_run_20260623'
OUT.mkdir(parents=True, exist_ok=True)
ENGINE = 'V167_EXACT_SCANNER_DRY_RUN'
REQUIRED_FIELDS = [
    'symbol', 'entry_date', 'entry_price', 'zone_low', 'zone_high', 'risk_pct',
    'market_state', 'poi_source', 'v132_reclaim_class', 'v132_reclaim_bull_body_pct',
    'v161_outcome_field_leak', 'v161_decision_available', 'v164_rule_pass',
]
RULE_TEXT = "market_state==BEAR_RISK AND poi_source==DEMAND_OB AND v132_reclaim_class==TRUE_TAKEOVER_3_STRICT AND v132_reclaim_bull_body_pct<=65"


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return default
        if isinstance(v, str) and not v.strip():
            return default
        return float(v)
    except Exception:
        return default


def bval(v: Any) -> bool:
    return str(v).strip().lower() in {'true', '1', 'yes'}


def rule_pass(r: dict[str, Any]) -> bool:
    return (
        str(r.get('market_state')) == 'BEAR_RISK'
        and str(r.get('poi_source')) == 'DEMAND_OB'
        and str(r.get('v132_reclaim_class')) == 'TRUE_TAKEOVER_3_STRICT'
        and fnum(r.get('v132_reclaim_bull_body_pct'), 999) <= 65.0
        and bval(r.get('v164_rule_pass'))
        and not bval(r.get('v161_outcome_field_leak'))
        and bval(r.get('v161_decision_available'))
    )


def missing_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    out = {}
    for k in REQUIRED_FIELDS:
        c = 0
        for r in rows:
            v = r.get(k)
            if v is None or str(v) == '' or (k in {'entry_price', 'zone_low', 'zone_high'} and fnum(v) <= 0):
                c += 1
        out[k] = c
    return out


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text('', encoding='utf-8'); return
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader(); w.writerows(rows)


def read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def main() -> None:
    rows = json.loads(IN.read_text(encoding='utf-8'))
    missing = missing_counts(rows)
    buys = []
    watches = []
    for r in rows:
        out = dict(r)
        out['v167_engine'] = ENGINE
        out['v167_rule'] = RULE_TEXT
        out['v167_tp_r'] = 1.5
        out['v167_max_hold_bars'] = 10
        out['v167_sl_buffer_pct'] = 1.0
        out['production_write'] = False
        out['frontend_write'] = False
        out['watchlist_write'] = False
        if rule_pass(r):
            out['v167_dry_action'] = 'BUY'
            out['v167_dry_reason'] = 'V167_RULE_PASS'
            buys.append(out)
        else:
            out['v167_dry_action'] = 'WATCH_ONLY'
            if bval(r.get('v161_outcome_field_leak')):
                reason = 'OUTCOME_LEAK'
            elif not bval(r.get('v161_decision_available')):
                reason = 'DECISION_NOT_AVAILABLE'
            elif not bval(r.get('v164_rule_pass')):
                reason = 'V164_BASE_RULE_FAIL'
            else:
                reason = 'V167_RULE_FAIL'
            out['v167_dry_reason'] = reason
            watches.append(out)

    recent = [r for r in rows if str(r.get('entry_date')) >= '20260509']
    recent_buys = [r for r in buys if str(r.get('entry_date')) >= '20260509']
    latest_date = max((str(r.get('entry_date')) for r in buys), default='')
    latest_buys = [r for r in buys if str(r.get('entry_date')) == latest_date]
    year_counts = Counter(str(r.get('entry_date'))[:4] for r in buys)
    recent_year_counts = Counter(str(r.get('entry_date'))[:4] for r in recent_buys)

    v166_best = read_csv(V166_ROWS)
    v166_key_rows = [r for r in v166_best if str(r.get('entry_date'))[:4] >= '2023']
    # Compare scanner application count with V166 best rows. V166 was entry_year>=2023;
    # V167 includes full scanner history, so compare 2023+ subset.
    v167_2023p = [r for r in buys if str(r.get('entry_date'))[:4] >= '2023']

    slim_cols = ['symbol','entry_date','entry_price','zone_low','zone_high','risk_pct','market_state','poi_source','combo_family','event_type','v132_reclaim_class','v132_reclaim_bull_body_pct','v132_reclaim_close_above_zone_high_pct','entry_chase_above_zone_pct','v167_dry_action','v167_dry_reason','production_write','frontend_write','watchlist_write']
    write_csv(OUT / 'v167_buy_rows.csv', [{k: r.get(k) for k in slim_cols} for r in buys])
    write_csv(OUT / 'v167_recent45_buy_rows.csv', [{k: r.get(k) for k in slim_cols} for r in recent_buys])
    write_csv(OUT / 'v167_latest_buy_rows.csv', [{k: r.get(k) for k in slim_cols} for r in latest_buys])
    write_csv(OUT / 'v167_watch_rows_sample.csv', [{k: r.get(k) for k in slim_cols} for r in watches[:1000]])

    buy_missing = missing_counts(buys)
    # Source-level missing body rows are allowed only when they are safely routed
    # WATCH_ONLY; BUY rows must have every decision field complete.
    gates = {
        'buy_required_fields_complete': all(v == 0 for v in buy_missing.values()),
        'missing_decision_field_rows_are_not_buy': all(not rule_pass(r) for r in rows if any((r.get(k) is None or str(r.get(k)) == '') for k in REQUIRED_FIELDS)),
        'outcome_leak_buy_rows_zero': sum(1 for r in buys if bval(r.get('v161_outcome_field_leak'))) == 0,
        'decision_unavailable_buy_rows_zero': sum(1 for r in buys if not bval(r.get('v161_decision_available'))) == 0,
        'base_v164_fail_buy_rows_zero': sum(1 for r in buys if not bval(r.get('v164_rule_pass'))) == 0,
        'production_write_false': True,
        'frontend_write_false': True,
        'watchlist_write_false': True,
        'v166_count_match_2023_plus': len(v167_2023p) == len(v166_key_rows),
    }
    decision = 'V167_DRYRUN_PASS__PROMOTION_GATE_NEXT' if all(gates.values()) else 'V167_DRYRUN_FAIL__DO_NOT_PROMOTE'
    summary = {
        'decision': decision,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'engine': ENGINE,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'rule': RULE_TEXT,
        'execution_contract': {'tp_r': 1.5, 'max_hold_bars': 10, 'sl_buffer_pct': 1.0, 't1_exit_start': 'entry_idx+1'},
        'source_rows': len(rows),
        'buy_rows': len(buys),
        'buy_rows_2023_plus': len(v167_2023p),
        'v166_best_rows_2023_plus': len(v166_key_rows),
        'watch_rows': len(watches),
        'recent45_rows': len(recent),
        'recent45_buy_rows': len(recent_buys),
        'latest_buy_date': latest_date,
        'latest_buy_rows': len(latest_buys),
        'year_counts': dict(sorted(year_counts.items())),
        'recent_year_counts': dict(sorted(recent_year_counts.items())),
        'missing_required_fields': missing,
        'missing_required_fields_in_buy_rows': buy_missing,
        'gates': gates,
        'next_required': 'Run endpoint/frontend dry-run mapping and production-source isolation only if this dry-run passes; still no production write until promotion bundle + browser/API smoke pass.',
        'artifacts': {
            'buy_rows': str(OUT / 'v167_buy_rows.csv'),
            'recent45_buy_rows': str(OUT / 'v167_recent45_buy_rows.csv'),
            'latest_buy_rows': str(OUT / 'v167_latest_buy_rows.csv'),
            'watch_sample': str(OUT / 'v167_watch_rows_sample.csv'),
        },
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    (OUT / 'report.md').write_text('# V167 exact scanner dry-run\n\n```json\n' + json.dumps(summary, ensure_ascii=False, indent=2, default=str) + '\n```\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
