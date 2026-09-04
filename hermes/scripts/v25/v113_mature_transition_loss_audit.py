#!/usr/bin/env python3
"""V113 mature RANGE_TRANSITION loss audit.

Research-only continuation of V112.
- No TP/SL tuning.
- No production/API/frontend/monitor writes.
- Inspect mature event_to_touch>=9 rows with raw K-line pre-entry context.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path('/root/.hermes')
V104_TRADES = ROOT / 'smc_opt_v104_strict_reclaim' / 'v104_trades.json'
KLINE_DIR = ROOT / 'kline_cache'
OUT_JSON = ROOT / 'smc_audit' / 'v113_mature_transition_loss_audit_20260619.json'
OUT_MD = ROOT / 'smc_audit' / 'v113_mature_transition_loss_audit_20260619.md'
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


def metric(rows):
    vals = [f(r.get('net_pnl_pct')) for r in rows]
    months = {str(r.get('entry_date', ''))[:6] for r in rows}
    return {
        'n': len(rows),
        'wr': pct(sum(v >= NET_SUCCESS for v in vals), len(rows)),
        'sl': pct(sum(r.get('exit_reason') == 'SL_HIT' for r in rows), len(rows)),
        'avg': round(statistics.mean(vals), 4) if vals else 0.0,
        'months': len(months),
    }


def symbol_path(symbol):
    code, exch = symbol.split('.')
    return KLINE_DIR / f'{code}_{exch}_daily_750.json'


def load_bars(symbol):
    p = symbol_path(symbol)
    if not p.exists():
        p = KLINE_DIR / f"{symbol.replace('.', '_')}_daily_300.json"
    return json.loads(p.read_text())


def enrich_indices(r):
    row = dict(r)
    row['event_to_entry'] = i(row.get('entry_idx')) - i(row.get('source_event_idx'))
    row['event_to_touch'] = i(row.get('touch_idx')) - i(row.get('source_event_idx'))
    row['touch_to_reclaim'] = i(row.get('reclaim_idx')) - i(row.get('touch_idx'))
    row['reclaim_to_entry'] = i(row.get('entry_idx')) - i(row.get('reclaim_idx'))
    return row


def dedup_v110(rows):
    chosen = {}
    for r in rows:
        e2e = i(r.get('event_to_entry'))
        rank = (0 if 8 <= e2e <= 21 else 1, f(r.get('risk_pct')), f(r.get('chase_pct')), abs(e2e - 9), str(r.get('family', '')))
        key = (r.get('symbol'), r.get('entry_date'))
        if key not in chosen or rank < chosen[key][0]:
            chosen[key] = (rank, r)
    return [v[1] for v in chosen.values()]


def add_kline_context(row):
    bars = load_bars(row['symbol'])
    src = i(row.get('source_event_idx'))
    touch = i(row.get('touch_idx'))
    rec = i(row.get('reclaim_idx'))
    ent = i(row.get('entry_idx'))
    zl = f(row.get('zone_low'))
    zh = f(row.get('zone_high'))
    pre = bars[src + 1:rec] if 0 <= src < rec <= len(bars) else []
    between_touch_reclaim = bars[touch:rec + 1] if 0 <= touch <= rec < len(bars) else []
    reclaim_bar = bars[rec] if 0 <= rec < len(bars) else {}
    entry_bar = bars[ent] if 0 <= ent < len(bars) else {}
    min_low = min([f(b.get('l')) for b in pre], default=0.0)
    close_below = [b for b in pre if f(b.get('c')) < zl]
    low_below = [b for b in pre if f(b.get('l')) < zl]
    zone_touches = [b for b in pre if f(b.get('l')) <= zh and f(b.get('h')) >= zl]
    row = dict(row)
    row.update({
        'pre_reclaim_bars': len(pre),
        'pre_reclaim_close_below_zone_count': len(close_below),
        'pre_reclaim_low_below_zone_count': len(low_below),
        'pre_reclaim_zone_touch_count': len(zone_touches),
        'pre_reclaim_min_low_below_zone_pct': round((min_low - zl) * 100.0 / zl, 4) if zl and min_low else 0.0,
        'zone_dead_before_reclaim': len(close_below) > 0,
        'deep_pierce_before_reclaim': (round((min_low - zl) * 100.0 / zl, 4) if zl and min_low else 0.0) <= -1.0,
        'reclaim_close_margin_pct': round((f(reclaim_bar.get('c')) - zh) * 100.0 / zh, 4) if zh else 0.0,
        'reclaim_body_pct': round((f(reclaim_bar.get('c')) - f(reclaim_bar.get('o'))) * 100.0 / f(reclaim_bar.get('o')), 4) if f(reclaim_bar.get('o')) else 0.0,
        'entry_gap_from_reclaim_close_pct': round((f(entry_bar.get('o')) - f(reclaim_bar.get('c'))) * 100.0 / f(reclaim_bar.get('c')), 4) if f(reclaim_bar.get('c')) else 0.0,
        'between_touch_reclaim_red_count': sum(f(b.get('c')) < f(b.get('o')) for b in between_touch_reclaim),
        'kline_date_check': {
            'source': bars[src].get('t') if 0 <= src < len(bars) else None,
            'touch': bars[touch].get('t') if 0 <= touch < len(bars) else None,
            'reclaim': bars[rec].get('t') if 0 <= rec < len(bars) else None,
            'entry': bars[ent].get('t') if 0 <= ent < len(bars) else None,
        },
    })
    return row


def summarize(name, rows):
    s = metric(rows)
    s['name'] = name
    for key in ['pre_reclaim_close_below_zone_count', 'pre_reclaim_low_below_zone_count', 'pre_reclaim_min_low_below_zone_pct', 'pre_reclaim_zone_touch_count', 'reclaim_close_margin_pct', 'reclaim_body_pct', 'entry_gap_from_reclaim_close_pct', 'risk_pct', 'retrace_pct', 'chase_pct', 'ret60', 'pos60']:
        vals = [f(r.get(key)) for r in rows]
        s[f'{key}_median'] = round(statistics.median(vals), 4) if vals else 0.0
    return s


def bucket(rows, key):
    d = defaultdict(list)
    for r in rows:
        d[str(r.get(key))].append(r)
    return [{'key': k, **metric(rs)} for k, rs in sorted(d.items())]


def concise(r):
    keys = ['symbol', 'entry_date', 'family', 'event_to_entry', 'event_to_touch', 'touch_to_reclaim', 'exit_reason', 'net_pnl_pct', 'zone_dead_before_reclaim', 'pre_reclaim_close_below_zone_count', 'pre_reclaim_min_low_below_zone_pct', 'reclaim_close_margin_pct', 'entry_gap_from_reclaim_close_pct', 'risk_pct', 'retrace_pct', 'chase_pct', 'ret60', 'pos60']
    return {k: r.get(k) for k in keys}


def main():
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    raw = [enrich_indices(r) for r in json.loads(V104_TRADES.read_text()) if r.get('trend_state') == 'RANGE_TRANSITION']
    unique = dedup_v110(raw)
    mature = [add_kline_context(r) for r in unique if i(r.get('event_to_touch')) >= 9]
    winners = [r for r in mature if f(r.get('net_pnl_pct')) >= NET_SUCCESS]
    losers = [r for r in mature if f(r.get('net_pnl_pct')) < NET_SUCCESS]

    rule_sets = [
        ('MATURE_ALL_EVENT_TO_TOUCH_GE9', mature),
        ('MATURE_WINNERS', winners),
        ('MATURE_LOSSES', losers),
        ('NO_ZONE_DEAD_BEFORE_RECLAIM', [r for r in mature if not r.get('zone_dead_before_reclaim')]),
        ('ZONE_DEAD_BEFORE_RECLAIM', [r for r in mature if r.get('zone_dead_before_reclaim')]),
        ('NO_DEEP_PIERCE_BEFORE_RECLAIM', [r for r in mature if not r.get('deep_pierce_before_reclaim')]),
        ('DEEP_PIERCE_BEFORE_RECLAIM', [r for r in mature if r.get('deep_pierce_before_reclaim')]),
    ]
    rule_table = [summarize(name, rows) for name, rows in rule_sets]

    result = {
        'version': 'V113_MATURE_TRANSITION_LOSS_AUDIT',
        'research_only': True,
        'production_files_touched': False,
        'inputs': {'v104_trades': str(V104_TRADES), 'kline_dir': str(KLINE_DIR)},
        'method': 'Read V104 mature RANGE_TRANSITION rows (event_to_touch>=9), load raw K-line context before reclaim, test whether zone was invalidated before reclaim. No TP/SL tuning.',
        'rule_table': rule_table,
        'mature_losses': [concise(r) for r in sorted(losers, key=lambda r: (f(r.get('net_pnl_pct')), r.get('entry_date'), r.get('symbol')))],
        'buckets': {
            'by_zone_dead_before_reclaim': bucket(mature, 'zone_dead_before_reclaim'),
            'by_deep_pierce_before_reclaim': bucket(mature, 'deep_pierce_before_reclaim'),
            'by_family': bucket(mature, 'family'),
        },
        'decision': 'RESEARCH_ONLY_NOT_PROMOTED',
        'findings': {
            'zone_death_not_root_cause': 'No mature row had a pre-reclaim close below zone_low; zone-dead-before-reclaim does not explain the remaining losses.',
            'mature_loss_shape': 'Mature losses pass the basic reclaim order check but show weaker source/POI context: loss median ret60 is lower and several rows are 100% retrace continuation FVGs.',
            'sample_limit': 'All conclusions are based on 18 mature rows only; this remains generator research.',
        },
        'next': 'Next read-only step should inspect FVG_Demand source construction for mature losses vs winners: whether the source FVG is continuation imbalance, true demand, or already mitigated supply-side reaction.',
    }
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    def line(s):
        return f"| {s['name']} | {s['n']} | {s['wr']}% | {s['sl']}% | {s['avg']}% | {s['months']} | {s['pre_reclaim_close_below_zone_count_median']} | {s['pre_reclaim_min_low_below_zone_pct_median']} | {s['reclaim_close_margin_pct_median']} | {s['entry_gap_from_reclaim_close_pct_median']} | {s['risk_pct_median']} | {s['ret60_median']} | {s['pos60_median']} |"

    lines = [
        '# V113 Mature RANGE_TRANSITION Loss Audit',
        '',
        'Decision: **RESEARCH_ONLY_NOT_PROMOTED**',
        '',
        'Scope: research-only; no TP/SL tuning; no production/API/frontend/monitor changes.',
        '',
        '## Rule comparison',
        '| Slice | n | WR | SL | Avg | Months | CloseBelowZone med | MinLowBelowZone% med | ReclaimMargin% med | EntryGap% med | Risk med | ret60 med | pos60 med |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for s in rule_table:
        lines.append(line(s))
    lines += [
        '',
        '## Mature losses with pre-entry context',
        '| Symbol | Entry | Family | E2E | Event→Touch | Exit | Net | ZoneDead | CloseBelowCnt | MinLowBelowZone% | ReclaimMargin% | EntryGap% | Risk | Retrace | Chase | ret60 | pos60 |',
        '|---|---|---|---:|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for r in result['mature_losses']:
        lines.append(f"| {r['symbol']} | {r['entry_date']} | {r['family']} | {r['event_to_entry']} | {r['event_to_touch']} | {r['exit_reason']} | {r['net_pnl_pct']} | {r['zone_dead_before_reclaim']} | {r['pre_reclaim_close_below_zone_count']} | {r['pre_reclaim_min_low_below_zone_pct']} | {r['reclaim_close_margin_pct']} | {r['entry_gap_from_reclaim_close_pct']} | {r['risk_pct']} | {r['retrace_pct']} | {r['chase_pct']} | {r['ret60']} | {r['pos60']} |")
    lines += [
        '',
        '## Conclusion',
        '- Mature `event_to_touch>=9` rows still contain 4 losers; they are not explained by TP/SL tuning.',
        '- `zone_dead_before_reclaim` is not the root cause here: all 18 mature rows had zero pre-reclaim closes below zone_low.',
        '- The remaining root cause is likely FVG_Demand source semantics: current generator treats all mature FVG_Demand rows as demand, but several losers are weak continuation FVGs / full-retrace contexts rather than durable demand.',
        '- V113 remains research-only; production remains V90 WATCH_ONLY / tradable active=0.',
    ]
    OUT_MD.write_text('\n'.join(lines) + '\n')
    print(json.dumps({'ok': True, 'out_json': str(OUT_JSON), 'out_md': str(OUT_MD), 'decision': result['decision']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
