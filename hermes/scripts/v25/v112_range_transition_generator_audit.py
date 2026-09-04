#!/usr/bin/env python3
"""V112 RANGE_TRANSITION generator ceiling / duplicate-source audit.

Research-only continuation of V111.
- Do not tune TP/SL.
- Do not write production/API/frontend/monitor files.
- Audit whether the V111 mature-transition hypothesis can increase sample
  inside the existing V104 generator output, and where duplicate rows come from.
"""
from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path('/root/.hermes')
V104_TRADES = ROOT / 'smc_opt_v104_strict_reclaim' / 'v104_trades.json'
OUT_JSON = ROOT / 'smc_audit' / 'v112_range_transition_generator_audit_20260619.json'
OUT_MD = ROOT / 'smc_audit' / 'v112_range_transition_generator_audit_20260619.md'
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


def avg(rows, key):
    vals = [f(r.get(key)) for r in rows]
    return round(statistics.mean(vals), 4) if vals else 0.0


def median(rows, key):
    vals = [f(r.get(key)) for r in rows]
    return round(statistics.median(vals), 4) if vals else 0.0


def enrich(r):
    row = dict(r)
    source_idx = i(row.get('source_event_idx'))
    touch_idx = i(row.get('touch_idx'))
    reclaim_idx = i(row.get('reclaim_idx'))
    entry_idx = i(row.get('entry_idx'))
    row['event_to_entry'] = entry_idx - source_idx
    row['event_to_touch'] = touch_idx - source_idx
    row['touch_to_reclaim'] = reclaim_idx - touch_idx
    row['reclaim_to_entry'] = entry_idx - reclaim_idx
    return row


def metric(rows):
    months = defaultdict(list)
    for r in rows:
        months[month(r)].append(r)
    stable3 = stable5 = 0
    for rs in months.values():
        n = len(rs)
        wr = pct(sum(f(x.get('net_pnl_pct')) >= NET_SUCCESS for x in rs), n)
        sl = pct(sum(x.get('exit_reason') == 'SL_HIT' for x in rs), n)
        if n >= 3 and wr >= 70 and sl <= 30:
            stable3 += 1
        if n >= 5 and wr >= 70 and sl <= 30:
            stable5 += 1
    vals = [f(r.get('net_pnl_pct')) for r in rows]
    return {
        'n': len(rows),
        'wr': pct(sum(v >= NET_SUCCESS for v in vals), len(rows)),
        'sl': pct(sum(r.get('exit_reason') == 'SL_HIT' for r in rows), len(rows)),
        'avg': round(statistics.mean(vals), 4) if vals else 0.0,
        'median': round(statistics.median(vals), 4) if vals else 0.0,
        'months': len(months),
        'stable3': stable3,
        'stable5': stable5,
    }


def dedup(rows, mode):
    chosen = {}
    for r in rows:
        key = (r.get('symbol'), r.get('entry_date'))
        e2e = i(r.get('event_to_entry'))
        e2t = i(r.get('event_to_touch'))
        if mode == 'v110_rank':
            rank = (0 if 8 <= e2e <= 21 else 1, f(r.get('risk_pct')), f(r.get('chase_pct')), abs(e2e - 9), str(r.get('family', '')))
        elif mode == 'mature_rank':
            rank = (0 if e2t >= 9 else 1, 0 if 9 <= e2e <= 21 else 1, -e2t, f(r.get('risk_pct')), f(r.get('chase_pct')), str(r.get('family', '')))
        else:
            raise ValueError(mode)
        if key not in chosen or rank < chosen[key][0]:
            chosen[key] = (rank, r)
    return [v[1] for v in chosen.values()]


def summarize(name, rows):
    s = metric(rows)
    s['name'] = name
    for key in ['event_to_entry', 'event_to_touch', 'touch_to_reclaim', 'risk_pct', 'retrace_pct', 'chase_pct', 'ret60', 'pos60']:
        s[f'{key}_median'] = median(rows, key)
    return s


def buckets(rows, key):
    d = defaultdict(list)
    for r in rows:
        d[str(r.get(key))].append(r)
    out = []
    for k, rs in sorted(d.items(), key=lambda kv: (i(kv[0], 9999), kv[0])):
        s = metric(rs)
        s['key'] = k
        out.append(s)
    return out


