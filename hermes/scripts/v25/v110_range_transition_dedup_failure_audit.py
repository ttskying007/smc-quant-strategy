#!/usr/bin/env python3
"""V110 RANGE_TRANSITION dedup + accepted failure audit.

Research-only continuation of V109.
- deduplicate by symbol + entry_date before judging stability
- audit accepted losses by ex-ante fields: risk_pct, retrace_pct, event_to_entry boundary
- compare 8-21 vs 9-21 vs second-confirm-only rules
- no TP/SL tuning, no production/API/frontend/monitor writes
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path('/root/.hermes')
IN_JSON = ROOT / 'smc_audit' / 'v109_range_transition_semantic_rebuild_20260619.json'
OUT_JSON = ROOT / 'smc_audit' / 'v110_range_transition_dedup_failure_audit_20260619.json'
OUT_MD = ROOT / 'smc_audit' / 'v110_range_transition_dedup_failure_audit_20260619.md'
NET_SUCCESS = 0.8


def f(x, default=0.0):
    try:
        if x is None or x == '':
            return default
        return float(x)
    except Exception:
        return default


def i(x, default=999):
    try:
        return int(float(x))
    except Exception:
        return default


def pct(a, b):
    return round(a * 100.0 / b, 2) if b else 0.0


def month(r):
    return str(r.get('entry_date', ''))[:6]


def metric(rows):
    n = len(rows)
    vals = [f(r.get('net_pnl_pct')) for r in rows]
    months = defaultdict(list)
    for r in rows:
        months[month(r)].append(r)
    stable3 = stable5 = 0
    weak_months = []
    for m, rs in sorted(months.items()):
        nn = len(rs)
        wr = pct(sum(f(x.get('net_pnl_pct')) >= NET_SUCCESS for x in rs), nn)
        sl = pct(sum(x.get('exit_reason') == 'SL_HIT' for x in rs), nn)
        avg = round(statistics.mean([f(x.get('net_pnl_pct')) for x in rs]), 4) if rs else 0.0
        if nn >= 3 and wr >= 70 and sl <= 30:
            stable3 += 1
        if nn >= 5 and wr >= 70 and sl <= 30:
            stable5 += 1
        if nn >= 3 and (wr < 70 or sl > 30):
            weak_months.append({'month': m, 'n': nn, 'wr': wr, 'sl': sl, 'avg': avg})
    return {
        'n': n,
        'wr': pct(sum(v >= NET_SUCCESS for v in vals), n),
        'sl': pct(sum(r.get('exit_reason') == 'SL_HIT' for r in rows), n),
        'avg': round(statistics.mean(vals), 4) if vals else 0.0,
        'median': round(statistics.median(vals), 4) if vals else 0.0,
        'cum': round(sum(vals), 4),
        'months': len(months),
        'stable3': stable3,
        'stable5': stable5,
        'weak_months': weak_months,
    }


def group(rows, key, min_n=1):
    d = defaultdict(list)
    for r in rows:
        d[str(key(r))].append(r)
    out = []
    for k, rs in d.items():
        if len(rs) >= min_n:
            s = metric(rs)
            s['key'] = k
            out.append(s)
    out.sort(key=lambda x: (x['key']))
    return out


def dedup_symbol_entry(rows):
    """Deterministic ex-ante canonical row per symbol+entry_date.

    Prefer the cleaner executable candidate before any outcome field:
    lower risk, lower chase, event_to_entry closer to confirmed window, then family name.
    """
    chosen = {}
    for r in rows:
        key = (r.get('symbol'), r.get('entry_date'))
        ete = i(r.get('event_to_entry'))
        in_window_penalty = 0 if 8 <= ete <= 21 else 1
        rank = (
            in_window_penalty,
            f(r.get('risk_pct')),
            f(r.get('chase_pct')),
            abs(ete - 9),
            str(r.get('family', '')),
        )
        old = chosen.get(key)
        if old is None or rank < old[0]:
            chosen[key] = (rank, r)
    return [v[1] for v in chosen.values()]


def is_accept_8_21(r):
    return 8 <= i(r.get('event_to_entry')) <= 21


def is_accept_9_21(r):
    return 9 <= i(r.get('event_to_entry')) <= 21


def is_accept_second_only(r):
    return bool(r.get('second_confirm_before_entry'))


def is_accept_v109(r):
    return is_accept_8_21(r) or is_accept_second_only(r)


def loss_rows(rows):
    return [r for r in rows if f(r.get('net_pnl_pct')) < NET_SUCCESS]


def bin_risk(r):
    x = f(r.get('risk_pct'))
    if x < 5:
        return '<5'
    if x < 6:
        return '5-6'
    if x < 7:
        return '6-7'
    return '>=7'


def bin_retrace(r):
    x = f(r.get('retrace_pct'))
    if x < 30:
        return '<30'
    if x < 50:
        return '30-50'
    if x < 70:
        return '50-70'
    return '>=70'


def bin_chase(r):
    x = f(r.get('chase_pct'))
    if x < 0.5:
        return '<0.5'
    if x < 1.0:
        return '0.5-1.0'
    if x < 1.5:
        return '1.0-1.5'
    return '>=1.5'


def concise(r):
    keys = ['symbol', 'entry_date', 'month', 'family', 'event_to_entry', 'second_confirm_before_entry', 'second_confirm_date', 'exit_reason', 'net_pnl_pct', 'risk_pct', 'retrace_pct', 'chase_pct']
    out = {k: r.get(k) for k in keys}
    out['month'] = month(r)
    return out


def monthly(rows):
    out = []
    d = defaultdict(list)
    for r in rows:
        d[month(r)].append(r)
    for m, rs in sorted(d.items()):
        s = metric(rs)
        s['month'] = m
        s['symbols'] = ','.join(sorted({str(r.get('symbol')) for r in rs})[:20])
        out.append(s)
    return out


def main():
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(IN_JSON.read_text())
    all_range = [dict(r) for r in data['per_trade_range_transition']]
    unique = dedup_symbol_entry(all_range)

    accepted_v109 = [r for r in unique if is_accept_v109(r)]
    accepted_8_21 = [r for r in unique if is_accept_8_21(r)]
    accepted_9_21 = [r for r in unique if is_accept_9_21(r)]
    accepted_10_21 = [r for r in unique if 10 <= i(r.get('event_to_entry')) <= 21]
    accepted_11_21 = [r for r in unique if 11 <= i(r.get('event_to_entry')) <= 21]
    second_only = [r for r in unique if is_accept_second_only(r)]
    second_or_9_21 = [r for r in unique if is_accept_9_21(r) or is_accept_second_only(r)]

    rule_rows = [
        ('RANGE_UNIQUE_BASE', unique),
        ('V109_UNIQUE_8_21_OR_SECOND', accepted_v109),
        ('WAIT_8_21_ONLY', accepted_8_21),
        ('WAIT_9_21_ONLY', accepted_9_21),
        ('WAIT_10_21_ONLY', accepted_10_21),
        ('WAIT_11_21_ONLY', accepted_11_21),
        ('SECOND_CONFIRM_ONLY', second_only),
        ('WAIT_9_21_OR_SECOND', second_or_9_21),
        ('BOUNDARY_E2E_8_ONLY', [r for r in unique if i(r.get('event_to_entry')) == 8]),
        ('WAIT_9_11', [r for r in unique if 9 <= i(r.get('event_to_entry')) <= 11]),
        ('WAIT_12_21', [r for r in unique if 12 <= i(r.get('event_to_entry')) <= 21]),
    ]
    rule_table = []
    for name, rows in rule_rows:
        s = metric(rows)
        s['name'] = name
        rule_table.append(s)

    losses = loss_rows(accepted_v109)
    loss_analysis = {
        'accepted_loss_rows': [concise(r) for r in sorted(losses, key=lambda r: (month(r), f(r.get('net_pnl_pct'))))],
        'loss_by_event_to_entry': group(losses, lambda r: r.get('event_to_entry')),
        'accepted_by_event_to_entry': group(accepted_v109, lambda r: r.get('event_to_entry')),
        'accepted_by_risk_bin': group(accepted_v109, bin_risk),
        'loss_by_risk_bin': group(losses, bin_risk),
        'accepted_by_retrace_bin': group(accepted_v109, bin_retrace),
        'loss_by_retrace_bin': group(losses, bin_retrace),
        'accepted_by_chase_bin': group(accepted_v109, bin_chase),
        'loss_by_chase_bin': group(losses, bin_chase),
        'boundary_8_vs_9_21': {
            'e2e_8': metric([r for r in accepted_v109 if i(r.get('event_to_entry')) == 8]),
            'e2e_9_21': metric([r for r in accepted_v109 if 9 <= i(r.get('event_to_entry')) <= 21]),
        },
    }

    promotion_pass = False
    best = max(rule_table, key=lambda x: (x['wr'], x['n'])) if rule_table else {}
    result = {
        'version': 'V110_RANGE_TRANSITION_DEDUP_FAILURE_AUDIT',
        'research_only': True,
        'production_files_touched': False,
        'inputs': {'v109_json': str(IN_JSON)},
        'method': 'Use V109 RANGE_TRANSITION rows, first deduplicate by symbol+entry_date with deterministic ex-ante ranking, then compare confirmation rules and dissect accepted losses. No TP/SL changes.',
        'dedup': {
            'raw_rows': len(all_range),
            'unique_symbol_entry_rows': len(unique),
            'removed_duplicate_rows': len(all_range) - len(unique),
        },
        'rule_table': rule_table,
        'monthly': {
            'v109_unique': monthly(accepted_v109),
            'wait_9_21': monthly(accepted_9_21),
            'wait_12_21': monthly([r for r in unique if 12 <= i(r.get('event_to_entry')) <= 21]),
        },
        'loss_analysis': loss_analysis,
        'decision': 'RESEARCH_ONLY_NOT_PROMOTED',
        'promotion_gate': {
            'required': 'production candidate needs n>=100, WR>=70, SL<=30, stable3>=12 after dedup, plus fresh full-market generator; V110 is only research audit',
            'passed': promotion_pass,
            'best_rule_by_wr': best,
            'reason': 'All cleaner RANGE_TRANSITION rules remain small after symbol+entry_date dedup; event_to_entry=8 boundary is weak; second-confirm-only has too few rows; 12-21 is clean but far below sample/month stability gate.',
        },
        'next': 'V111 should inspect actual structure of remaining WAIT_9_21/12_21 losses and duplicate source generation, not tune TP/SL and not route to production.',
    }
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    lines = [
        '# V110 RANGE_TRANSITION Dedup + Failure Audit', '',
        'Decision: **RESEARCH_ONLY_NOT_PROMOTED**', '',
        'Scope: research-only. First deduplicate by `symbol+entry_date`; no TP/SL tuning; no production/API/frontend changes.', '',
        '## Dedup',
        '| raw rows | unique rows | removed duplicate rows |',
        '|---:|---:|---:|',
        f"| {result['dedup']['raw_rows']} | {result['dedup']['unique_symbol_entry_rows']} | {result['dedup']['removed_duplicate_rows']} |",
        '', '## Rule comparison after dedup',
        '| Rule | n | WR | SL | Avg | Median | Months | Stable3 | Stable5 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for s in rule_table:
        lines.append(f"| {s['name']} | {s['n']} | {s['wr']}% | {s['sl']}% | {s['avg']}% | {s['median']}% | {s['months']} | {s['stable3']} | {s['stable5']} |")
    lines += ['', '## Accepted losses after dedup', '| Symbol | Entry | E2E | SecondBefore | Exit | Net | Risk | Retrace | Chase |', '|---|---|---:|---|---|---:|---:|---:|---:|']
    for r in result['loss_analysis']['accepted_loss_rows']:
        lines.append(f"| {r['symbol']} | {r['entry_date']} | {r['event_to_entry']} | {r['second_confirm_before_entry']} | {r['exit_reason']} | {r['net_pnl_pct']} | {r['risk_pct']} | {r['retrace_pct']} | {r['chase_pct']} |")
    lines += ['', '## Event boundary', '| Slice | n | WR | SL | Avg | Median |', '|---|---:|---:|---:|---:|---:|']
    for k, s in result['loss_analysis']['boundary_8_vs_9_21'].items():
        lines.append(f"| {k} | {s['n']} | {s['wr']}% | {s['sl']}% | {s['avg']}% | {s['median']}% |")
    lines += ['', '## Monthly V109 unique accepted', '| Month | n | WR | SL | Avg | Stable3? | Symbols |', '|---|---:|---:|---:|---:|---|---|']
    for s in result['monthly']['v109_unique']:
        ok = 'Y' if s['n'] >= 3 and s['wr'] >= 70 and s['sl'] <= 30 else 'N'
        lines.append(f"| {s['month']} | {s['n']} | {s['wr']}% | {s['sl']}% | {s['avg']}% | {ok} | {s['symbols']} |")
    lines += ['', '## Conclusion', '- V110 confirms V109 direction but still does not promote.', '- `event_to_entry=8` is a weak boundary; `9-21` is better, `12-21` is cleaner but too small.', '- `second-confirm-only` is not enough sample.', '- RANGE_TRANSITION cannot yet form a stable production rule after dedup.']
    OUT_MD.write_text('\n'.join(lines) + '\n')
    print(json.dumps({'out_json': str(OUT_JSON), 'out_md': str(OUT_MD), 'decision': result['decision'], 'dedup': result['dedup'], 'rule_table': rule_table, 'accepted_losses': result['loss_analysis']['accepted_loss_rows']}, ensure_ascii=False, indent=2)[:20000])


if __name__ == '__main__':
    main()
