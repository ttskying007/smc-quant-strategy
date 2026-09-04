#!/usr/bin/env python3
"""V351 no-write SMC Semantic Oracle: audit daily Pine/LuxAlgo signal semantics.

This is not a strategy, backtest, scanner, or entry generator.  It independently
re-derives the observable contracts for V27 daily signals and emits only
SEMANTIC_VALID continuation lifecycle seeds.  No production/UI/watchlist writes.
"""
from __future__ import annotations
import csv, importlib.util, json, math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
KDIR = ROOT / 'kline_cache'
AUD = ROOT / 'smc_audit'
OUT = AUD / f"v351_semantic_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST = AUD / 'v351_semantic_oracle_latest.json'

spec = importlib.util.spec_from_file_location('v27', ROOT / 'scripts/v25/smc_core_v27.py')
v27 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v27)


def num(bar, key):
    try:
        value = float(bar.get(key, 0))
        return value if math.isfinite(value) else 0.0
    except (TypeError, ValueError):
        return 0.0


def day(bar):
    return ''.join(c for c in str(bar.get('t') or bar.get('date') or '') if c.isdigit())[:8]


def load(path):
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return []
    bars = [b for b in raw if day(b) and all(num(b, k) > 0 for k in ('o', 'h', 'l', 'c'))]
    return sorted(bars, key=day)


def symbol(path):
    parts = path.name.replace('_daily_750.json', '').split('_')
    return f'{parts[0]}.{parts[1]}' if len(parts) == 2 else path.stem


def atr(ks, i, period=14):
    if i < 2:
        return 0.0
    values = []
    for j in range(max(1, i - period + 1), i + 1):
        values.append(max(num(ks[j], 'h') - num(ks[j], 'l'),
                          abs(num(ks[j], 'h') - num(ks[j - 1], 'c')),
                          abs(num(ks[j], 'l') - num(ks[j - 1], 'c'))))
    return sum(values) / len(values) if values else 0.0


def validate_swings(ks, swings):
    bad = []
    for side, field, cmp in [('highs', 'h', 'high'), ('lows', 'l', 'low')]:
        for swing in swings.get(side, []):
            i, confirm = swing.get('idx', -1), swing.get('confirm_idx', -1)
            if not (3 <= i < len(ks) - 3 and confirm == i + 3):
                bad.append((side, i, 'CONFIRMATION_INDEX')); continue
            candidate = num(ks[i], field)
            left = [num(ks[j], field) for j in range(i - 3, i)]
            right = [num(ks[j], field) for j in range(i + 1, i + 4)]
            if side == 'highs':
                valid = candidate > max(left) and candidate >= max(right)
            else:
                valid = candidate < min(left) and candidate <= min(right)
            if not valid:
                bad.append((side, i, 'PIVOT_GEOMETRY'))
    return bad


def validate_structure(ks, swings, events):
    high = {x['idx']: x for x in swings.get('highs', [])}
    low = {x['idx']: x for x in swings.get('lows', [])}
    bad = []
    for ev in events:
        i, si, direction = ev.get('index', -1), ev.get('broken_swing_idx', -1), ev.get('direction')
        source = high.get(si) if direction == 'bull' else low.get(si)
        if source is None or source.get('confirm_idx', len(ks)) > i:
            bad.append((i, 'STRUCTURE_UNCONFIRMED_SWING')); continue
        threshold = source['price'] * (1 + .002 if direction == 'bull' else 1 - .002)
        close = num(ks[i], 'c') if 0 <= i < len(ks) else 0
        if (direction == 'bull' and close <= threshold) or (direction == 'bear' and close >= threshold):
            bad.append((i, 'STRUCTURE_BREAK_GEOMETRY'))
        if ev.get('type') not in {'BOS', 'CHOCH', 'MSS'}:
            bad.append((i, 'UNKNOWN_STRUCTURE_TYPE'))
    return bad


def validate_fvgs(ks, fvgs):
    bad = []
    for fvg in fvgs:
        i = fvg.get('index', -1)
        if i < 2 or i >= len(ks):
            bad.append((i, 'FVG_INDEX')); continue
        h0, l0 = num(ks[i - 2], 'h'), num(ks[i - 2], 'l')
        h2, l2 = num(ks[i], 'h'), num(ks[i], 'l')
        if fvg.get('direction') == 'bull':
            valid = l2 > h0 and abs(num(fvg, 'gap_low') - h0) < 1e-8 and abs(num(fvg, 'gap_high') - l2) < 1e-8
        else:
            valid = h2 < l0 and abs(num(fvg, 'gap_low') - h2) < 1e-8 and abs(num(fvg, 'gap_high') - l0) < 1e-8
        if not valid:
            bad.append((i, 'FVG_THREE_BAR_GEOMETRY'))
    return bad


def validate_sweeps(ks, swings, sweeps):
    lows = {x['idx']: x for x in swings.get('lows', [])}
    highs = {x['idx']: x for x in swings.get('highs', [])}
    bad = []
    for sweep in sweeps:
        i, si, direction = sweep.get('index', -1), sweep.get('swept_swing_idx', -1), sweep.get('direction')
        source = lows.get(si) if direction == 'bull' else highs.get(si)
        if source is None or source.get('confirm_idx', len(ks)) > i:
            bad.append((i, 'SWEEP_UNCONFIRMED_LIQUIDITY')); continue
        b, price = ks[i], source['price']
        valid = (num(b, 'l') < price * .997 and num(b, 'c') > price * .9985) if direction == 'bull' else (num(b, 'h') > price * 1.003 and num(b, 'c') < price * .9985)
        if not valid:
            bad.append((i, 'SWEEP_WICK_RECLAIM_GEOMETRY'))
    return bad


