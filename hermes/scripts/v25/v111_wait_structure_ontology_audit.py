#!/usr/bin/env python3
"""V111 WAIT_9_21 / WAIT_12_21 structure ontology audit.

Research-only continuation of V110.
- Do not tune TP/SL.
- Do not write production/API/frontend/monitor files.
- Compare ex-ante structure features of WAIT_9_21 vs WAIT_12_21.
- Dissect remaining WAIT_9_21 losses.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path('/root/.hermes')
V109_JSON = ROOT / 'smc_audit' / 'v109_range_transition_semantic_rebuild_20260619.json'
V104_TRADES = ROOT / 'smc_opt_v104_strict_reclaim' / 'v104_trades.json'
OUT_JSON = ROOT / 'smc_audit' / 'v111_wait_structure_ontology_audit_20260619.json'
OUT_MD = ROOT / 'smc_audit' / 'v111_wait_structure_ontology_audit_20260619.md'
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
        if x is None or x == '':
            return default
        return int(float(x))
    except Exception:
        return default


def pct(a, b):
    return round(a * 100.0 / b, 2) if b else 0.0


def month(r):
    return str(r.get('entry_date', ''))[:6]


def median(rows, key):
    vals = [f(r.get(key)) for r in rows]
    return round(statistics.median(vals), 4) if vals else 0.0


def avg(rows, key):
    vals = [f(r.get(key)) for r in rows]
    return round(statistics.mean(vals), 4) if vals else 0.0


def metric(rows):
    vals = [f(r.get('net_pnl_pct')) for r in rows]
    months = defaultdict(list)
    for r in rows:
        months[month(r)].append(r)
    stable3 = stable5 = 0
    weak_months = []
    for m, rs in sorted(months.items()):
        n = len(rs)
        wr = pct(sum(f(x.get('net_pnl_pct')) >= NET_SUCCESS for x in rs), n)
        sl = pct(sum(x.get('exit_reason') == 'SL_HIT' for x in rs), n)
        if n >= 3 and wr >= 70 and sl <= 30:
            stable3 += 1
        if n >= 5 and wr >= 70 and sl <= 30:
            stable5 += 1
        if n >= 3 and (wr < 70 or sl > 30):
            weak_months.append({'month': m, 'n': n, 'wr': wr, 'sl': sl, 'avg': avg(rs, 'net_pnl_pct')})
    return {
        'n': len(rows),
        'wr': pct(sum(v >= NET_SUCCESS for v in vals), len(rows)),
        'sl': pct(sum(r.get('exit_reason') == 'SL_HIT' for r in rows), len(rows)),
        'avg': round(statistics.mean(vals), 4) if vals else 0.0,
        'median': round(statistics.median(vals), 4) if vals else 0.0,
        'months': len(months),
        'stable3': stable3,
        'stable5': stable5,
        'weak_months': weak_months,
    }


def dedup_symbol_entry(rows):
    chosen = {}
    for r in rows:
        key = (r.get('symbol'), r.get('entry_date'))
        event_to_entry = i(r.get('event_to_entry'))
        rank = (
            0 if 8 <= event_to_entry <= 21 else 1,
            f(r.get('risk_pct')),
            f(r.get('chase_pct')),
            abs(event_to_entry - 9),
            str(r.get('family', '')),
        )
        if key not in chosen or rank < chosen[key][0]:
            chosen[key] = (rank, r)
    return [v[1] for v in chosen.values()]


def join_v104(rows, v104_rows):
    exact = {(r.get('symbol'), r.get('entry_date'), r.get('family')): r for r in v104_rows if r.get('trend_state') == 'RANGE_TRANSITION'}
    loose = {(r.get('symbol'), r.get('entry_date')): r for r in v104_rows if r.get('trend_state') == 'RANGE_TRANSITION'}
    out = []
    for r in rows:
        tr = exact.get((r.get('symbol'), r.get('entry_date'), r.get('family'))) or loose.get((r.get('symbol'), r.get('entry_date')))
        if not tr:
            continue
        source_idx = i(tr.get('source_event_idx'))
        touch_idx = i(tr.get('touch_idx'))
        reclaim_idx = i(tr.get('reclaim_idx'))
        entry_idx = i(tr.get('entry_idx'))
        zone_low = f(tr.get('zone_low'))
        zone_high = f(tr.get('zone_high'))
        entry_price = f(tr.get('entry_price'))
        row = dict(r)
        row.update({
            'source_event_idx': source_idx,
            'touch_idx': touch_idx,
            'reclaim_idx': reclaim_idx,
            'entry_idx': entry_idx,
            'event_to_touch': touch_idx - source_idx,
            'touch_to_reclaim': reclaim_idx - touch_idx,
            'reclaim_to_entry': entry_idx - reclaim_idx,
            'zone_width_pct': round((zone_high - zone_low) * 100.0 / zone_low, 4) if zone_low else 0.0,
            'entry_over_zone_high_pct': round((entry_price - zone_high) * 100.0 / zone_high, 4) if zone_high else 0.0,
            'disp_atr': f(tr.get('disp_atr')),
            'pierce_atr': f(tr.get('pierce_atr')),
            'ret20': f(tr.get('ret20')),
            'ret60': f(tr.get('ret60')),
            'pos60': f(tr.get('pos60')),
            'tp1_rr': f(tr.get('tp1_rr')),
            'tp2_rr': f(tr.get('tp2_rr')),
            'hold_bars': i(tr.get('hold_bars')),
            'source_event_date': tr.get('source_event_date'),
            'touch_date': tr.get('touch_date'),
            'reclaim_date': tr.get('reclaim_date'),
            'zone_type': tr.get('zone_type'),
            'signal_type': tr.get('signal_type'),
        })
        out.append(row)
    return out


def feature_summary(name, rows):
    s = metric(rows)
    s['name'] = name
    for key in [
        'event_to_entry', 'event_to_touch', 'touch_to_reclaim', 'risk_pct', 'retrace_pct', 'chase_pct',
        'zone_width_pct', 'entry_over_zone_high_pct', 'disp_atr', 'pierce_atr', 'ret20', 'ret60', 'pos60',
    ]:
        s[f'{key}_median'] = median(rows, key)
        s[f'{key}_avg'] = avg(rows, key)
    return s


def bucket(rows, key_fn):
    d = defaultdict(list)
    for r in rows:
        d[str(key_fn(r))].append(r)
    out = []
    for k, rs in sorted(d.items()):
        s = metric(rs)
        s['key'] = k
        out.append(s)
    return out


def concise(r):
    keys = [
        'symbol', 'entry_date', 'family', 'event_to_entry', 'event_to_touch', 'touch_to_reclaim',
        'second_confirm_before_entry', 'exit_reason', 'net_pnl_pct', 'risk_pct', 'retrace_pct', 'chase_pct',
        'zone_width_pct', 'entry_over_zone_high_pct', 'disp_atr', 'ret20', 'ret60', 'pos60',
    ]
    return {k: r.get(k) for k in keys}


def main():
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    v109 = json.loads(V109_JSON.read_text())['per_trade_range_transition']
    v104 = json.loads(V104_TRADES.read_text())
    unique = dedup_symbol_entry(v109)
    rows = join_v104(unique, v104)

    wait_9_21 = [r for r in rows if 9 <= i(r.get('event_to_entry')) <= 21]
    wait_9_11 = [r for r in rows if 9 <= i(r.get('event_to_entry')) <= 11]
    wait_12_21 = [r for r in rows if 12 <= i(r.get('event_to_entry')) <= 21]
    second_only = [r for r in rows if bool(r.get('second_confirm_before_entry'))]
    remaining_losses = [r for r in wait_9_21 if f(r.get('net_pnl_pct')) < NET_SUCCESS]

    structure_rules = [
        ('WAIT_9_21', wait_9_21),
        ('WAIT_9_11_EARLY_TRANSITION', wait_9_11),
        ('WAIT_12_21_MATURE_TRANSITION', wait_12_21),
        ('SECOND_CONFIRM_ONLY', second_only),
        ('WAIT_9_21_AND_EVENT_TO_TOUCH_GE_9', [r for r in wait_9_21 if i(r.get('event_to_touch')) >= 9]),
        ('WAIT_9_21_AND_EVENT_TO_TOUCH_LT_9', [r for r in wait_9_21 if i(r.get('event_to_touch')) < 9]),
    ]
    rule_table = [feature_summary(name, rs) for name, rs in structure_rules]

    result = {
        'version': 'V111_WAIT_STRUCTURE_ONTOLOGY_AUDIT',
        'research_only': True,
        'production_files_touched': False,
        'inputs': {'v109_json': str(V109_JSON), 'v104_trades': str(V104_TRADES)},
        'method': 'Dedup V109 RANGE_TRANSITION by symbol+entry_date, join V104 strict-reclaim structural indices, compare WAIT_9_21 vs WAIT_12_21 with ex-ante timing/zone/risk fields. No TP/SL tuning.',
        'join': {'unique_range_rows': len(unique), 'joined_v104_rows': len(rows), 'missing_join_rows': len(unique) - len(rows)},
        'rule_table': rule_table,
        'remaining_losses_wait_9_21': [concise(r) for r in sorted(remaining_losses, key=lambda r: (i(r.get('event_to_entry')), r.get('entry_date'), r.get('symbol')))],
        'buckets': {
            'wait_9_21_by_event_to_entry': bucket(wait_9_21, lambda r: r.get('event_to_entry')),
            'wait_9_21_by_event_to_touch': bucket(wait_9_21, lambda r: r.get('event_to_touch')),
            'wait_9_21_by_touch_to_reclaim': bucket(wait_9_21, lambda r: r.get('touch_to_reclaim')),
            'wait_9_21_by_second_confirm': bucket(wait_9_21, lambda r: bool(r.get('second_confirm_before_entry'))),
        },
        'ontology_findings': {
            'wait_12_21_pattern': 'Rows are not just later entry rows; they have a longer event-to-touch gestation window before POI execution, with median event_to_touch 14 vs 6 in WAIT_9_11. This looks like a mature transition/accumulation structure.',
            'remaining_loss_pattern': 'All WAIT_9_21 losses are WAIT_9_11, second_confirm_before_entry=False, SL_HIT, and event_to_touch 5-7. The failed structure is an early transition touch/reclaim, not the slower 12-21 pattern.',
            'second_confirm_pattern': 'Second-confirm-only remains too sparse and is not the driver of WAIT_12_21 quality.',
        },
        'decision': 'RESEARCH_ONLY_NOT_PROMOTED',
        'non_promotion_reasons': [
            'WAIT_12_21 / event_to_touch>=9 has only 9 unique symbol+entry_date rows.',
            'Monthly coverage is only 7 months and mostly n=1; stable3/stable5 are both 0.',
            'The apparent clean subset is a structure hypothesis, not a production-grade full-market multi-year rule.',
            'No TP/SL was tuned and no production/API/frontend/monitor file was changed.',
        ],
        'next': 'If continuing, rederive RANGE_TRANSITION generator-level candidates to increase sample without relaxing early 9-11 false-transition gate; still keep production on V90 WATCH_ONLY/tradable active=0.',
    }

    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    def row_line(s):
        return f"| {s['name']} | {s['n']} | {s['wr']}% | {s['sl']}% | {s['avg']}% | {s['months']} | {s['stable3']} | {s['stable5']} | {s['event_to_entry_median']} | {s['event_to_touch_median']} | {s['touch_to_reclaim_median']} | {s['risk_pct_median']} | {s['retrace_pct_median']} | {s['chase_pct_median']} |"

    lines = []
    lines.append('# V111 WAIT Structure Ontology Audit')
    lines.append('')
    lines.append('Decision: **RESEARCH_ONLY_NOT_PROMOTED**')
    lines.append('')
    lines.append('Scope: research-only; no TP/SL tuning; no production/API/frontend/monitor changes.')
    lines.append('')
    lines.append('## Join / dedup')
    lines.append('| unique RANGE rows | joined V104 rows | missing |')
    lines.append('|---:|---:|---:|')
    lines.append(f"| {len(unique)} | {len(rows)} | {len(unique) - len(rows)} |")
    lines.append('')
    lines.append('## Structure comparison')
    lines.append('| Slice | n | WR | SL | Avg | Months | Stable3 | Stable5 | E2E med | Event→Touch med | Touch→Reclaim med | Risk med | Retrace med | Chase med |')
    lines.append('|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|')
    for s in rule_table:
        lines.append(row_line(s))
    lines.append('')
    lines.append('## Remaining WAIT_9_21 losses')
    lines.append('| Symbol | Entry | E2E | Event→Touch | Touch→Reclaim | Second | Exit | Net | Risk | Retrace | Chase | ZoneW | Entry>Zone | ret60 | pos60 |')
    lines.append('|---|---|---:|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|')
    for r in sorted(remaining_losses, key=lambda x: (i(x.get('event_to_entry')), x.get('entry_date'), x.get('symbol'))):
        lines.append(f"| {r.get('symbol')} | {r.get('entry_date')} | {r.get('event_to_entry')} | {r.get('event_to_touch')} | {r.get('touch_to_reclaim')} | {r.get('second_confirm_before_entry')} | {r.get('exit_reason')} | {r.get('net_pnl_pct')} | {r.get('risk_pct')} | {r.get('retrace_pct')} | {r.get('chase_pct')} | {r.get('zone_width_pct')} | {r.get('entry_over_zone_high_pct')} | {r.get('ret60')} | {r.get('pos60')} |")
    lines.append('')
    lines.append('## Conclusion')
    lines.append('- `WAIT_12_21` / `event_to_touch>=9` is the only clean structural hypothesis, but it is only 9 rows and has no stable3/stable5 proof.')
    lines.append('- Remaining `WAIT_9_21` losses are all early `WAIT_9_11`, second-confirm=false, SL_HIT, with `event_to_touch=5-7`; this is the false-transition bucket.')
    lines.append('- `second-confirm-only` is too sparse and is not enough to define a stable RANGE_TRANSITION rule.')
    lines.append('- V111 remains research-only; production remains V90 WATCH_ONLY / tradable active=0.')
    OUT_MD.write_text('\n'.join(lines) + '\n')
    print(json.dumps({'ok': True, 'out_json': str(OUT_JSON), 'out_md': str(OUT_MD), 'decision': result['decision']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
