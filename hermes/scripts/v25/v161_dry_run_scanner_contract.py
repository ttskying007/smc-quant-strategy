#!/usr/bin/env python3
"""V161 dry-run scanner contract for V158/V160 lifecycle rule fields.

Purpose:
- Verify whether the fields needed by V158/V160 can be generated from the real
  daily scanner candidate stream at scan time.
- Do not read historical V158/V160 chosen rows as candidate input.
- Do not use post-entry outcome fields such as pnl/exit/MAE/MFE.
- Do not write production/frontend/watchlist artifacts.

Input contract source:
- v90_daily_full_market_scanner.py output: v128_parallel_shadow_candidates.json
  generated from current kline cache and scanner POI/entry logic.
- Kline cache only for reclaim-confirmation candles needed before the delayed
  scanner decision.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, '/root/.hermes/scripts/v25')

from v132_fvg_reclaim_takeover_shadow_backtest import calc_reclaim_features, classify, true_takeover  # noqa: E402
from v90_daily_full_market_scanner import date_key, num  # noqa: E402

ROOT = Path('/root/.hermes')
SCANNER_DIR = ROOT / 'smc_opt_v90_daily_full_market_scanner'
SRC = SCANNER_DIR / 'v128_parallel_shadow_candidates.json'
SCANNER_REPORT = SCANNER_DIR / 'v90_daily_scan_report.json'
KLINE_DIR = ROOT / 'kline_cache'
OUT = ROOT / 'smc_audit' / 'v161_dry_run_scanner_contract_20260622'
OUT.mkdir(parents=True, exist_ok=True)

ENGINE = 'V161_DRY_RUN_SCANNER_CONTRACT'
RECENT_BARS = 45
V158_CHASE_MAX = 3.0
V160_CHASE_MAX = 3.5
NONSTRICT_BODY_MAX = 86.6124

# These fields must be absent from V161 selector inputs. They are allowed only in
# historical evaluation files, never in the scanner dry-run decision payload.
OUTCOME_FIELD_TOKENS = (
    'pnl', 'exit_', 'exitreason', 'exit_reason', 'won', 'mae', 'mfe',
    'hold_bars', 'valid_backtest', 't1_violation', 'v138_', 'v150_',
    'v151_', 'v152_', 'v153_', 'v154_', 'v158_', 'v159_', 'v160_',
)

REQUIRED_SOURCE_FIELDS = [
    'symbol', 'poi_source', 'combo_family', 'event_type', 'event_date',
    'zone_date', 'zone_low', 'zone_high', 'touch_idx', 'reclaim_idx',
    'entry_idx', 'entry_date', 'entry_price', 'risk_pct',
    'v85_zone_width_pct', 'market_state', 'reclaim_close_above_zone_pct',
    'reclaim_close_pos', 'touch_to_reclaim_bars',
    'entry_chase_above_zone_pct',
]

OPTIONAL_SOURCE_FIELDS = [
    # FVG/OB+FVG rows have these; DEMAND_OB rows legitimately do not. They are
    # not part of the selected V158/V160 rule, so absence must not block the core
    # scanner contract.
    'source_gap_atr', 'source_mid_body_atr',
]

REQUIRED_V161_FIELDS = REQUIRED_SOURCE_FIELDS + [
    'v132_reclaim_bull_body_pct', 'v132_reclaim_close_pos_pct',
    'v132_reclaim_class', 'v132_true_takeover_1', 'v132_true_takeover_2',
    'v132_true_takeover_3_strict', 'v132_hold_close_above_zone_high_1',
    'v132_hold_close_above_zone_high_2', 'v132_hold_close_above_zone_high_3',
    'v132_no_break_reclaim_low_1', 'v132_no_break_reclaim_low_2',
    'v132_no_break_reclaim_low_3', 'v132_post_zone_pullback_depth_pct_1',
    'v132_post_zone_pullback_depth_pct_2', 'v132_post_zone_pullback_depth_pct_3',
    'v158_dry_action', 'v160_dry_action', 'v160_rule_pass',
    'v161_outcome_field_leak',
]


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def kline_path(symbol: str) -> Path:
    return KLINE_DIR / f"{symbol.replace('.', '_')}_daily_750.json"


def row_has_outcome_field(row: Dict[str, Any]) -> bool:
    for key, value in row.items():
        lk = str(key).lower()
        if any(tok in lk for tok in OUTCOME_FIELD_TOKENS):
            if value not in (None, '', [], {}):
                return True
    return False


def missing_required(row: Dict[str, Any], fields: List[str]) -> List[str]:
    missing: List[str] = []
    for field in fields:
        value = row.get(field)
        if value in (None, ''):
            missing.append(field)
            continue
        if field in {'zone_low', 'zone_high', 'entry_price'} and num(value) <= 0:
            missing.append(field)
    return missing


def apply_v158(row: Dict[str, Any]) -> tuple[str, str]:
    strict3 = bool(row.get('v132_true_takeover_3_strict'))
    chase_ok = num(row.get('entry_chase_above_zone_pct'), 999.0) <= V158_CHASE_MAX
    nonstrict_body_ok = strict3 or num(row.get('v132_reclaim_bull_body_pct'), 999.0) <= NONSTRICT_BODY_MAX
    ok = (strict3 or chase_ok) and nonstrict_body_ok
    reasons = []
    if not (strict3 or chase_ok):
        reasons.append('TT2_NEEDS_SECOND_CONFIRM_OR_CHASE_TOO_HIGH')
    if not nonstrict_body_ok:
        reasons.append('NONSTRICT_RECLAIM_BODY_EXHAUSTION')
    return ('BUY' if ok else 'WATCH_ONLY', ';'.join(reasons) if reasons else 'V158_RULE_PASS')


def apply_v160(row: Dict[str, Any]) -> tuple[str, str, bool]:
    strict3 = bool(row.get('v132_true_takeover_3_strict'))
    chase_ok = num(row.get('entry_chase_above_zone_pct'), 999.0) <= V160_CHASE_MAX
    nonstrict_body_ok = strict3 or num(row.get('v132_reclaim_bull_body_pct'), 999.0) <= NONSTRICT_BODY_MAX
    ok = (strict3 or chase_ok) and nonstrict_body_ok
    reasons = []
    if not (strict3 or chase_ok):
        reasons.append('TT2_CONFIRM_OR_CHASE_LE_3_5_FAIL')
    if not nonstrict_body_ok:
        reasons.append('NONSTRICT_BODY_LE_86_6_FAIL')
    return ('BUY' if ok else 'WATCH_ONLY', ';'.join(reasons) if reasons else 'V160_RULE_PASS', ok)


def build_row(src: Dict[str, Any], bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    base = {k: src.get(k, '') for k in REQUIRED_SOURCE_FIELDS + OPTIONAL_SOURCE_FIELDS}
    base.update({
        'engine': ENGINE,
        'scanner_source': 'v90_daily_full_market_scanner:v128_parallel_shadow_candidates',
        'scanner_input_file': str(SRC),
        'production_write': False,
        'dry_run_only': True,
        'symbol': src.get('symbol'),
        'bars_since_entry': src.get('bars_since_entry', ''),
        'v161_recent45': 0 <= num(src.get('bars_since_entry'), 9999) <= RECENT_BARS,
        'v161_outcome_field_leak': row_has_outcome_field(src),
    })
    feats = calc_reclaim_features(src, bars)
    if feats:
        base.update(feats)
        base['v132_reclaim_class'] = classify(base)
        base['v132_true_takeover_1'] = true_takeover(base, 1)
        base['v132_true_takeover_2'] = true_takeover(base, 2)
        base['v132_true_takeover_3_strict'] = true_takeover(base, 3, strict=True)
    else:
        base['v132_reclaim_class'] = 'FEATURE_BUILD_FAILED'
        base['v132_true_takeover_1'] = False
        base['v132_true_takeover_2'] = False
        base['v132_true_takeover_3_strict'] = False
    v158_action, v158_reason = apply_v158(base)
    v160_action, v160_reason, v160_pass = apply_v160(base)
    base.update({
        'v158_dry_action': v158_action,
        'v158_dry_reason': v158_reason,
        'v160_dry_action': v160_action,
        'v160_dry_reason': v160_reason,
        'v160_rule_pass': v160_pass,
    })
    base['v161_missing_source_fields'] = missing_required(base, REQUIRED_SOURCE_FIELDS)
    base['v161_missing_contract_fields'] = missing_required(base, REQUIRED_V161_FIELDS)
    base['v161_decision_available'] = bool(feats) and not base['v161_missing_contract_fields'] and not base['v161_outcome_field_leak']
    return base


def field_audit(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    miss = {f: 0 for f in REQUIRED_V161_FIELDS}
    for row in rows:
        for field in REQUIRED_V161_FIELDS:
            if field in row.get('v161_missing_contract_fields', []):
                miss[field] += 1
    return {
        'rows': len(rows),
        'required_fields': REQUIRED_V161_FIELDS,
        'missing': miss,
        'ready': bool(rows) and all(v == 0 for v in miss.values()),
        'decision_available_rows': sum(1 for r in rows if r.get('v161_decision_available')),
        'outcome_field_leak_rows': sum(1 for r in rows if r.get('v161_outcome_field_leak')),
    }


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    fields = sorted({k for r in rows for k in r.keys()}) if rows else []
    with path.open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction='ignore')
        if fields:
            writer.writeheader()
            writer.writerows(rows)


def main() -> None:
    src_rows = load_json(SRC, [])
    scanner_report = load_json(SCANNER_REPORT, {})
    bar_cache: Dict[str, List[Dict[str, Any]]] = {}
    rows: List[Dict[str, Any]] = []
    missing_kline = 0
    for src in src_rows:
        sym = str(src.get('symbol') or '')
        if not sym:
            continue
        if sym not in bar_cache:
            path = kline_path(sym)
            bar_cache[sym] = load_json(path, []) if path.exists() else []
        bars = bar_cache[sym]
        if not bars:
            missing_kline += 1
            continue
        rows.append(build_row(src, bars))

    recent = [r for r in rows if r.get('v161_recent45')]
    buy160_recent = [r for r in recent if r.get('v160_rule_pass')]
    buy160_all = [r for r in rows if r.get('v160_rule_pass')]
    by_source = Counter(str(r.get('poi_source')) for r in rows)
    by_action_recent = Counter(str(r.get('v160_dry_action')) for r in recent)
    by_class_recent = Counter(str(r.get('v132_reclaim_class')) for r in recent)
    all_audit = field_audit(rows)
    recent_audit = field_audit(recent)
    buy_recent_audit = field_audit(buy160_recent)

    contract_clean = (
        recent_audit['ready']
        and buy_recent_audit['ready']
        and recent_audit['outcome_field_leak_rows'] == 0
        and buy_recent_audit['outcome_field_leak_rows'] == 0
        and missing_kline == 0
    )
    decision = 'V161_DRY_RUN_SCANNER_CONTRACT_CLEAN_NO_PRODUCTION_WRITE' if contract_clean else 'V161_DRY_RUN_SCANNER_CONTRACT_BLOCKED_NO_PRODUCTION_WRITE'

    summary = {
        'decision': decision,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'input': str(SRC),
        'out': str(OUT),
        'scanner_report': {
            'engine': scanner_report.get('engine'),
            'run_at': scanner_report.get('run_at'),
            'scanned_symbols': scanner_report.get('scanned_symbols'),
            'latest_market_date': scanner_report.get('latest_market_date'),
            'v128_dedup_rows': (scanner_report.get('v128_parallel_shadow') or {}).get('dedup_rows'),
            'v128_recent45_rows': (scanner_report.get('v128_parallel_shadow') or {}).get('recent45_rows'),
            'v125_contract_pass_recent45': (scanner_report.get('v128_parallel_shadow') or {}).get('v125_contract_pass_recent45'),
        },
        'source_rows': len(src_rows),
        'contract_rows_built': len(rows),
        'missing_kline': missing_kline,
        'recent45_rows': len(recent),
        'v160_buy_all': len(buy160_all),
        'v160_buy_recent45': len(buy160_recent),
        'all_field_contract': all_audit,
        'recent45_field_contract': recent_audit,
        'v160_buy_recent45_field_contract': buy_recent_audit,
        'by_poi_source_all': dict(by_source),
        'by_v160_action_recent45': dict(by_action_recent),
        'by_reclaim_class_recent45': dict(by_class_recent),
        'rule_contract': {
            'v158': f'(v132_true_takeover_3_strict OR entry_chase_above_zone_pct <= {V158_CHASE_MAX}) AND (strict3 OR v132_reclaim_bull_body_pct <= {NONSTRICT_BODY_MAX})',
            'v160_best_rule': f'(v132_true_takeover_3_strict OR entry_chase_above_zone_pct <= {V160_CHASE_MAX}) AND (strict3 OR v132_reclaim_bull_body_pct <= {NONSTRICT_BODY_MAX})',
            'excluded_from_selector': 'pnl/exit/MAE/MFE/hold/outcome and historical V158/V160 rows',
        },
        'sample_recent45': [
            {k: r.get(k) for k in [
                'symbol','poi_source','combo_family','entry_date','bars_since_entry','market_state',
                'entry_chase_above_zone_pct','v132_reclaim_bull_body_pct','v132_true_takeover_3_strict',
                'v132_reclaim_class','v160_dry_action','v160_dry_reason','v161_decision_available'
            ]}
            for r in recent[:30]
        ],
        'sample_v160_buy_recent45': [
            {k: r.get(k) for k in [
                'symbol','poi_source','combo_family','entry_date','bars_since_entry','market_state',
                'entry_chase_above_zone_pct','v132_reclaim_bull_body_pct','v132_true_takeover_3_strict',
                'v132_reclaim_class','v160_dry_action','v160_dry_reason'
            ]}
            for r in buy160_recent[:30]
        ],
    }

    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    (OUT / 'v161_dryrun_rows.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    (OUT / 'v161_dryrun_recent45.json').write_text(json.dumps(recent, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    (OUT / 'v161_v160_buy_recent45.json').write_text(json.dumps(buy160_recent, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    write_csv(OUT / 'v161_dryrun_recent45.csv', recent)

    report = [
        '# V161 dry-run scanner contract', '',
        f"Decision: `{decision}`。只读 dry-run；未写生产/前端/watchlist。", '',
        '## Contract summary',
        f"- scanner source rows: {len(src_rows)}",
        f"- built rows: {len(rows)}",
        f"- recent45 rows: {len(recent)}",
        f"- V160 BUY recent45: {len(buy160_recent)}",
        f"- missing kline: {missing_kline}",
        f"- outcome field leak rows: all={all_audit['outcome_field_leak_rows']}, recent45={recent_audit['outcome_field_leak_rows']}", '',
        '## Field contract',
        '|scope|rows|ready|decision_available|outcome_leak|missing_nonzero|',
        '|---|---:|---|---:|---:|---:|',
    ]
    for scope, audit in [('all', all_audit), ('recent45', recent_audit), ('v160_buy_recent45', buy_recent_audit)]:
        miss_nonzero = sum(1 for v in audit['missing'].values() if v)
        report.append(f"|{scope}|{audit['rows']}|{audit['ready']}|{audit['decision_available_rows']}|{audit['outcome_field_leak_rows']}|{miss_nonzero}|")
    report.extend([
        '', '## Recent45 V160 action counts',
        '|action|n|', '|---|---:|',
    ])
    for k, v in sorted(by_action_recent.items()):
        report.append(f'|{k}|{v}|')
    report.extend(['', '## Recent45 reclaim classes', '|class|n|', '|---|---:|'])
    for k, v in sorted(by_class_recent.items()):
        report.append(f'|{k}|{v}|')
    report.extend([
        '', '## Conclusion',
        'V161 validates only scanner-time field availability and leak cleanliness. It does not promote V158/V160 to production because V160 stability remained non-robust (bad month present).',
    ])
    (OUT / 'report.md').write_text('\n'.join(report), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
