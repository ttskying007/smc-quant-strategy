#!/usr/bin/env python3
"""V66 daily full-market completeness gate."""
from __future__ import annotations
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
KLINE_DIR = ROOT / 'kline_cache'
OUT_JSON = ROOT / 'smc_audit' / 'v66_daily_completeness_gate.json'
OUT_MD = ROOT / 'smc_audit' / 'v66_daily_completeness_gate.md'

MIN_REQUESTED = 4800
MIN_OK = 4500
MIN_LATEST_DATE_COUNT = 4500
MIN_LATEST_DATE_RATIO = 0.94
MAX_FAILED_RATIO = 0.08


def load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def dkey(v: Any) -> str:
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def symbol_from_file(fp: Path) -> str:
    stem = fp.stem.replace('_daily_750', '').replace('_daily_300', '')
    return stem.replace('_SH', '.SH').replace('_SZ', '.SZ').replace('_BJ', '.BJ')


def latest_date(fp: Path) -> str:
    try:
        arr = json.loads(fp.read_text())
        return dkey((arr[-1] or {}).get('t') or (arr[-1] or {}).get('date')) if arr else ''
    except Exception:
        return ''


def main() -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    refresh = load(ROOT / 'smc_monitor/kline_refresh_latest.json', {})
    ops = load(ROOT / 'smc_monitor/ops_latest.json', {})
    daily_candidates = load(ROOT / 'smc_opt_v66/v66_daily_candidates.json', [])
    v90_scan_rows = load(ROOT / 'smc_opt_v90_daily_full_market_scanner/v90_active_picks.json', [])
    v90_scan_report = load(ROOT / 'smc_opt_v90_daily_full_market_scanner/v90_daily_scan_report.json', {})
    current_candidates = v90_scan_rows if v90_scan_rows else daily_candidates
    picks = load(ROOT / 'smc_opt_v66/v66_picks.json', [])

    files_750 = list(KLINE_DIR.glob('*_daily_750.json'))
    symbols = {symbol_from_file(fp): fp for fp in files_750}
    latest_counts = Counter(latest_date(fp) for fp in symbols.values())
    latest_date_key = max([k for k in latest_counts if k] or [''])
    latest_count = latest_counts.get(latest_date_key, 0)
    requested = int(refresh.get('requested') or len(symbols))
    latest_ratio = latest_count / len(symbols) if symbols else 0
    ok = max(int(refresh.get('ok') or 0), latest_count)
    failed = int(refresh.get('failed') or max(0, requested - ok))
    if latest_count >= MIN_LATEST_DATE_COUNT and latest_ratio >= MIN_LATEST_DATE_RATIO:
        failed = min(failed, max(0, requested - latest_count))
    failed_ratio = failed / requested if requested else 1
    data_date = dkey(ops.get('data_date')) or latest_date_key
    v90_market_date = dkey(v90_scan_report.get('latest_market_date') or v90_scan_report.get('latest_date'))
    latest_pick_date = dkey(((ops.get('pick_diagnostics') or {}).get('latest_pick_date'))) or max([dkey(p.get('pick_date') or p.get('entry_date')) for p in picks] or [''])
    candidate_dates = Counter(dkey(p.get('market_latest_date') or p.get('data_date') or p.get('pick_date') or p.get('entry_date')) for p in current_candidates)
    active_latest = [p for p in current_candidates if dkey(p.get('market_latest_date') or p.get('data_date') or p.get('pick_date') or p.get('entry_date')) == latest_date_key and (p.get('pick_scope') in ('ACTIVE_CANDIDATE', 'ACTIVE_ENTRY') or p.get('is_active_pick'))]
    watch_latest = [p for p in current_candidates if dkey(p.get('market_latest_date') or p.get('data_date') or p.get('pick_date') or p.get('entry_date')) == latest_date_key and p.get('pick_scope') == 'WATCH_ONLY']

    checks = {
        'kline_requested_min_4800': requested >= MIN_REQUESTED,
        'kline_ok_min_4500': ok >= MIN_OK,
        'kline_failed_ratio_max_8pct': failed_ratio <= MAX_FAILED_RATIO,
        'cache_latest_date_count_min_4500': latest_count >= MIN_LATEST_DATE_COUNT,
        'cache_latest_date_ratio_min_94pct': latest_ratio >= MIN_LATEST_DATE_RATIO,
        'ops_data_date_matches_cache_latest': data_date == latest_date_key,
        'daily_scan_ran_for_latest_market_date': data_date == latest_date_key and (not v90_market_date or v90_market_date == latest_date_key),
    }
    failed_checks = [k for k, v in checks.items() if not v]
    missing_or_stale_symbols = [sym for sym, fp in sorted(symbols.items()) if latest_date(fp) != latest_date_key][:100]
    summary = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'pass': not failed_checks,
        'failed_checks': failed_checks,
        'checks': checks,
        'requested': requested,
        'ok': ok,
        'failed': failed,
        'failed_ratio_pct': round(failed_ratio * 100, 3),
        'cache_symbol_count': len(symbols),
        'cache_latest_date': latest_date_key,
        'cache_latest_date_count': latest_count,
        'cache_latest_date_ratio_pct': round(latest_ratio * 100, 3),
        'latest_counts_top': dict(latest_counts.most_common(10)),
        'ops_data_date': data_date,
        'v90_market_date': v90_market_date,
        'current_candidate_source': 'V90_DAILY_SCANNER' if v90_scan_rows else 'V66_DAILY_CANDIDATES',
        'latest_pick_date': latest_pick_date,
        'daily_candidate_date_counts': dict(candidate_dates),
        'active_latest_count': len(active_latest),
        'watch_latest_count': len(watch_latest),
        'missing_or_stale_symbols_sample': missing_or_stale_symbols,
        'thresholds': {
            'MIN_REQUESTED': MIN_REQUESTED,
            'MIN_OK': MIN_OK,
            'MIN_LATEST_DATE_COUNT': MIN_LATEST_DATE_COUNT,
            'MIN_LATEST_DATE_RATIO': MIN_LATEST_DATE_RATIO,
            'MAX_FAILED_RATIO': MAX_FAILED_RATIO,
        },
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    OUT_MD.write_text('# V66 Daily Completeness Gate\n\n```json\n' + json.dumps(summary, ensure_ascii=False, indent=2) + '\n```\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
