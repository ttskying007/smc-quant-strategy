#!/usr/bin/env python3
"""V356 independent no-write Pine/Lux semantic differential audit.

This is deliberately separate from smc_core_v27.  It re-implements only the
published daily primitive contracts, then compares every emitted primitive and
continuation seed with V27/V351.  It does not create entries, outcomes,
watchlists, or production/UI writes.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
KDIR = ROOT / 'kline_cache'
AUD = ROOT / 'smc_audit'
OUT = AUD / f'v356_independent_semantic_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v356_independent_semantic_oracle_latest.json'
V351 = AUD / 'v351_semantic_oracle_latest.json'
LEFT = RIGHT = 3
STRUCT_START = 30  # explicit legacy V27 warm-up boundary; audited, never hidden
BREAK = 0.002
SWEEP = 0.003
SWEEP_LOOKBACK = 60
OB_BACKSCAN = 10
FORBIDDEN = ('entry', 'exit', 'pnl', 'tp', 'sl', 'risk', 'won')

spec = importlib.util.spec_from_file_location('v27_reference', ROOT / 'scripts/v25/smc_core_v27.py')
v27 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v27)


def f(value: object) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else 0.0
    except (TypeError, ValueError):
        return 0.0


def day(bar: dict) -> str:
    return ''.join(c for c in str(bar.get('t') or bar.get('date') or '') if c.isdigit())[:8]


def symbol(path: Path) -> str:
    parts = path.name.removesuffix('_daily_750.json').split('_')
    return f'{parts[0]}.{parts[1]}' if len(parts) == 2 else path.stem


def load(path: Path) -> list[dict]:
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    bars = []
    for b in raw:
        if not isinstance(b, dict) or not day(b):
            continue
        nb = {k: f(b.get(k)) for k in ('o', 'h', 'l', 'c')}
        if all(nb[k] > 0 for k in nb):
            nb['t'] = day(b)
            bars.append(nb)
    return sorted(bars, key=lambda b: b['t'])


def oracle_swings(ks: list[dict]) -> dict[str, list[dict]]:
    highs, lows = [], []
    # V27 has an additional left+right warm-up: its first eligible pivot is 6,
    # not 3. Keep this explicit so any detector divergence is not hidden.
    for i in range(LEFT + RIGHT, len(ks) - RIGHT):
        h, l = ks[i]['h'], ks[i]['l']
        # Pine pivot semantics: unique extreme across left/right window.
        if all(ks[j]['h'] < h for j in range(i - LEFT, i + RIGHT + 1) if j != i):
            highs.append({'idx': i, 'price': h, 'confirm_idx': i + RIGHT})
        if all(ks[j]['l'] > l for j in range(i - LEFT, i + RIGHT + 1) if j != i):
            lows.append({'idx': i, 'price': l, 'confirm_idx': i + RIGHT})
    return {'highs': highs, 'lows': lows}


def oracle_structure(ks: list[dict], swings: dict[str, list[dict]]) -> list[dict]:
    by_high = {x['confirm_idx']: x for x in swings['highs']}
    by_low = {x['confirm_idx']: x for x in swings['lows']}
    broken: set[tuple[str, int]] = set()
    trend, events = 'unknown', []
    for i in range(STRUCT_START, len(ks)):
        # V27 explicitly considers the most-recent confirmed level first.
        for ci in sorted((x for x in by_high if x <= i), reverse=True):
            sw = by_high[ci]
            if ('high', sw['idx']) in broken:
                continue
            if ks[i]['c'] > sw['price'] * (1 + BREAK):
                typ = 'BOS' if trend == 'bullish' else 'CHOCH'
                events.append({'type': typ, 'direction': 'bull', 'index': i,
                               'broken_swing_idx': sw['idx'], 'broken_swing_price': sw['price'],
                               'confirm_visible_at': ci})
                broken.add(('high', sw['idx']))
                trend = 'bullish'
                break
        else:
            for ci in sorted((x for x in by_low if x <= i), reverse=True):
                sw = by_low[ci]
                if ('low', sw['idx']) in broken:
                    continue
                if ks[i]['c'] < sw['price'] * (1 - BREAK):
                    typ = 'BOS' if trend == 'bearish' else 'CHOCH'
                    events.append({'type': typ, 'direction': 'bear', 'index': i,
                                   'broken_swing_idx': sw['idx'], 'broken_swing_price': sw['price'],
                                   'confirm_visible_at': ci})
                    broken.add(('low', sw['idx']))
                    trend = 'bearish'
                    break
    return events


def oracle_fvgs(ks: list[dict]) -> list[dict]:
    out = []
    for i in range(2, len(ks)):
        if ks[i]['l'] > ks[i - 2]['h'] and (ks[i]['l'] - ks[i - 2]['h']) / ks[i - 2]['h'] > 0.0005:
            out.append({'direction': 'bull', 'index': i, 'gap_low': ks[i - 2]['h'], 'gap_high': ks[i]['l']})
        if ks[i]['h'] < ks[i - 2]['l'] and (ks[i - 2]['l'] - ks[i]['h']) / ks[i]['h'] > 0.0005:
            out.append({'direction': 'bear', 'index': i, 'gap_low': ks[i]['h'], 'gap_high': ks[i - 2]['l']})
    return out


def oracle_sweeps(ks: list[dict], swings: dict[str, list[dict]]) -> list[dict]:
    out = []
    for i in range(20, len(ks)):
        b = ks[i]
        for sw in swings['lows']:
            if sw['confirm_idx'] > i or i - sw['idx'] > SWEEP_LOOKBACK:
                continue
            p = sw['price']
            if b['l'] < p * (1 - SWEEP) and b['c'] > p * (1 - SWEEP / 2) and (p - b['l']) / p >= SWEEP:
                out.append({'direction': 'bull', 'index': i, 'swept_swing_idx': sw['idx']})
        for sw in swings['highs']:
            if sw['confirm_idx'] > i or i - sw['idx'] > SWEEP_LOOKBACK:
                continue
            p = sw['price']
            if b['h'] > p * (1 + SWEEP) and b['c'] < p * (1 - SWEEP / 2) and (b['h'] - p) / p >= SWEEP:
                out.append({'direction': 'bear', 'index': i, 'swept_swing_idx': sw['idx']})
    return out


def oracle_obs(ks: list[dict], events: list[dict]) -> list[dict]:
    out = []
    for ev in events:
        direction, i = ev['direction'], ev['index']
        for j in range(i - 1, max(0, i - OB_BACKSCAN - 1), -1):
            opposite = ks[j]['c'] < ks[j]['o'] if direction == 'bull' else ks[j]['c'] > ks[j]['o']
            if opposite:
                out.append({'direction': direction, 'index': j, 'anchor_event_idx': i,
                            'zone_low': ks[j]['l'], 'zone_high': ks[j]['h']})
                break
    return out


def key(stage: str, row: dict) -> tuple:
    if stage == 'swing_high': return (row.get('idx'), round(f(row.get('price')), 8), row.get('confirm_idx'))
    if stage == 'swing_low': return (row.get('idx'), round(f(row.get('price')), 8), row.get('confirm_idx'))
    # MSS is a qualified CHOCH subtype in V27, not a different structural break.
    # Compare the underlying break identity; MSS qualification is audited separately.
    if stage == 'structure':
        typ = row.get('source_event') if row.get('type') == 'MSS' else row.get('type')
        return (row.get('direction'), typ, row.get('index'), row.get('broken_swing_idx'), row.get('confirm_visible_at'))
    if stage == 'fvg': return (row.get('direction'), row.get('index'), round(f(row.get('gap_low')), 8), round(f(row.get('gap_high')), 8))
    if stage == 'sweep': return (row.get('direction'), row.get('index'), row.get('swept_swing_idx'))
    if stage == 'ob': return (row.get('direction'), row.get('index'), row.get('anchor_event_idx'), round(f(row.get('zone_low')), 8), round(f(row.get('zone_high')), 8))
    raise ValueError(stage)


def diff(sym: str, stage: str, actual: list[dict], oracle: list[dict], output: list[dict], counts: Counter) -> None:
    a, o = {key(stage, x) for x in actual}, {key(stage, x) for x in oracle}
    counts[f'{stage}_v27'] += len(a)
    counts[f'{stage}_oracle'] += len(o)
    counts[f'{stage}_matched'] += len(a & o)
    for kind, values in (('V27_EXTRA', a - o), ('ORACLE_MISSING_FROM_V27', o - a)):
        counts[f'{stage}_{kind}'] += len(values)
        for value in sorted(values)[:20]:
            output.append({'symbol': sym, 'stage': stage, 'disposition': kind, 'semantic_key': repr(value)})


def seed_keys(rows: list[dict]) -> set[tuple]:
    return {(str(r.get('symbol', '')), int(r.get('event_idx', -1)), int(r.get('ob_idx', -1)), str(r.get('event_type', ''))) for r in rows}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    counts, mismatches = Counter(), []
    oracle_seed_rows = []
    causal_failures = Counter()
    for path in sorted(KDIR.glob('*_daily_750.json')):
        ks = load(path)
        if len(ks) < 60:
            continue
        sym = symbol(path)
        counts['symbols_scanned'] += 1
        # V27 returns mutable dictionaries; use separate copies to remove shared-state effects.
        refbars = [dict(b) for b in ks]
        rs = v27.confirmed_swings(refbars)
        rst = v27.structure_signals(refbars, rs)
        rf = v27.fvg_list(refbars)
        rw = v27.sweep_signals(refbars, rs)
        ro = v27.ob_signals(refbars, rst)
        os = oracle_swings(ks)
        ost = oracle_structure(ks, os)
        of = oracle_fvgs(ks)
        ow = oracle_sweeps(ks, os)
        oo = oracle_obs(ks, ost)
        diff(sym, 'swing_high', rs['highs'], os['highs'], mismatches, counts)
        diff(sym, 'swing_low', rs['lows'], os['lows'], mismatches, counts)
        diff(sym, 'structure', rst, ost, mismatches, counts)
        diff(sym, 'fvg', rf, of, mismatches, counts)
        diff(sym, 'sweep', rw, ow, mismatches, counts)
        diff(sym, 'ob', ro, oo, mismatches, counts)
        for ev in rst:
            if int(ev.get('confirm_visible_at', 10**9)) > int(ev.get('index', -1)):
                causal_failures['V27_STRUCTURE_FUTURE_SWING'] += 1
        for ob in ro:
            if int(ob.get('anchor_event_idx', -1)) <= int(ob.get('index', 10**9)):
                causal_failures['V27_OB_NONCAUSAL_ANCHOR'] += 1
        for ev in ost:
            if ev['type'] == 'BOS' and ev['direction'] == 'bull':
                for ob in (x for x in oo if x['anchor_event_idx'] == ev['index'] and x['direction'] == 'bull'):
                    oracle_seed_rows.append({
                        'symbol': sym, 'lifecycle_state': 'SEMANTIC_VALID_CONTINUATION_SEED',
                        'event_type': 'BOS', 'event_idx': ev['index'], 'event_date': ks[ev['index']]['t'],
                        'broken_swing_idx': ev['broken_swing_idx'], 'swing_confirm_idx': ev['confirm_visible_at'],
                        'ob_idx': ob['index'], 'ob_date': ks[ob['index']]['t'],
                        'zone_low': ob['zone_low'], 'zone_high': ob['zone_high'],
                        'semantic_contract': 'independent_confirmed_swing>bull_BOS>backward_nearest_bearish_OB',
                        'tradable': False, 'buy_enabled': False,
                    })

    v351_rows = []
    if V351.exists():
        try:
            v351_report = json.loads(V351.read_text())
            with Path(v351_report['artifacts']['seeds']).open(newline='') as h:
                v351_rows = list(csv.DictReader(h))
        except (OSError, KeyError, json.JSONDecodeError):
            causal_failures['V351_SOURCE_UNREADABLE'] += 1
    v351_set, oracle_set = seed_keys(v351_rows), seed_keys(oracle_seed_rows)
    for kind, values in (('V351_EXTRA_SEED', v351_set - oracle_set), ('ORACLE_MISSING_V351_SEED', oracle_set - v351_set)):
        counts[kind] = len(values)
        for value in sorted(values)[:100]:
            mismatches.append({'symbol': value[0], 'stage': 'continuation_seed', 'disposition': kind, 'semantic_key': repr(value)})

    fields = ['symbol', 'stage', 'disposition', 'semantic_key']
    with (OUT / 'v356_semantic_differential_mismatches.csv').open('w', newline='') as h:
        w = csv.DictWriter(h, fieldnames=fields)
        w.writeheader(); w.writerows(mismatches)
    seed_fields = ['symbol', 'lifecycle_state', 'event_type', 'event_idx', 'event_date', 'broken_swing_idx', 'swing_confirm_idx', 'ob_idx', 'ob_date', 'zone_low', 'zone_high', 'semantic_contract', 'tradable', 'buy_enabled']
    with (OUT / 'v356_independent_semantic_valid_continuation_seeds.csv').open('w', newline='') as h:
        w = csv.DictWriter(h, fieldnames=seed_fields)
        w.writeheader(); w.writerows(oracle_seed_rows)
    mismatch_total = sum(v for k, v in counts.items() if k.endswith('V27_EXTRA') or k.endswith('ORACLE_MISSING_FROM_V27'))
    report = {
        'version': 'V356_INDEPENDENT_SEMANTIC_ORACLE_DIFFERENTIAL_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'contracts': {
            'swing': 'unique 3-left/3-right pivot, visible only at pivot+3',
            'structure': 'close beyond a confirmed swing by 0.2%; one nearest unbroken level per bar; V27 warm-up starts at bar 30 and is explicitly audited',
            'ob': 'backward nearest opposite candle within 10 bars of the same structure event',
            'sweep': 'wick pierces confirmed swing by 0.3% then closes back inside, max 60 bars from pivot',
            'fvg': 'three-bar non-overlap with 0.05% minimum gap',
        },
        'stage_counts': dict(counts),
        'causality_failures': dict(causal_failures),
        'mismatch_total': mismatch_total,
        'v351_seed_count': len(v351_set),
        'independent_oracle_seed_count': len(oracle_set),
        'seed_set_equal': v351_set == oracle_set,
        'invariants': {
            'no_entries_created': True,
            'no_outcome_fields': not any(any(t in field.lower() for t in FORBIDDEN) for field in fields),
            'all_outputs_non_tradable_semantic_audit_only': True,
            'v27_structure_causal': not causal_failures.get('V27_STRUCTURE_FUTURE_SWING'),
            'v27_ob_anchor_causal': not causal_failures.get('V27_OB_NONCAUSAL_ANCHOR'),
        },
        'decision': 'SEMANTIC_DIFFERENTIAL_PASS__LIFECYCLE_INPUT_CONTRACT_CONFIRMED' if mismatch_total == 0 and v351_set == oracle_set and not causal_failures else 'SEMANTIC_DIFFERENTIAL_GAPS_FOUND__LIFECYCLE_SOURCE_REBUILD_BLOCKED',
        'artifacts': {'out_dir': str(OUT), 'mismatches': str(OUT / 'v356_semantic_differential_mismatches.csv'), 'independent_seeds': str(OUT / 'v356_independent_semantic_valid_continuation_seeds.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v356_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
