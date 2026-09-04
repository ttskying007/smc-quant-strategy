#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

BASE = Path('/root/.hermes/smc_audit/v118_baseline_v90')
CUR = Path('/root/.hermes/smc_opt_v90_daily_full_market_scanner')
V104 = Path('/root/.hermes/smc_opt_v104_strict_reclaim/v104_trades.json')
OUT_JSON = Path('/root/.hermes/smc_audit/v118_v116_shadow_daily_scan_diff_20260619.json')
OUT_MD = Path('/root/.hermes/smc_audit/v118_v116_shadow_daily_scan_diff_20260619.md')

REQ = ['family', 'retrace_pct', 'fvg_mid_body_atr', 'source_label', 'v116_gate_reason']
GATE_REASON = 'WEAK_CONTINUATION_FULL_RETRACE_FVG_SHADOW_DOWNGRADE'


def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == '':
            return default
        return float(x)
    except Exception:
        return default


def key(r: Dict[str, Any]) -> str:
    return '|'.join(str(r.get(k) or '') for k in ('symbol', 'entry_date', 'event_date', 'zone_idx', 'entry_idx'))


def scope_counts(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    return {
        'rows': len(rows),
        'active': sum(1 for r in rows if r.get('pick_scope') == 'ACTIVE_CANDIDATE' or r.get('is_active_pick') is True),
        'watch_only': sum(1 for r in rows if r.get('pick_scope') == 'WATCH_ONLY'),
        'gate_downgrade': sum(1 for r in rows if r.get('v116_gate_reason') == GATE_REASON),
    }


def field_contract(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    miss = {k: 0 for k in REQ}
    for r in rows:
        for k in REQ:
            if k not in r or r.get(k) is None or (k != 'v116_gate_reason' and r.get(k) == ''):
                miss[k] += 1
    return {'rows': len(rows), 'missing': miss, 'ready': all(v == 0 for v in miss.values())}


def diff_keys(before: List[Dict[str, Any]], after: List[Dict[str, Any]]) -> Dict[str, Any]:
    b, a = {key(r) for r in before}, {key(r) for r in after}
    return {'before': len(b), 'after': len(a), 'added': len(a - b), 'removed': len(b - a), 'same': len(a & b)}


def label_counts(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    return dict(Counter(str(r.get('source_label') or '') for r in rows))


def concise_row(r: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'symbol': r.get('symbol'),
        'entry_date': r.get('entry_date'),
        'pick_scope': r.get('pick_scope'),
        'market_state': r.get('market_state'),
        'trend_regime': r.get('trend_regime'),
        'family': r.get('family'),
        'retrace_pct': r.get('retrace_pct'),
        'fvg_mid_body_atr': r.get('fvg_mid_body_atr'),
        'source_label': r.get('source_label'),
        'v116_gate_reason': r.get('v116_gate_reason'),
        'v116_shadow_action': r.get('v116_shadow_action'),
        'bars_since_entry': r.get('bars_since_entry'),
    }


def strong_full_retrace(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in rows if f(r.get('retrace_pct')) >= 95 and f(r.get('fvg_mid_body_atr')) >= 0.65]


def main() -> None:
    before_all = load(BASE / 'v90_all_contract_candidates.json', [])
    before_recent = load(BASE / 'v90_active_picks.json', [])
    after_all = load(CUR / 'v90_all_contract_candidates.json', [])
    after_recent = load(CUR / 'v90_active_picks.json', [])
    report = load(CUR / 'v90_daily_scan_report.json', {})
    v104 = load(V104, [])

    downgrade_all = [r for r in after_all if r.get('v116_gate_reason') == GATE_REASON]
    downgrade_recent = [r for r in after_recent if r.get('v116_gate_reason') == GATE_REASON]
    active_downgrade = [r for r in after_recent if (r.get('pick_scope') == 'ACTIVE_CANDIDATE' or r.get('is_active_pick') is True) and r.get('v116_gate_reason') == GATE_REASON]
    watch_downgrade = [r for r in after_recent if r.get('pick_scope') == 'WATCH_ONLY' and r.get('v116_gate_reason') == GATE_REASON]

    after_strong = strong_full_retrace(after_all)
    scanner_trend_up_strong = [r for r in after_strong if 'UP' in str(r.get('trend_regime') or r.get('trend_state') or '')]
    scanner_strong_miskill = [r for r in scanner_trend_up_strong if r.get('v116_gate_reason')]
    v104_trend_up_strong = [r for r in v104 if r.get('trend_state') == 'TREND_UP' and f(r.get('retrace_pct')) >= 95 and f(r.get('fvg_mid_body_atr')) >= 0.65]
    v104_trend_up_strong_miskill = [r for r in v104_trend_up_strong if r.get('v116_gate_reason')]

    result = {
        'engine': 'V118_V116_SHADOW_DAILY_SCAN_DIFF',
        'run_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_files_touched': False,
        'hard_reject': False,
        'gate_rule': 'family == CONTINUATION AND retrace_pct >= 95 AND fvg_mid_body_atr < 0.65',
        'scanner_output': str(CUR),
        'baseline_snapshot': str(BASE),
        'baseline_counts': {'all': scope_counts(before_all), 'recent': scope_counts(before_recent)},
        'after_counts': {'all': scope_counts(after_all), 'recent': scope_counts(after_recent)},
        'key_diff': {'all_candidates': diff_keys(before_all, after_all), 'recent_picks': diff_keys(before_recent, after_recent)},
        'field_contract': {'all_candidates': field_contract(after_all), 'recent_picks': field_contract(after_recent)},
        'v90_report_field_audit_all': report.get('field_audit_all'),
        'v90_report_field_audit_recent': report.get('field_audit_recent'),
        'source_label_counts_all': label_counts(after_all),
        'source_label_counts_recent': label_counts(after_recent),
        'dry_run_diff': {
            'active_diff_if_downgrade_applied': -len(active_downgrade),
            'candidate_diff_if_shadow_only': 0,
            'candidate_rows_tagged_for_downgrade': len(downgrade_all),
            'watch_only_diff_if_downgrade_applied': len(active_downgrade),
            'recent_watch_only_rows_already_tagged': len(watch_downgrade),
            'hard_reject_removed_rows': 0,
        },
        'downgrade_list_all': [concise_row(r) for r in downgrade_all],
        'downgrade_list_recent': [concise_row(r) for r in downgrade_recent],
        'strong_full_retrace_guard': {
            'scanner_strong_full_retrace_all': len(after_strong),
            'scanner_trend_up_or_up_continuation_strong_full_retrace': len(scanner_trend_up_strong),
            'scanner_miskilled_by_gate': len(scanner_strong_miskill),
            'scanner_miskill_examples': [concise_row(r) for r in scanner_strong_miskill[:20]],
            'v104_trend_up_strong_full_retrace': len(v104_trend_up_strong),
            'v104_trend_up_strong_miskilled_by_gate': len(v104_trend_up_strong_miskill),
        },
        'decision': 'RESEARCH_ONLY_FIELD_PROPAGATION_AND_SHADOW_DRY_RUN_DONE_NOT_PROMOTED',
    }
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    def row(items: List[Any]) -> str:
        return '| ' + ' | '.join(str(x) for x in items) + ' |'

    md: List[str] = []
    md.append('# V118 V116 shadow/downgrade daily-scan dry-run diff')
    md.append('')
    md.append(f"- Decision: `{result['decision']}`")
    md.append('- Research only: true; hard reject: false; production files touched: false')
    md.append(f"- Gate: `{result['gate_rule']}`")
    md.append('')
    md.append('## Field contract')
    md.append(row(['scope','rows','ready','family','retrace_pct','fvg_mid_body_atr','source_label','v116_gate_reason']))
    md.append(row(['---','---:','---','---:','---:','---:','---:','---:']))
    for scope, fc in result['field_contract'].items():
        m = fc['missing']
        md.append(row([scope, fc['rows'], fc['ready'], m['family'], m['retrace_pct'], m['fvg_mid_body_atr'], m['source_label'], m['v116_gate_reason']]))
    md.append('')
    md.append('## Baseline vs after scan identity diff')
    md.append(row(['scope','before','after','added','removed','same']))
    md.append(row(['---','---:','---:','---:','---:','---:']))
    for scope, d in result['key_diff'].items():
        md.append(row([scope, d['before'], d['after'], d['added'], d['removed'], d['same']]))
    md.append('')
    md.append('## Shadow/downgrade dry-run diff')
    dd = result['dry_run_diff']
    md.append(row(['active_diff','candidate_diff','watch_only_diff','tagged_all','tagged_recent_watch','hard_reject_removed']))
    md.append(row(['---:','---:','---:','---:','---:','---:']))
    md.append(row([dd['active_diff_if_downgrade_applied'], dd['candidate_diff_if_shadow_only'], dd['watch_only_diff_if_downgrade_applied'], dd['candidate_rows_tagged_for_downgrade'], dd['recent_watch_only_rows_already_tagged'], dd['hard_reject_removed_rows']]))
    md.append('')
    md.append('## Source labels')
    md.append(row(['source_label','all','recent']))
    md.append(row(['---','---:','---:']))
    labels = sorted(set(result['source_label_counts_all']) | set(result['source_label_counts_recent']))
    for lab in labels:
        md.append(row([lab, result['source_label_counts_all'].get(lab, 0), result['source_label_counts_recent'].get(lab, 0)]))
    md.append('')
    md.append('## Strong full-retrace guard')
    sg = result['strong_full_retrace_guard']
    md.append(row(['check','n']))
    md.append(row(['---','---:']))
    for k in ['scanner_strong_full_retrace_all','scanner_trend_up_or_up_continuation_strong_full_retrace','scanner_miskilled_by_gate','v104_trend_up_strong_full_retrace','v104_trend_up_strong_miskilled_by_gate']:
        md.append(row([k, sg[k]]))
    md.append('')
    md.append('## Downgrade list - recent')
    md.append(row(['symbol','entry_date','scope','market_state','trend_regime','family','retrace_pct','mid_body_atr','reason']))
    md.append(row(['---','---','---','---','---','---','---:','---:','---']))
    for r in result['downgrade_list_recent'][:50]:
        md.append(row([r['symbol'], r['entry_date'], r['pick_scope'], r['market_state'], r['trend_regime'], r['family'], r['retrace_pct'], r['fvg_mid_body_atr'], r['v116_gate_reason']]))
    if not result['downgrade_list_recent']:
        md.append('| none |  |  |  |  |  |  |  |  |')
    md.append('')
    md.append('## Downgrade list - all candidates')
    md.append(row(['symbol','entry_date','scope','market_state','trend_regime','family','retrace_pct','mid_body_atr','bars_since_entry']))
    md.append(row(['---','---','---','---','---','---','---:','---:','---:']))
    for r in result['downgrade_list_all'][:80]:
        md.append(row([r['symbol'], r['entry_date'], r['pick_scope'], r['market_state'], r['trend_regime'], r['family'], r['retrace_pct'], r['fvg_mid_body_atr'], r.get('bars_since_entry')]))
    OUT_MD.write_text('\n'.join(md) + '\n')
    print(json.dumps({'out_json': str(OUT_JSON), 'out_md': str(OUT_MD), 'decision': result['decision'], 'dry_run_diff': result['dry_run_diff'], 'strong_guard': result['strong_full_retrace_guard']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
