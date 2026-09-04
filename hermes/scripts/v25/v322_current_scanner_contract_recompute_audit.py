#!/usr/bin/env python3
"""V322 no-write audit: current scanner contract recompute.

V321 found V246 historical pass but current scanner emitted 0 actionable rows.
This audit checks whether the current dry-run path is blocked by stale scanner
fields (especially bars_since_entry) or by genuine absence of current signals.
No production/frontend/watchlist writes.
"""
from __future__ import annotations

import importlib.util
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
KDIR = ROOT / 'kline_cache'
V164_ROWS = AUD / 'v164_corrected_scanner_dry_run_20260622/v164_dryrun_rows.json'
SCANNER_REPORT = ROOT / 'smc_opt_v90_daily_full_market_scanner/v90_daily_scan_report.json'
OUT = AUD / f"v322_current_scanner_contract_recompute_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
LATEST = AUD / 'v322_current_scanner_contract_recompute_latest.json'
MAX_ACTIONABLE_BARS = 10


def load_mod(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod

v246 = load_mod('/root/.hermes/scripts/v25/v246_daily_current_shadow_audit.py', 'v246_for_v322')


def dkey(v: Any) -> str:
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def sf(v: Any, default: float | None = None):
    try:
        if v in (None, ''):
            return default
        return float(v)
    except Exception:
        return default


def load_json(path: Path, default: Any):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def kline_dates(symbol: str) -> list[str]:
    if not symbol or '.' not in symbol:
        return []
    code, exch = symbol.split('.')
    p = KDIR / f'{code}_{exch}_daily_750.json'
    data = load_json(p, [])
    return sorted(dkey((b or {}).get('t') or (b or {}).get('date') or (b or {}).get('day')) for b in data if dkey((b or {}).get('t') or (b or {}).get('date') or (b or {}).get('day')))


def actual_bars_since(symbol: str, entry_date: str, latest_market_date: str) -> int | None:
    dates = kline_dates(symbol)
    if not dates or entry_date not in dates:
        return None
    latest = latest_market_date if latest_market_date in dates else dates[-1]
    if latest not in dates:
        return None
    return dates.index(latest) - dates.index(entry_date)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    dry = load_json(V164_ROWS, [])
    report0 = load_json(SCANNER_REPORT, {})
    latest_market_date = dkey(report0.get('latest_market_date')) or max((dkey(r.get('entry_date')) for r in dry), default='')

    # Build industry/breadth features once, using the exact V246 implementation.
    all_strong, strong_dates = v246.build_all_market_strong1()
    br_ma20, br_dates = v246.load_breadth_above_ma20()
    sym_ind, ind_features, ind_dates = v246.build_industry_features()
    history = v246.load_history_keys()

    rows = []
    mismatch = []
    v164_recent = []
    v164_buy = []
    direct_selected = []
    strict_parent = []
    strict_v246 = []

    for r0 in dry:
        r = dict(r0)
        ed = dkey(r.get('entry_date'))
        sym = str(r.get('symbol') or '')
        stale = sf(r.get('bars_since_entry'))
        actual = actual_bars_since(sym, ed, latest_market_date)
        r['v322_latest_market_date'] = latest_market_date
        r['v322_stale_bars_since_entry'] = stale
        r['v322_actual_bars_since_entry'] = actual
        r['v322_stale_actual_delta'] = None if actual is None or stale is None else actual - stale
        r['v322_recent45_actual'] = actual is not None and 0 <= actual <= 45
        r['v322_actionable_actual10'] = actual is not None and 0 <= actual <= MAX_ACTIONABLE_BARS
        if stale is not None and actual is not None and stale != actual:
            if len(mismatch) < 100:
                mismatch.append({k: r.get(k) for k in ['symbol','entry_date','bars_since_entry','v322_actual_bars_since_entry','v322_stale_actual_delta','v164_rule_pass','v132_reclaim_class']})
        if r.get('v161_recent45'):
            v164_recent.append(r)
        if r.get('v164_rule_pass'):
            v164_buy.append(r)

        # Enrich V246 source-side current features.
        prev_strong_d = v246.previous_market_date(strong_dates, ed)
        prev_breadth_d = v246.previous_market_date(br_dates, ed)
        ind = sym_ind.get(sym, 'UNKNOWN')
        prev_ind_d = v246.previous_market_date(ind_dates, ed)
        feats = ind_features.get((prev_ind_d, ind), {})
        r['v246_prev_market_date'] = prev_strong_d
        r['v236_all_strong1_pct'] = all_strong.get(prev_strong_d)
        r['v246_breadth_date'] = prev_breadth_d
        r['v236_br_above_ma20'] = br_ma20.get(prev_breadth_d)
        r['v244_industry'] = ind
        r['v244_industry_prev_date'] = prev_ind_d
        r.update(feats)
        r['v244_ind_vs_all_strong1'] = v246.sf(r.get('v244_ind_strong1_pct'), 0) - v246.sf(r.get('v236_all_strong1_pct'), 0)
        r['v246_parent_rule_pass'] = v246.parent_rule_pass(r)
        r['v246_daily_shadow_rule_pass'] = v246.v246_rule_pass(r)
        weak = str(r.get('v244_industry')) in v246.WEAK_INDUSTRIES
        addback = v246.sf(r.get('v244_ind_strong1_pct'), -999) >= 31.1688 or v246.sf(r.get('v236_br_above_ma20'), -999) >= 46.8561
        r['v322_direct_v164_plus_v246_industry_pass'] = bool(r.get('v164_rule_pass')) and ((not weak) or addback)
        key = v246.row_key(r)
        r['v322_any_history_overlap'] = any(key in s for s in history.values())

        if r.get('v246_parent_rule_pass'):
            strict_parent.append(r)
        if r.get('v246_daily_shadow_rule_pass'):
            strict_v246.append(r)
        if r.get('v322_direct_v164_plus_v246_industry_pass'):
            direct_selected.append(r)
        rows.append(r)

    def c_actual(arr: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            'rows': len(arr),
            'stale_recent45_rows': sum(bool(r.get('v161_recent45')) for r in arr),
            'actual_recent45_rows': sum(bool(r.get('v322_recent45_actual')) for r in arr),
            'stale_actionable10_rows': sum(0 <= sf(r.get('bars_since_entry'), 999) <= 10 for r in arr),
            'actual_actionable10_rows': sum(bool(r.get('v322_actionable_actual10')) for r in arr),
            'actual_actionable20_rows': sum((r.get('v322_actual_bars_since_entry') is not None) and 0 <= r.get('v322_actual_bars_since_entry') <= 20 for r in arr),
            'entry_dates_top': dict(Counter(dkey(r.get('entry_date')) for r in arr).most_common(12)),
            'actual_bars_top': dict(Counter(str(r.get('v322_actual_bars_since_entry')) for r in arr).most_common(12)),
            'history_overlap_rows': sum(bool(r.get('v322_any_history_overlap')) for r in arr),
            'nonoverlap_actionable10_rows': sum(bool(r.get('v322_actionable_actual10')) and not bool(r.get('v322_any_history_overlap')) for r in arr),
        }

    summary = {
        'version': 'V322_CURRENT_SCANNER_CONTRACT_RECOMPUTE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'dry_source': str(V164_ROWS),
        'scanner_report': str(SCANNER_REPORT),
        'scanner_run_at': report0.get('run_at'),
        'latest_market_date': latest_market_date,
        'scanner_recent_active_candidates': report0.get('recent_active_candidates'),
        'scanner_active_entry_window_candidates': report0.get('active_entry_window_candidates'),
        'source_counts': {
            'dry_rows': len(dry),
            'v161_stale_recent45_rows': len(v164_recent),
            'v164_rule_pass_all_rows': len(v164_buy),
            'stale_actual_mismatch_examples': len(mismatch),
        },
        'contract_counts': {
            'v246_strict_parent': c_actual(strict_parent),
            'v246_strict_after_industry': c_actual(strict_v246),
            'direct_v164_plus_v246_industry': c_actual(direct_selected),
        },
        'mismatch_examples': mismatch[:30],
        'diagnosis': {
            'primary_blocker': 'NO_TRUE_CURRENT_ENTRY_WINDOW_ROWS' if c_actual(direct_selected)['actual_actionable10_rows'] == 0 else 'STRICT_V246_PARENT_RULE_TOO_NARROW',
            'stale_bars_since_entry_is_present': bool(mismatch),
            'strict_parent_rule_zero_current_rows': len(strict_parent) == 0,
            'direct_rule_has_historical_recent_but_not_actionable': len(direct_selected) > 0 and c_actual(direct_selected)['actual_actionable10_rows'] == 0,
        },
        'decision': 'V322_NO_CURRENT_ACTIONABLE_ROWS_AFTER_RECOMPUTE__KEEP_V185' if c_actual(direct_selected)['nonoverlap_actionable10_rows'] == 0 else 'V322_CURRENT_ACTIONABLE_DIRECT_ROWS_FOUND__SHADOW_ENDPOINT_NEXT',
        'artifacts': {
            'summary': str(OUT / 'v322_summary.json'),
            'direct_rows': str(OUT / 'v322_direct_v164_plus_v246_industry_rows.json'),
            'strict_parent_rows': str(OUT / 'v322_strict_parent_rows.json'),
            'latest': str(LATEST),
        },
    }
    json.dump(summary, open(OUT / 'v322_summary.json', 'w'), ensure_ascii=False, indent=2)
    json.dump(direct_selected, open(OUT / 'v322_direct_v164_plus_v246_industry_rows.json', 'w'), ensure_ascii=False, indent=2)
    json.dump(strict_parent, open(OUT / 'v322_strict_parent_rows.json', 'w'), ensure_ascii=False, indent=2)
    json.dump(summary, open(LATEST, 'w'), ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
