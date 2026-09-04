#!/usr/bin/env python3
"""V409 no-write causal SMC combination state machine.

Enumerates only three signal stories from raw daily bars, without PnL or trade
outcomes:
  R1: confirmed SSL sweep -> bullish CHOCH -> event-anchored demand OB -> retest/reclaim/hold
  R2: confirmed SSL sweep -> bullish CHOCH -> post-confirmation bullish FVG -> retest/reclaim/hold
  C1: confirmed bullish BOS -> event-anchored demand OB -> retest/reclaim/hold

Every candidate remains non-tradable.  This is the signal automation layer;
entry/exits are deliberately outside its contract.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
KDIR, AUD = ROOT / 'kline_cache', ROOT / 'smc_audit'
OUT = AUD / f'v409_causal_signal_combination_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v409_causal_signal_combination_latest.json'

spec = importlib.util.spec_from_file_location('v27', ROOT / 'scripts/v25/smc_core_v27.py')
v27 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v27)


def f(x):
    try:
        value = float(x)
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
    bars = [b for b in raw if day(b) and all(f(b.get(k)) > 0 for k in ('o', 'h', 'l', 'c'))]
    return sorted(bars, key=day)


def symbol(path):
    parts = path.name.replace('_daily_750.json', '').split('_')
    return f'{parts[0]}.{parts[1]}' if len(parts) == 2 else path.stem


def lifecycle(ks, event_i, low, high):
    """First post-confirmation touch/reclaim/hold; a close below zone kills setup."""
    touch = reclaim = None
    for i in range(event_i + 1, min(len(ks), event_i + 31)):
        b = ks[i]
        if f(b.get('c')) < low:
            return 'CANCEL_ZONE_INVALIDATED', i, touch, reclaim
        if touch is None:
            if f(b.get('l')) <= high:
                touch = i
            continue
        if reclaim is None:
            if f(b.get('c')) > high:
                reclaim = i
            continue
        if i > reclaim and f(b.get('c')) > high and f(b.get('l')) >= low:
            return 'TAKEOVER_CONFIRMED', i, touch, reclaim
    observed = event_i + 30 < len(ks)
    if touch is None:
        return ('EXPIRE_NO_TOUCH_30B' if observed else 'WAIT_TOUCH_UNOBSERVED'), None, None, None
    if reclaim is None:
        return ('EXPIRE_NO_RECLAIM_30B' if observed else 'WAIT_RECLAIM_UNOBSERVED'), None, touch, None
    return ('EXPIRE_NO_HOLD_30B' if observed else 'WAIT_HOLD_UNOBSERVED'), None, touch, reclaim


def obs_by_event(obs):
    result = defaultdict(list)
    for ob in obs:
        if ob.get('direction') == 'bull':
            result[ob.get('anchor_event_idx')].append(ob)
    return result


def valid_reversal_rows(sym, ks, signals):
    """R1/R2: SSL must precede bull CHOCH by 1..20 confirmed bars."""
    rows = []
    bull_sweeps = [x for x in signals['sweeps'] if x.get('direction') == 'bull']
    bull_choch = [x for x in signals['structure'] if x.get('direction') == 'bull' and x.get('type') == 'CHOCH']
    obs = obs_by_event(signals['obs'])
    fvgs = [x for x in signals['fvgs'] if x.get('direction') == 'bull']
    for event in bull_choch:
        ei = event['index']
        starts = [s for s in bull_sweeps if 1 <= ei - s.get('index', -99999) <= 20]
        if not starts:
            continue
        sweep = max(starts, key=lambda x: x['index'])  # nearest prior causal liquidity event
        for ob in obs.get(ei, []):
            rows.append(seed(sym, ks, 'R1_SSL_CHOCH_DEMAND_OB', sweep['index'], ei, ob['index'], ob['zone_low'], ob['zone_high'], 'DEMAND_OB'))
        # FVG may only be born at/after CHOCH; it cannot be retrospectively promoted.
        for fvg in fvgs:
            fi = fvg['index']
            if ei <= fi <= ei + 3:
                rows.append(seed(sym, ks, 'R2_SSL_CHOCH_BULL_FVG', sweep['index'], ei, fi, fvg['gap_low'], fvg['gap_high'], 'BULL_FVG'))
    return rows


def valid_continuation_rows(sym, ks, signals):
    """C1: confirmed bull BOS plus its causal backward-anchored demand OB."""
    rows = []
    obs = obs_by_event(signals['obs'])
    for event in signals['structure']:
        if event.get('direction') != 'bull' or event.get('type') != 'BOS':
            continue
        ei = event['index']
        for ob in obs.get(ei, []):
            rows.append(seed(sym, ks, 'C1_BOS_DEMAND_OB', None, ei, ob['index'], ob['zone_low'], ob['zone_high'], 'DEMAND_OB'))
    return rows


def seed(sym, ks, combo, sweep_i, event_i, poi_i, low, high, poi_type):
    status, state_i, touch_i, reclaim_i = lifecycle(ks, event_i, f(low), f(high))
    def date_at(i): return day(ks[i]) if i is not None else ''
    return {
        'symbol': sym, 'combo_key': combo, 'lifecycle_state': status,
        'sweep_idx': '' if sweep_i is None else sweep_i, 'sweep_date': date_at(sweep_i),
        'event_idx': event_i, 'event_date': date_at(event_i),
        'poi_idx': poi_i, 'poi_date': date_at(poi_i), 'poi_type': poi_type,
        'zone_low': round(f(low), 6), 'zone_high': round(f(high), 6),
        'touch_idx': '' if touch_i is None else touch_i, 'touch_date': date_at(touch_i),
        'reclaim_idx': '' if reclaim_i is None else reclaim_i, 'reclaim_date': date_at(reclaim_i),
        'takeover_idx': '' if state_i is None else state_i,
        'takeover_date': date_at(state_i) if status == 'TAKEOVER_CONFIRMED' else '',
        'sweep_to_event_bars': '' if sweep_i is None else event_i - sweep_i,
        'event_to_poi_bars': poi_i - event_i,
        'event_to_touch_bars': '' if touch_i is None else touch_i - event_i,
        'touch_to_reclaim_bars': '' if touch_i is None or reclaim_i is None else reclaim_i - touch_i,
        'reclaim_to_takeover_bars': '' if reclaim_i is None or state_i is None else state_i - reclaim_i,
        'semantic_contract': 'confirmed primitive events only; causal order enforced; lifecycle starts after confirmation',
        'tradable': 'false', 'buy_enabled': 'false', 'outcome_fields_present': 'false',
    }


def q50(values):
    values = sorted(x for x in values if isinstance(x, int))
    return values[len(values) // 2] if values else None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    counts, rows = Counter(), []
    for path in sorted(KDIR.glob('*_daily_750.json')):
        ks = load(path)
        if len(ks) < 60:
            continue
        counts['symbols_scanned'] += 1
        bars = [dict(x) for x in ks]
        swings = v27.confirmed_swings(bars)
        signals = {
            'structure': v27.structure_signals(bars, swings),
            'sweeps': v27.sweep_signals(bars, swings),
            'fvgs': v27.fvg_list(bars),
            'obs': v27.ob_signals(bars, v27.structure_signals(bars, swings)),
        }
        generated = valid_reversal_rows(symbol(path), ks, signals) + valid_continuation_rows(symbol(path), ks, signals)
        # A POI cannot become a new continuation setup merely because subsequent
        # BOS bars keep breaking levels. Keep its first causal event only; reversal
        # identities retain their distinct sweep->CHOCH provenance.
        seen = set()
        for row in generated:
            key = ((row['symbol'], row['combo_key'], row['poi_idx'])
                   if row['combo_key'] == 'C1_BOS_DEMAND_OB'
                   else (row['symbol'], row['combo_key'], row['sweep_idx'], row['event_idx'], row['poi_idx']))
            if key in seen:
                continue
            seen.add(key); rows.append(row); counts[row['combo_key']] += 1; counts[row['lifecycle_state']] += 1

    fields = list(rows[0]) if rows else ['symbol', 'combo_key']
    with (OUT / 'v409_combination_lifecycle_rows.csv').open('w', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    combos = {}
    for combo in ('R1_SSL_CHOCH_DEMAND_OB', 'R2_SSL_CHOCH_BULL_FVG', 'C1_BOS_DEMAND_OB'):
        x = [r for r in rows if r['combo_key'] == combo]
        stages = Counter(r['lifecycle_state'] for r in x)
        combos[combo] = {
            'candidates': len(x), 'lifecycle': dict(stages),
            'takeover_rate_pct': round(stages['TAKEOVER_CONFIRMED'] / len(x) * 100, 2) if x else 0,
            'median_sweep_to_event_bars': q50([r['sweep_to_event_bars'] for r in x]),
            'median_event_to_poi_bars': q50([r['event_to_poi_bars'] for r in x]),
            'median_event_to_touch_bars': q50([r['event_to_touch_bars'] for r in x]),
            'median_touch_to_reclaim_bars': q50([r['touch_to_reclaim_bars'] for r in x]),
        }
    report = {
        'version': 'V409_CAUSAL_SIGNAL_COMBINATION_STATE_MACHINE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'scope': 'automated signal-combination discovery; no entry, exit, PnL, or candidate promotion',
        'three_combo_contracts': {
            'R1_SSL_CHOCH_DEMAND_OB': 'confirmed SSL sweep -> bull CHOCH within 20 bars -> CHOCH-anchored backward demand OB -> post-confirmation first retest/reclaim/hold',
            'R2_SSL_CHOCH_BULL_FVG': 'confirmed SSL sweep -> bull CHOCH within 20 bars -> bullish FVG born 0..3 bars after CHOCH -> first retest/reclaim/hold',
            'C1_BOS_DEMAND_OB': 'confirmed bull BOS -> BOS-anchored backward demand OB -> post-confirmation first retest/reclaim/hold',
        },
        'primitive_contract': '3L/3R visible pivots; 0.2% close structure break; 0.3% wick-and-close liquidity sweep; three-bar FVG; nearest opposite candle OB within 10 bars backward from structure event',
        'stage_counts': dict(counts), 'combination_summary': combos,
        'invariants': {'all_rows_non_tradable': all(r['tradable'] == 'false' for r in rows), 'no_outcome_fields': all(r['outcome_fields_present'] == 'false' for r in rows)},
        'decision': 'COMBINATION_AUTOMATION_READY__NEXT_RUN_FROZEN_T1_EXECUTION_REPLAY_PER_COMBO',
        'artifacts': {'out_dir': str(OUT), 'rows': str(OUT / 'v409_combination_lifecycle_rows.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v409_report.json').write_text(text); LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