def concise(r):
    return {
        'symbol': r.get('symbol'),
        'entry_date': r.get('entry_date'),
        'family': r.get('family'),
        'event_to_entry': r.get('event_to_entry'),
        'event_to_touch': r.get('event_to_touch'),
        'touch_to_reclaim': r.get('touch_to_reclaim'),
        'exit_reason': r.get('exit_reason'),
        'net_pnl_pct': f(r.get('net_pnl_pct')),
        'risk_pct': f(r.get('risk_pct')),
        'retrace_pct': f(r.get('retrace_pct')),
        'chase_pct': f(r.get('chase_pct')),
        'ret60': f(r.get('ret60')),
        'pos60': f(r.get('pos60')),
    }


def main():
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    all_trades = json.loads(V104_TRADES.read_text())
    raw = [enrich(r) for r in all_trades if r.get('trend_state') == 'RANGE_TRANSITION']
    unique_v110 = dedup(raw, 'v110_rank')
    unique_mature = dedup(raw, 'mature_rank')

    dup_groups = defaultdict(list)
    for r in raw:
        dup_groups[(r.get('symbol'), r.get('entry_date'))].append(r)
    duplicate_groups = [rs for rs in dup_groups.values() if len(rs) > 1]
    family_combo_counts = Counter(tuple(sorted(set(r.get('family') for r in rs))) for rs in duplicate_groups)

    rules = [
        ('RAW_RANGE_ALL', raw),
        ('UNIQUE_V110_RANK_ALL', unique_v110),
        ('UNIQUE_MATURE_RANK_ALL', unique_mature),
        ('UNIQUE_V110_EVENT_TO_TOUCH_GE9', [r for r in unique_v110 if i(r.get('event_to_touch')) >= 9]),
        ('UNIQUE_V110_EVENT_TO_TOUCH_GE8', [r for r in unique_v110 if i(r.get('event_to_touch')) >= 8]),
        ('UNIQUE_V110_E2E_12_21', [r for r in unique_v110 if 12 <= i(r.get('event_to_entry')) <= 21]),
        ('UNIQUE_V110_E2E_12_21_AND_EVENT_TO_TOUCH_GE9', [r for r in unique_v110 if 12 <= i(r.get('event_to_entry')) <= 21 and i(r.get('event_to_touch')) >= 9]),
        ('UNIQUE_V110_E2E_9_21_AND_EVENT_TO_TOUCH_GE9', [r for r in unique_v110 if 9 <= i(r.get('event_to_entry')) <= 21 and i(r.get('event_to_touch')) >= 9]),
    ]
    rule_table = [summarize(name, rows) for name, rows in rules]

    mature_rows = [r for r in unique_v110 if i(r.get('event_to_touch')) >= 9]
    mature_losses = [concise(r) for r in sorted(mature_rows, key=lambda r: (f(r.get('net_pnl_pct')), r.get('entry_date'), r.get('symbol'))) if f(r.get('net_pnl_pct')) < NET_SUCCESS]

    duplicate_examples = []
    for rs in sorted(duplicate_groups, key=lambda group: (group[0].get('entry_date'), group[0].get('symbol')))[:20]:
        duplicate_examples.append({
            'symbol': rs[0].get('symbol'),
            'entry_date': rs[0].get('entry_date'),
            'rows': [concise(r) for r in sorted(rs, key=lambda r: (str(r.get('family')), i(r.get('event_to_entry')), i(r.get('event_to_touch'))))],
        })

    result = {
        'version': 'V112_RANGE_TRANSITION_GENERATOR_AUDIT',
        'research_only': True,
        'production_files_touched': False,
        'inputs': {'v104_trades': str(V104_TRADES)},
        'method': 'Use V104 raw RANGE_TRANSITION generator output only. Compare raw vs ex-ante dedup, mature event_to_touch>=9 hypothesis, duplicate family sources. No TP/SL tuning and no production routing.',
        'generator_counts': {
            'raw_range_rows': len(raw),
            'unique_symbol_entry_rows_v110_rank': len(unique_v110),
            'unique_symbol_entry_rows_mature_rank': len(unique_mature),
            'duplicate_groups': len(duplicate_groups),
            'duplicate_rows': sum(len(rs) for rs in duplicate_groups),
            'extra_duplicate_rows': sum(len(rs) - 1 for rs in duplicate_groups),
            'family_combo_counts': {'+'.join(k): v for k, v in family_combo_counts.items()},
        },
        'rule_table': rule_table,
        'mature_losses': mature_losses,
        'buckets': {
            'unique_v110_by_event_to_touch': buckets(unique_v110, 'event_to_touch'),
            'unique_v110_by_event_to_entry': buckets(unique_v110, 'event_to_entry'),
            'mature_by_month': buckets(mature_rows, 'entry_date'),
        },
        'duplicate_examples': duplicate_examples,
        'decision': 'RESEARCH_ONLY_NOT_PROMOTED',
        'findings': {
            'existing_generator_ceiling': 'The current V104 RANGE_TRANSITION generator has 238 raw rows but only 182 unique symbol+entry_date rows; duplicate family emission is large and mostly REVERSAL+CONTINUATION duplicates.',
            'mature_hypothesis_expansion': 'Applying event_to_touch>=9 to all unique V104 RANGE_TRANSITION rows expands the V111 mature sample from 9 to 18 rows, but quality drops to WR 77.78 / SL 16.67 due to three mature losses.',
            'not_enough_for_production': '18 rows over 10 months still has no stable5 proof and includes 2023/2025 mature losses, so it is a generator research direction, not a production rule.',
        },
        'next': 'Next research should rederive RANGE_TRANSITION generator semantics: why mature event_to_touch rows still lose, and whether source event/POI type is structurally wrong. Continue read-only; no TP/SL tuning and no production routing.',
    }
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    def line(s):
        return f"| {s['name']} | {s['n']} | {s['wr']}% | {s['sl']}% | {s['avg']}% | {s['months']} | {s['stable3']} | {s['stable5']} | {s['event_to_entry_median']} | {s['event_to_touch_median']} | {s['touch_to_reclaim_median']} | {s['risk_pct_median']} | {s['retrace_pct_median']} | {s['chase_pct_median']} |"

    lines = [
        '# V112 RANGE_TRANSITION Generator Audit',
        '',
        'Decision: **RESEARCH_ONLY_NOT_PROMOTED**',
        '',
        'Scope: research-only; no TP/SL tuning; no production/API/frontend/monitor changes.',
        '',
        '## Generator duplicate source',
        '| raw rows | unique rows | duplicate groups | duplicate rows | extra duplicate rows | family combos |',
        '|---:|---:|---:|---:|---:|---|',
        f"| {len(raw)} | {len(unique_v110)} | {len(duplicate_groups)} | {sum(len(rs) for rs in duplicate_groups)} | {sum(len(rs)-1 for rs in duplicate_groups)} | {dict(result['generator_counts']['family_combo_counts'])} |",
        '',
        '## Rule comparison',
        '| Slice | n | WR | SL | Avg | Months | Stable3 | Stable5 | E2E med | Event→Touch med | Touch→Reclaim med | Risk med | Retrace med | Chase med |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for s in rule_table:
        lines.append(line(s))
    lines += [
        '',
        '## Mature event_to_touch>=9 losses',
        '| Symbol | Entry | Family | E2E | Event→Touch | Touch→Reclaim | Exit | Net | Risk | Retrace | Chase | ret60 | pos60 |',
        '|---|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|',
    ]
    for r in mature_losses:
        lines.append(f"| {r['symbol']} | {r['entry_date']} | {r['family']} | {r['event_to_entry']} | {r['event_to_touch']} | {r['touch_to_reclaim']} | {r['exit_reason']} | {r['net_pnl_pct']} | {r['risk_pct']} | {r['retrace_pct']} | {r['chase_pct']} | {r['ret60']} | {r['pos60']} |")
    lines += [
        '',
        '## Conclusion',
        '- The V104 generator emits heavy duplicate RANGE_TRANSITION rows: 238 raw -> 182 unique, 56 extra duplicate rows.',
        '- `event_to_touch>=9` expands the V111 clean bucket from 9 to 18 rows, but drops to 77.78% WR / 16.67% SL; current generator still mixes structurally wrong mature cases.',
        '- Duplicate source is mostly REVERSAL+CONTINUATION double emission; dedup is mandatory before any quality judgment.',
        '- V112 remains research-only; production remains V90 WATCH_ONLY / tradable active=0.',
    ]
    OUT_MD.write_text('\n'.join(lines) + '\n')
    print(json.dumps({'ok': True, 'out_json': str(OUT_JSON), 'out_md': str(OUT_MD), 'decision': result['decision']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
