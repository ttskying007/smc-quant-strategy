#!/usr/bin/env python3
"""V164 corrected scanner dry-run after V163 integrity audit.

V163 found that V161/V160 scanner dry-run leaked FAILED/RECOVERY/UNCLEAR
reclaim classes because the application rule did not require TRUE_TAKEOVER_2
or TRUE_TAKEOVER_3_STRICT. This script keeps V161's scanner-time field build
contract, applies the corrected V164 rule, and writes audit artifacts only.

No production/frontend/watchlist writes.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, '/root/.hermes/scripts/v25')

from v161_dry_run_scanner_contract import (  # noqa: E402
    ENGINE as V161_ENGINE,
    OUTCOME_FIELD_TOKENS,
    RECENT_BARS,
    REQUIRED_V161_FIELDS,
    SCANNER_REPORT,
    SRC,
    build_row,
    field_audit,
    kline_path,
    load_json,
    missing_required,
    num,
)

ROOT = Path('/root/.hermes')
OUT = ROOT / 'smc_audit' / 'v164_corrected_scanner_dry_run_20260622'
OUT.mkdir(parents=True, exist_ok=True)

ENGINE = 'V164_CORRECTED_SCANNER_DRY_RUN'
BODY_RELEASE_MAX = 87.1077


def boolish(value: Any) -> bool:
    return str(value).strip().lower() in {'true', '1', 'yes'}


def apply_v164(row: Dict[str, Any]) -> tuple[str, str, bool]:
    tt2 = boolish(row.get('v132_true_takeover_2'))
    tt3 = boolish(row.get('v132_true_takeover_3_strict'))
    takeover_ok = tt2 or tt3
    body_ok = num(row.get('v132_reclaim_bull_body_pct'), 999.0) <= BODY_RELEASE_MAX
    ok = takeover_ok and body_ok
    reasons: list[str] = []
    if not takeover_ok:
        reasons.append('NOT_TRUE_TAKEOVER_2_OR_3')
    if not body_ok:
        reasons.append('BODY_GT_87_1077')
    return ('BUY' if ok else 'WATCH_ONLY', ';'.join(reasons) if reasons else 'V164_RULE_PASS', ok)


def enrich_v164(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    action, reason, ok = apply_v164(out)
    out.update({
        'v164_engine': ENGINE,
        'v164_dry_action': action,
        'v164_dry_reason': reason,
        'v164_rule_pass': ok,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
    })
    return out


def vc(rows: List[Dict[str, Any]], key: str) -> dict[str, int]:
    return dict(Counter(str(r.get(key, '')) for r in rows))


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    fields = sorted({k for r in rows for k in r.keys()}) if rows else []
    with path.open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction='ignore')
        if fields:
            writer.writeheader()
            writer.writerows(rows)


def slim(row: Dict[str, Any]) -> Dict[str, Any]:
    cols = [
        'symbol', 'poi_source', 'combo_family', 'event_type', 'entry_date', 'entry_price',
        'bars_since_entry', 'market_state', 'risk_pct', 'entry_chase_above_zone_pct',
        'reclaim_close_above_zone_pct', 'reclaim_close_pos', 'touch_to_reclaim_bars',
        'v132_reclaim_class', 'v132_reclaim_bull_body_pct', 'v132_reclaim_close_pos_pct',
        'v132_true_takeover_2', 'v132_true_takeover_3_strict',
        'v160_dry_action', 'v160_dry_reason', 'v164_dry_action', 'v164_dry_reason',
    ]
    return {c: row.get(c, '') for c in cols if c in row}


def main() -> None:
    src_rows = load_json(SRC, [])
    scanner_report = load_json(SCANNER_REPORT, {})
    bar_cache: Dict[str, List[Dict[str, Any]]] = {}
    built_rows: List[Dict[str, Any]] = []
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
        built_rows.append(enrich_v164(build_row(src, bars)))

    recent = [r for r in built_rows if r.get('v161_recent45')]
    v160_buy_recent = [r for r in recent if r.get('v160_rule_pass')]
    v164_buy_recent = [r for r in recent if r.get('v164_rule_pass')]
    v164_latest_date = max((str(r.get('entry_date')) for r in v164_buy_recent), default='')
    v164_latest = [r for r in v164_buy_recent if str(r.get('entry_date')) == v164_latest_date]

    recent_audit = field_audit(recent)
    v164_buy_audit = field_audit(v164_buy_recent)
    non_takeover_v164 = [r for r in v164_buy_recent if not (boolish(r.get('v132_true_takeover_2')) or boolish(r.get('v132_true_takeover_3_strict')))]
    body_fail_v164 = [r for r in v164_buy_recent if num(r.get('v132_reclaim_bull_body_pct'), 999.0) > BODY_RELEASE_MAX]

    summary: dict[str, Any] = {
        'decision': 'V164_CORRECTED_RULE_SCANNER_DRY_RUN_PASS_NO_PRODUCTION_WRITE' if (
            recent_audit['ready']
            and v164_buy_audit['ready']
            and recent_audit['outcome_field_leak_rows'] == 0
            and v164_buy_audit['outcome_field_leak_rows'] == 0
            and missing_kline == 0
            and not non_takeover_v164
            and not body_fail_v164
        ) else 'V164_CORRECTED_RULE_SCANNER_DRY_RUN_BLOCKED_NO_PRODUCTION_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'engine': ENGINE,
        'input': str(SRC),
        'scanner_report': {
            'engine': scanner_report.get('engine'),
            'run_at': scanner_report.get('run_at'),
            'scanned_symbols': scanner_report.get('scanned_symbols'),
            'latest_market_date': scanner_report.get('latest_market_date'),
            'v128_dedup_rows': (scanner_report.get('v128_parallel_shadow') or {}).get('dedup_rows'),
            'v128_recent45_rows': (scanner_report.get('v128_parallel_shadow') or {}).get('recent45_rows'),
        },
        'source_rows': len(src_rows),
        'built_rows': len(built_rows),
        'missing_kline': missing_kline,
        'recent45_rows': len(recent),
        'v160_buy_recent45_old_buggy': len(v160_buy_recent),
        'v164_buy_recent45_corrected': len(v164_buy_recent),
        'rejected_from_v160_buy_by_v164': len(v160_buy_recent) - len([r for r in v160_buy_recent if r.get('v164_rule_pass')]),
        'v164_latest_entry_date': v164_latest_date,
        'v164_latest_rows': len(v164_latest),
        'recent45_field_contract': recent_audit,
        'v164_buy_recent45_field_contract': v164_buy_audit,
        'v164_rule_contract': f'(v132_true_takeover_2 OR v132_true_takeover_3_strict) AND v132_reclaim_bull_body_pct <= {BODY_RELEASE_MAX}',
        'v164_integrity': {
            'non_takeover_buy_rows': len(non_takeover_v164),
            'body_fail_buy_rows': len(body_fail_v164),
            'outcome_field_leak_rows': v164_buy_audit['outcome_field_leak_rows'],
        },
        'by_v164_action_recent45': vc(recent, 'v164_dry_action'),
        'by_v164_reason_recent45': vc(recent, 'v164_dry_reason'),
        'by_reclaim_class_v164_buy_recent45': vc(v164_buy_recent, 'v132_reclaim_class'),
        'by_poi_source_v164_buy_recent45': vc(v164_buy_recent, 'poi_source'),
        'latest_rows': [slim(r) for r in v164_latest],
    }

    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    (OUT / 'v164_dryrun_rows.json').write_text(json.dumps(built_rows, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    (OUT / 'v164_dryrun_recent45.json').write_text(json.dumps(recent, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    (OUT / 'v164_buy_recent45.json').write_text(json.dumps(v164_buy_recent, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    write_csv(OUT / 'v164_buy_recent45.csv', [slim(r) for r in v164_buy_recent])
    write_csv(OUT / 'v164_latest_buy.csv', [slim(r) for r in v164_latest])

    lines = [
        '# V164 corrected scanner dry-run', '',
        f"Decision: `{summary['decision']}`。只读 dry-run；未写生产/前端/watchlist。", '',
        '## 修复规则', '',
        f"`{summary['v164_rule_contract']}`", '',
        '## Counts', '',
        '|scope|n|', '|---|---:|',
        f"|source rows|{summary['source_rows']}|",
        f"|built rows|{summary['built_rows']}|",
        f"|recent45 rows|{summary['recent45_rows']}|",
        f"|old V160 BUY recent45|{summary['v160_buy_recent45_old_buggy']}|",
        f"|V164 corrected BUY recent45|{summary['v164_buy_recent45_corrected']}|",
        f"|rejected from old V160 BUY|{summary['rejected_from_v160_buy_by_v164']}|",
        f"|latest BUY date|{summary['v164_latest_entry_date']}|",
        f"|latest BUY rows|{summary['v164_latest_rows']}|",
        '', '## Integrity', '',
        '|check|value|', '|---|---:|',
        f"|non-takeover BUY rows|{summary['v164_integrity']['non_takeover_buy_rows']}|",
        f"|body-fail BUY rows|{summary['v164_integrity']['body_fail_buy_rows']}|",
        f"|outcome leak BUY rows|{summary['v164_integrity']['outcome_field_leak_rows']}|",
        '', '## Latest BUY rows', '',
    ]
    if v164_latest:
        # Lightweight markdown table without requiring tabulate.
        latest_slim = [slim(r) for r in v164_latest]
        headers = list(latest_slim[0].keys())
        lines.append('|' + '|'.join(headers) + '|')
        lines.append('|' + '|'.join(['---'] * len(headers)) + '|')
        for row in latest_slim:
            lines.append('|' + '|'.join(str(row.get(h, '')) for h in headers) + '|')
    else:
        lines.append('None')
    lines.extend(['', '## Artifacts', '', f"- `{OUT / 'summary.json'}`", f"- `{OUT / 'v164_buy_recent45.csv'}`", f"- `{OUT / 'v164_latest_buy.csv'}`"])
    (OUT / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
