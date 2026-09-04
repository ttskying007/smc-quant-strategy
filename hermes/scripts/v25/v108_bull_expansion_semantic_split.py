#!/usr/bin/env python3
"""V108 BULL_EXPANSION semantic split audit.

Research-only. Builds on V107C 750-bar breadth and V104 strict reclaim rows.
Focus:
- split BULL_EXPANSION into TREND_UP vs RANGE_TRANSITION structural behavior
- isolate RANGE_TRANSITION pseudo-structure
- audit event_to_entry 5-8 over-early confirmation
Does not write production/API/frontend/monitor files.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path('/root/.hermes')
OUT_JSON = ROOT / 'smc_audit' / 'v108_bull_expansion_semantic_split_20260619.json'
OUT_MD = ROOT / 'smc_audit' / 'v108_bull_expansion_semantic_split_20260619.md'

sys.path.append('/root/.hermes/scripts/v25')
import v107c_tradeable_regime_rederive as v107c  # noqa: E402


def f(x, default=0.0):
    try:
        if x is None or x == '':
            return default
        return float(x)
    except Exception:
        return default


def pct(a, b):
    return round(a * 100.0 / b, 2) if b else 0.0


def metric(rows):
    n = len(rows)
    vals = [f(r.get('net_pnl_pct')) for r in rows]
    months = defaultdict(list)
    for r in rows:
        months[str(r.get('entry_date'))[:6]].append(r)
    stable3 = stable5 = 0
    for ms in months.values():
        nn = len(ms)
        wr = pct(sum(f(x.get('net_pnl_pct')) >= 0.8 for x in ms), nn)
        sl = pct(sum(x.get('exit_reason') == 'SL_HIT' for x in ms), nn)
        if nn >= 3 and wr >= 70 and sl <= 30:
            stable3 += 1
        if nn >= 5 and wr >= 70 and sl <= 30:
            stable5 += 1
    return {
        'n': n,
        'wr': pct(sum(v >= 0.8 for v in vals), n),
        'sl': pct(sum(r.get('exit_reason') == 'SL_HIT' for r in rows), n),
        'avg': round(statistics.mean(vals), 4) if vals else 0.0,
        'median': round(statistics.median(vals), 4) if vals else 0.0,
        'cum': round(sum(vals), 4),
        'months': len(months),
        'stable3': stable3,
        'stable5': stable5,
    }


def group(rows, key):
    d = defaultdict(list)
    for r in rows:
        d[str(key(r))].append(r)
    out = []
    for k, rs in d.items():
        s = metric(rs)
        s['key'] = k
        out.append(s)
    out.sort(key=lambda x: (-x['n'], -x['wr'], -x['avg']))
    return out


def enrich_rows():
    rows = v107c.add_features(v107c.load_trades())
    entry_dates = sorted({str(r.get('entry_date')) for r in rows})
    market = v107c.compute_full_market_stats_750(entry_dates)
    for r in rows:
        r['market_v107c'] = market.get(str(r.get('entry_date')), {})
        r['tradeable_regime'] = v107c.classify_regime_v107c(r['market_v107c'])
        ev = int(r.get('entry_idx', 0)) - int(r.get('source_event_idx', r.get('event_idx', 0)))
        r['event_to_entry'] = ev
        if ev <= 5:
            r['event_timing_class'] = 'TOO_FAST_0_5'
        elif ev <= 8:
            r['event_timing_class'] = 'EARLY_5_8'
        elif ev <= 13:
            r['event_timing_class'] = 'CONFIRMED_8_13'
        elif ev <= 21:
            r['event_timing_class'] = 'MATURE_13_21'
        else:
            r['event_timing_class'] = 'LATE_GT_21'
        r['range_pseudo_flag'] = (
            r.get('tradeable_regime') == 'BULL_EXPANSION'
            and r.get('trend_state') == 'RANGE_TRANSITION'
            and r['event_timing_class'] in {'TOO_FAST_0_5', 'EARLY_5_8'}
        )
    return rows


def concise(rows, limit=80):
    keys = ['symbol','entry_date','family','trend_state','event_timing_class','event_to_entry','retrace_pct','risk_pct','chase_pct','disp_atr','exit_reason','net_pnl_pct','month']
    rows = sorted(rows, key=lambda r: (str(r.get('entry_date')), str(r.get('symbol'))))[:limit]
    return [{k: r.get(k) for k in keys} for r in rows]


def main():
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    rows = enrich_rows()
    bull = [r for r in rows if r.get('tradeable_regime') == 'BULL_EXPANSION']
    trend = [r for r in bull if r.get('trend_state') == 'TREND_UP']
    rng = [r for r in bull if r.get('trend_state') == 'RANGE_TRANSITION']
    early = [r for r in bull if r.get('event_timing_class') == 'EARLY_5_8']
    non_early = [r for r in bull if r.get('event_timing_class') != 'EARLY_5_8']
    confirmed_window = [r for r in bull if 8 < int(r.get('event_to_entry', 0)) <= 21]
    range_pseudo = [r for r in bull if r.get('range_pseudo_flag')]
    range_confirmed = [r for r in rng if 8 < int(r.get('event_to_entry', 0)) <= 21]

    rules = [
        ('BULL_EXPANSION_BASE', bull),
        ('TREND_UP_ONLY', trend),
        ('RANGE_TRANSITION_ONLY', rng),
        ('EARLY_5_8_ALL', early),
        ('NON_EARLY_EXCLUDE_5_8', non_early),
        ('CONFIRMED_8_21_ALL', confirmed_window),
        ('TREND_UP_CONFIRMED_8_21', [r for r in trend if 8 < int(r.get('event_to_entry', 0)) <= 21]),
        ('TREND_UP_RETRACE_20_70', [r for r in trend if 20 <= f(r.get('retrace_pct')) <= 70]),
        ('RANGE_PSEUDO_FAST_OR_EARLY', range_pseudo),
        ('RANGE_CONFIRMED_8_21', range_confirmed),
        ('RANGE_CONFIRMED_8_21_RETRACE_20_70', [r for r in range_confirmed if 20 <= f(r.get('retrace_pct')) <= 70]),
    ]
    rule_table = []
    for name, rs in rules:
        s = metric(rs)
        s['name'] = name
        rule_table.append(s)

    result = {
        'version': 'V108_BULL_EXPANSION_SEMANTIC_SPLIT',
        'research_only': True,
        'production_files_touched': False,
        'source': 'V104 strict reclaim trades + V107C 750-bar breadth',
        'decision': 'RESEARCH_ONLY_NOT_PROMOTED',
        'promotion_gate': {
            'required': 'n>=100, WR>=70, SL<=30, stable3>=12, no production pollution, T+1 clean',
            'passed': False,
            'reason': 'best structural subsets are high quality but n/month coverage remain below production gate',
        },
        'rule_table': rule_table,
        'trend_up_vs_range': {
            'trend_up': metric(trend),
            'range_transition': metric(rng),
            'trend_by_timing': group(trend, lambda r: r.get('event_timing_class')),
            'range_by_timing': group(rng, lambda r: r.get('event_timing_class')),
            'range_pseudo_rows': concise(range_pseudo),
        },
        'event_timing': group(bull, lambda r: r.get('event_timing_class')),
        'family_timing': group(bull, lambda r: f"{r.get('family')}|{r.get('event_timing_class')}"),
        'hard_findings': [
            'BULL_EXPANSION is the only broad tradable regime, but it is not homogeneous.',
            'TREND_UP is real expansion: materially higher WR and lower SL than RANGE_TRANSITION.',
            'RANGE_TRANSITION contains pseudo-structure when event_to_entry is 5-8 or faster; this bucket is the main false-confirmation source.',
            'event_to_entry 8-21 is the clean confirmation window; it improves quality but leaves insufficient stable monthly coverage.',
            'No V108 rule is promoted: this is a semantic audit artifact only.',
        ],
        'next_v109_contract': {
            'allowed_direction': 'rebuild RANGE_TRANSITION confirmation semantics only: require slower 8-21 confirmation or second structural break before entry',
            'forbidden_direction': 'do not adjust TP/SL or promote MIXED_CHOP small samples',
        },
    }
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    lines = ['# V108 BULL_EXPANSION Semantic Split', '', 'Decision: **RESEARCH_ONLY_NOT_PROMOTED**', '', '## Rule table', '| Rule | n | WR | SL | Avg | Median | Cum | Months | Stable3 | Stable5 |', '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for s in rule_table:
        lines.append(f"| {s['name']} | {s['n']} | {s['wr']}% | {s['sl']}% | {s['avg']}% | {s['median']}% | {s['cum']}% | {s['months']} | {s['stable3']} | {s['stable5']} |")
    lines += ['', '## TREND_UP timing', '| timing | n | WR | SL | Avg |', '|---|---:|---:|---:|---:|']
    for s in result['trend_up_vs_range']['trend_by_timing']:
        lines.append(f"| {s['key']} | {s['n']} | {s['wr']}% | {s['sl']}% | {s['avg']}% |")
    lines += ['', '## RANGE_TRANSITION timing', '| timing | n | WR | SL | Avg |', '|---|---:|---:|---:|---:|']
    for s in result['trend_up_vs_range']['range_by_timing']:
        lines.append(f"| {s['key']} | {s['n']} | {s['wr']}% | {s['sl']}% | {s['avg']}% |")
    lines += ['', '## Findings']
    for x in result['hard_findings']:
        lines.append(f'- {x}')
    lines += ['', '## Next V109 contract']
    for k, v in result['next_v109_contract'].items():
        lines.append(f'- {k}: {v}')
    OUT_MD.write_text('\n'.join(lines) + '\n')
    print(json.dumps({'out_json': str(OUT_JSON), 'out_md': str(OUT_MD), 'decision': result['decision'], 'rule_table': rule_table}, ensure_ascii=False, indent=2)[:12000])


if __name__ == '__main__':
    main()
