#!/usr/bin/env python3
"""V231 daily current shadow audit (no production/frontend/watchlist writes).

Purpose:
- Keep V231 as a monitored shadow candidate after V185 production baseline.
- Re-evaluate current V164 scanner rows with the V231 non-leaking rule.
- Emit only non-expired, non-overlap actionable rows for later endpoint mapping smoke.

This script intentionally never writes production/watchlist/frontend artifacts.
"""
from __future__ import annotations

import bisect
import glob
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

BASE = Path('/root/.hermes')
KDIR = BASE / 'kline_cache'
AUDIT = BASE / 'smc_audit'
ACTIVE = BASE / 'smc_opt_v185_combined_production_candidate/v185_active_picks.json'
V185_TRADES = BASE / 'smc_opt_v185_combined_production_candidate/v185_trades.json'

RULE_VERSION = 'V231_DAILY_CURRENT_SHADOW_AUDIT'
MAX_ACTIONABLE_BARS = 10


def sf(x: Any, default: float | None = None) -> float | None:
    try:
        if x is None or x == '':
            return default
        if isinstance(x, float) and math.isnan(x):
            return default
        return float(x)
    except Exception:
        return default


def dn(x: Any) -> str:
    if x is None:
        return ''
    s = ''.join(ch for ch in str(x).replace('-', '')[:10] if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def row_key(r: dict[str, Any]) -> tuple[str, str]:
    return str(r.get('symbol') or ''), dn(r.get('entry_date') or r.get('pick_date'))


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def latest_path(pattern: str) -> Path | None:
    paths = [Path(p) for p in glob.glob(pattern)]
    paths = [p for p in paths if p.exists()]
    if not paths:
        return None
    return max(paths, key=lambda p: p.stat().st_mtime)


def latest_v164_dryrun() -> Path:
    p = latest_path(str(AUDIT / 'v164_corrected_scanner_dry_run_*' / 'v164_dryrun_rows.json'))
    if p is None:
        raise FileNotFoundError('missing latest v164_dryrun_rows.json')
    return p


def latest_v231_combined_csv() -> Path | None:
    return latest_path(str(AUDIT / 'v231_v230_candidate_independent_audit_no_write_*' / 'v231_combined_rows.csv'))


def sym_from_file(path: str) -> str | None:
    parts = Path(path).name.split('_')
    if len(parts) >= 2 and parts[0].isdigit():
        return parts[0] + '.' + parts[1]
    return None


def build_all_market_strong1() -> tuple[dict[str, float], list[str]]:
    rows_by_date: dict[str, list[float]] = defaultdict(list)
    for fp in glob.glob(str(KDIR / '*_daily_750.json')):
        if not sym_from_file(fp):
            continue
        try:
            data = json.loads(Path(fp).read_text())
        except Exception:
            continue
        bars: list[tuple[str, float]] = []
        for b in data:
            d = dn(b.get('t') or b.get('date'))
            c = sf(b.get('c'))
            if d and c:
                bars.append((d, float(c)))
        bars.sort()
        if len(bars) < 22:
            continue
        closes = [x[1] for x in bars]
        for i, (d, c) in enumerate(bars):
            if i < 20:
                continue
            prev_c = closes[i - 1]
            if prev_c:
                rows_by_date[d].append((c / prev_c - 1.0) * 100.0)
    all_strong = {d: sum(x > 3.0 for x in vals) / len(vals) * 100.0 for d, vals in rows_by_date.items() if vals}
    return all_strong, sorted(all_strong)


def previous_market_date(dates: list[str], entry_date: str) -> str:
    i = bisect.bisect_left(dates, entry_date) - 1
    return dates[i] if i >= 0 else ''


def load_history_keys() -> dict[str, set[tuple[str, str]]]:
    keys: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for r in load_json(V185_TRADES, []):
        keys['v185_trades'].add(row_key(r))
    for r in load_json(ACTIVE, []):
        keys['v185_active'].add(row_key(r))
    v231_csv = latest_v231_combined_csv()
    if v231_csv:
        for r in pd.read_csv(v231_csv, low_memory=False).to_dict('records'):
            keys['v231_combined_history'].add(row_key(r))
    return keys


def selector_leak_fields(fields: list[str]) -> list[str]:
    bad_tokens = ['pnl', 'exit_', 'won', 'mae', 'mfe', 'hold_bars', 'hit', 'rr_realized', 'base_', 'v211_pnl']
    return [f for f in fields if any(tok in f.lower() for tok in bad_tokens)]


def main() -> None:
    dry_path = latest_v164_dryrun()
    dry = load_json(dry_path, [])
    all_strong, dates = build_all_market_strong1()
    history = load_history_keys()
    out = AUDIT / ('v231_daily_current_shadow_audit_no_write_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    out.mkdir(parents=True, exist_ok=True)

    selector_fields = [
        'market_state',
        'v132_bull_count_3',
        'v132_post_zone_pullback_depth_pct_3',
        'v231_prev_market_date',
        'v231_all_strong1_pct',
        'poi_source',
        'event_type',
        'risk_pct',
        'entry_chase_above_zone_pct',
        'bars_since_entry',
    ]
    leak = selector_leak_fields(selector_fields)

    raw: list[dict[str, Any]] = []
    for r in dry:
        if not r.get('v161_recent45'):
            continue
        ed = dn(r.get('entry_date'))
        if not ed:
            continue
        prev_d = previous_market_date(dates, ed)
        rr = dict(r)
        rr['entry_date'] = ed
        rr['v231_prev_market_date'] = prev_d
        rr['v231_all_strong1_pct'] = all_strong.get(prev_d)
        rr['v231_daily_shadow_rule_pass'] = (
            str(r.get('market_state')) == 'ACCUMULATION'
            and sf(r.get('v132_bull_count_3'), -1) >= 3
            and sf(r.get('v132_post_zone_pullback_depth_pct_3'), 999) <= 5
            and sf(rr.get('v231_all_strong1_pct'), 999) <= 42
        )
        if rr['v231_daily_shadow_rule_pass']:
            raw.append(rr)

    pri_poi = {'DEMAND_OB': 0, 'OB+FVG': 1, 'FVG_Demand': 2}
    pri_event = {'SSL_SWEEP_CHOCH_REVERSAL': 0, 'BOS_CONTINUATION': 1}
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in raw:
        groups[row_key(r)].append(r)

    dedup: list[dict[str, Any]] = []
    duplicate_keys: list[dict[str, Any]] = []
    for k, arr in groups.items():
        if len(arr) > 1:
            duplicate_keys.append({'symbol': k[0], 'entry_date': k[1], 'raw_count': len(arr)})
        arr = sorted(
            arr,
            key=lambda r: (
                pri_poi.get(str(r.get('poi_source')), 9),
                pri_event.get(str(r.get('event_type')), 9),
                sf(r.get('risk_pct'), 999),
                sf(r.get('entry_chase_above_zone_pct'), 999),
            ),
        )
        best = dict(arr[0])
        k2 = row_key(best)
        best['overlap_v185_trades'] = k2 in history['v185_trades']
        best['overlap_v185_active'] = k2 in history['v185_active']
        best['overlap_v231_combined_history'] = k2 in history['v231_combined_history']
        best['actionable_by_maxhold10'] = sf(best.get('bars_since_entry'), 999) <= MAX_ACTIONABLE_BARS
        best['time_order_bad'] = bool(dn(best.get('v231_prev_market_date')) and dn(best.get('v231_prev_market_date')) >= dn(best.get('entry_date')))
        dedup.append(best)

    actionable = [
        r for r in dedup
        if r['actionable_by_maxhold10']
        and not r['overlap_v185_trades']
        and not r['overlap_v185_active']
        and not r['overlap_v231_combined_history']
        and not r['time_order_bad']
    ]
    expired = [r for r in dedup if not r['actionable_by_maxhold10']]
    overlap = [r for r in dedup if r['overlap_v185_trades'] or r['overlap_v185_active'] or r['overlap_v231_combined_history']]
    time_bad = [r for r in dedup if r['time_order_bad']]
    active_pollution = [r for r in actionable if any(str(r.get(f) or '') for f in ('exit_date', 'exit_reason', 'pnl_pct', 'won', 'base_exit_reason', 'base_pnl_pct'))]

    pd.DataFrame(dedup).to_csv(out / 'v231_current_rule_dedup_rows.csv', index=False)
    pd.DataFrame(actionable).to_csv(out / 'v231_current_actionable_rows.csv', index=False)
    pd.DataFrame(expired).to_csv(out / 'v231_current_expired_rows.csv', index=False)

    summary = {
        'version': RULE_VERSION,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'out_dir': str(out),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'dry_source': str(dry_path),
        'latest_market_date': max(dates) if dates else '',
        'dry_recent45_rows': sum(1 for r in dry if r.get('v161_recent45')),
        'raw_rule_rows': len(raw),
        'dedup_rule_rows': len(dedup),
        'duplicate_symbol_entry_keys': len(duplicate_keys),
        'expired_rows': len(expired),
        'overlap_rows': len(overlap),
        'time_order_bad_count': len(time_bad),
        'active_outcome_pollution': len(active_pollution),
        'new_actionable_rows': len(actionable),
        'selector_fields': selector_fields,
        'selector_leak_fields': leak,
        'history_key_counts': {k: len(v) for k, v in history.items()},
        'new_actionable_symbols': [
            {
                'symbol': r.get('symbol'),
                'entry_date': dn(r.get('entry_date')),
                'bars_since_entry': r.get('bars_since_entry'),
                'market_state': r.get('market_state'),
                'allStrongPrev': r.get('v231_all_strong1_pct'),
                'prev_market_date': r.get('v231_prev_market_date'),
                'poi_source': r.get('poi_source'),
                'event_type': r.get('event_type'),
                'risk_pct': r.get('risk_pct'),
                'entry_price': r.get('entry_price'),
            }
            for r in actionable
        ],
        'decision': '',
    }
    if leak:
        summary['decision'] = 'V231_DAILY_SHADOW_AUDIT_FAIL_LEAK_FIELD__NO_WRITE'
    elif time_bad:
        summary['decision'] = 'V231_DAILY_SHADOW_AUDIT_FAIL_TIME_ORDER__NO_WRITE'
    elif active_pollution:
        summary['decision'] = 'V231_DAILY_SHADOW_AUDIT_FAIL_ACTIVE_OUTCOME_POLLUTION__NO_WRITE'
    elif actionable:
        summary['decision'] = 'V231_CURRENT_ACTIONABLE_ROWS_FOUND__ENDPOINT_MAPPING_NEXT_NO_WRITE'
    else:
        summary['decision'] = 'V231_NO_CURRENT_ACTIONABLE_ROWS__KEEP_SHADOW_MONITORING_NO_WRITE'

    (out / 'v231_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    (AUDIT / 'v231_daily_current_shadow_audit_latest.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