def validate_obs(ks, events, obs):
    event_by_idx = {e['index']: e for e in events}
    bad = []
    for ob in obs:
        ai, oi, direction = ob.get('anchor_event_idx', -1), ob.get('index', -1), ob.get('direction')
        ev = event_by_idx.get(ai)
        if ev is None or not (0 <= oi < ai <= len(ks) - 1) or ai - oi > 10:
            bad.append((oi, 'OB_INVALID_ANCHOR')); continue
        expected_bear = direction == 'bull'
        ob_bear = num(ks[oi], 'c') < num(ks[oi], 'o')
        if ob_bear != expected_bear:
            bad.append((oi, 'OB_NOT_OPPOSITE_CANDLE')); continue
        for j in range(oi + 1, ai):
            is_opposite = num(ks[j], 'c') < num(ks[j], 'o') if expected_bear else num(ks[j], 'c') > num(ks[j], 'o')
            if is_opposite:
                bad.append((oi, 'OB_NOT_NEAREST_OPPOSITE')); break
    return bad


def candidate_seed(sym, ks, signals, semantic_bad):
    invalid_event = {i for i, reason in semantic_bad['structure']}
    invalid_ob = {i for i, reason in semantic_bad['ob']}
    obs_by_event = {}
    for ob in signals['obs']:
        if ob.get('direction') == 'bull' and ob.get('index') not in invalid_ob:
            obs_by_event.setdefault(ob.get('anchor_event_idx'), []).append(ob)
    rows = []
    for ev in signals['structure']:
        i = ev.get('index', -1)
        if ev.get('type') != 'BOS' or ev.get('direction') != 'bull' or i in invalid_event:
            continue
        for ob in obs_by_event.get(i, []):
            rows.append({'symbol': sym, 'lifecycle_state': 'SEMANTIC_VALID_CONTINUATION_SEED',
                         'event_type': 'BOS', 'event_idx': i, 'event_date': day(ks[i]),
                         'broken_swing_idx': ev.get('broken_swing_idx'),
                         'swing_confirm_idx': ev.get('confirm_visible_at'),
                         'ob_idx': ob.get('index'), 'ob_date': day(ks[ob['index']]),
                         'zone_low': ob.get('zone_low'), 'zone_high': ob.get('zone_high'),
                         'semantic_contract': 'confirmed_swing>bull_BOS>backward_nearest_bearish_OB',
                         'tradable': False, 'buy_enabled': False})
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    counts, failures, seeds = Counter(), Counter(), []
    for path in sorted(KDIR.glob('*_daily_750.json')):
        ks = load(path)
        if len(ks) < 60:
            continue
        counts['symbols_scanned'] += 1
        # Oracle scope intentionally excludes BPR/OTE/PO3: those are not part of
        # the continuation generator contract and BPR's cross-FVG pairing is O(n²).
        # This preserves the exact V27 definitions for the five audited primitives.
        oracle_bars = [dict(x) for x in ks]
        swings = v27.confirmed_swings(oracle_bars)
        structure = v27.structure_signals(oracle_bars, swings)
        fvgs = v27.fvg_list(oracle_bars)
        sweeps = v27.sweep_signals(oracle_bars, swings)
        obs = v27.ob_signals(oracle_bars, structure)
        result = {'swings': swings, 'structure': structure, 'fvgs': fvgs, 'sweeps': sweeps, 'obs': obs}
        checks = {'swing': validate_swings(ks, result['swings']),
                  'structure': validate_structure(ks, result['swings'], result['structure']),
                  'fvg': validate_fvgs(ks, result['fvgs']),
                  'sweep': validate_sweeps(ks, result['swings'], result['sweeps']),
                  'ob': validate_obs(ks, result['structure'], result['obs'])}
        for name, items in checks.items():
            counts[f'{name}_emitted'] += len(result['swings'].get('highs', []) if name == 'swing' else result[name + 's'] if name not in {'structure'} else result['structure'])
            counts[f'{name}_failed'] += len(items)
            for _, reason in items:
                failures[reason] += 1
        seeds.extend(candidate_seed(symbol(path), ks, result, checks))
    fields = ['symbol','lifecycle_state','event_type','event_idx','event_date','broken_swing_idx','swing_confirm_idx','ob_idx','ob_date','zone_low','zone_high','semantic_contract','tradable','buy_enabled']
    with (OUT / 'v351_semantic_valid_continuation_seeds.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(seeds)
    report = {'version': 'V351_SEMANTIC_ORACLE_DAILY_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'),
              'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
              'oracle_contract': {'swing': '3-left/3-right confirmed pivot; visible only at pivot+3',
                                  'bos': 'close breaks confirmed swing by 0.2%',
                                  'ob': 'nearest opposite candle within 10 bars, scanned backward from event',
                                  'sweep': 'wick pierces confirmed swing then closes back inside',
                                  'fvg': 'three-candle non-overlap geometry'},
              'stage_counts': dict(counts), 'failure_reasons': dict(failures),
              'semantic_valid_continuation_seeds': len(seeds),
              'decision': 'SEMANTIC_ORACLE_READY__LIFECYCLE_REBUILD_NEXT',
              'artifacts': {'out_dir': str(OUT), 'seeds': str(OUT / 'v351_semantic_valid_continuation_seeds.csv'), 'latest': str(LATEST)}}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v351_report.json').write_text(text); LATEST.write_text(text)
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
