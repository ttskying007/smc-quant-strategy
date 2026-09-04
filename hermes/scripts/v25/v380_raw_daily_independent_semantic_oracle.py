#!/usr/bin/env python3
"""V380 no-write independent SMC semantic differential on V379 raw daily bars.

Two separately implemented detectors consume only daily OHLCV aggregated from the
same Sina 60m source. Segment boundaries are hard: no primitive is allowed to
look through an excluded source day. Emits semantic POI seeds only, never trades.
"""
from __future__ import annotations

import csv
import gzip
import importlib.util
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
RAW = ROOT / 'intraday_cache' / 'sina_raw_daily_v379'
AUDIT = ROOT / 'smc_audit'
V379 = AUDIT / 'v379_sina_m60_raw_daily_data_gate_latest.json'
OUT = AUDIT / f'v380_raw_daily_independent_semantic_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v380_raw_daily_independent_semantic_oracle_latest.json'
LEFT = RIGHT = 3
BREAK, SWEEP, LOOKBACK, OB_BACK = .002, .003, 60, 10

spec = importlib.util.spec_from_file_location('v27_reference', ROOT / 'scripts/v25/smc_core_v27.py')
v27 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v27)


def f(x: object) -> float:
    try:
        y = float(x)
        return y if math.isfinite(y) else 0.0
    except (TypeError, ValueError):
        return 0.0


def load(path: Path) -> list[dict]:
    with gzip.open(path, 'rt') as h:
        raw = json.load(h)
    out = []
    for x in raw:
        b = {k: f(x.get(k)) for k in ('o', 'h', 'l', 'c')}
        if x.get('t') and all(b.values()):
            b.update(t=str(x['t']), segment_id=int(x.get('segment_id', 0)))
            out.append(b)
    return out


def independent(b: list[dict]) -> dict:
    highs, lows = [], []
    for i in range(6, len(b) - RIGHT):
        if all(b[j]['h'] < b[i]['h'] for j in range(i - LEFT, i + RIGHT + 1) if j != i):
            highs.append({'idx': i, 'price': b[i]['h'], 'confirm_idx': i + RIGHT})
        if all(b[j]['l'] > b[i]['l'] for j in range(i - LEFT, i + RIGHT + 1) if j != i):
            lows.append({'idx': i, 'price': b[i]['l'], 'confirm_idx': i + RIGHT})
    broken, trend, structure = set(), 'unknown', []
    for i in range(30, len(b)):
        choices = [('high', x) for x in highs if x['confirm_idx'] <= i and ('high', x['idx']) not in broken]
        choices.sort(key=lambda q: q[1]['confirm_idx'], reverse=True)
        found = False
        for _, x in choices:
            if b[i]['c'] > x['price'] * (1 + BREAK):
                structure.append({'direction': 'bull', 'type': 'BOS' if trend == 'bullish' else 'CHOCH', 'index': i,
                                  'broken_swing_idx': x['idx'], 'confirm_visible_at': x['confirm_idx']})
                broken.add(('high', x['idx'])); trend = 'bullish'; found = True; break
        if found:
            continue
        choices = [('low', x) for x in lows if x['confirm_idx'] <= i and ('low', x['idx']) not in broken]
        choices.sort(key=lambda q: q[1]['confirm_idx'], reverse=True)
        for _, x in choices:
            if b[i]['c'] < x['price'] * (1 - BREAK):
                structure.append({'direction': 'bear', 'type': 'BOS' if trend == 'bearish' else 'CHOCH', 'index': i,
                                  'broken_swing_idx': x['idx'], 'confirm_visible_at': x['confirm_idx']})
                broken.add(('low', x['idx'])); trend = 'bearish'; break
    fvg = []
    for i in range(2, len(b)):
        if b[i]['l'] > b[i-2]['h'] and (b[i]['l'] - b[i-2]['h']) / b[i-2]['h'] > .0005:
            fvg.append({'direction': 'bull', 'index': i, 'gap_low': b[i-2]['h'], 'gap_high': b[i]['l']})
        if b[i]['h'] < b[i-2]['l'] and (b[i-2]['l'] - b[i]['h']) / b[i]['h'] > .0005:
            fvg.append({'direction': 'bear', 'index': i, 'gap_low': b[i]['h'], 'gap_high': b[i-2]['l']})
    sweep = []
    for i in range(20, len(b)):
        for x in lows:
            p = x['price']
            if (x['confirm_idx'] <= i and i - x['idx'] <= LOOKBACK and b[i]['l'] < p * (1-SWEEP)
                    and b[i]['c'] > p * (1-SWEEP/2) and (p-b[i]['l']) / p >= SWEEP):
                sweep.append({'direction': 'bull', 'index': i, 'swept_swing_idx': x['idx']})
        for x in highs:
            p = x['price']
            if (x['confirm_idx'] <= i and i - x['idx'] <= LOOKBACK and b[i]['h'] > p * (1+SWEEP)
                    and b[i]['c'] < p * (1-SWEEP/2) and (b[i]['h']-p) / p >= SWEEP):
                sweep.append({'direction': 'bear', 'index': i, 'swept_swing_idx': x['idx']})
    obs = []
    for e in structure:
        for j in range(e['index']-1, max(0, e['index']-OB_BACK-1), -1):
            opposite = b[j]['c'] < b[j]['o'] if e['direction'] == 'bull' else b[j]['c'] > b[j]['o']
            if opposite:
                obs.append({'direction': e['direction'], 'index': j, 'anchor_event_idx': e['index'],
                            'zone_low': b[j]['l'], 'zone_high': b[j]['h']})
                break
    return {'swings': {'highs': highs, 'lows': lows}, 'structure': structure, 'fvg': fvg, 'sweep': sweep, 'ob': obs}


def reference(b: list[dict]) -> dict:
    x = [dict(z) for z in b]
    swings = v27.confirmed_swings(x)
    structure = v27.structure_signals(x, swings)
    return {'swings': swings, 'structure': structure, 'fvg': v27.fvg_list(x), 'sweep': v27.sweep_signals(x, swings), 'ob': v27.ob_signals(x, structure)}


def key(stage: str, x: dict) -> tuple:
    if stage == 'swing_high': return (x['idx'], round(f(x['price']), 8), x['confirm_idx'])
    if stage == 'swing_low': return (x['idx'], round(f(x['price']), 8), x['confirm_idx'])
    if stage == 'structure':
        typ = x.get('source_event') if x.get('type') == 'MSS' else x.get('type')
        return (x['direction'], typ, x['index'], x['broken_swing_idx'], x['confirm_visible_at'])
    if stage == 'fvg': return (x['direction'], x['index'], round(f(x['gap_low']),8), round(f(x['gap_high']),8))
    if stage == 'sweep': return (x['direction'], x['index'], x['swept_swing_idx'])
    return (x['direction'], x['index'], x['anchor_event_idx'], round(f(x['zone_low']),8), round(f(x['zone_high']),8))


def main() -> None:
    gate = json.loads(V379.read_text())
    if gate['decision'] != 'DATA_GATE_PASS__RAW_DAILY_SEMANTIC_ORACLE_ALLOWED':
        raise RuntimeError('V379 data gate failed; semantic audit prohibited')
    OUT.mkdir(parents=True, exist_ok=True)
    counts, causal, mismatches, seeds = Counter(), Counter(), [], []
    for n, path in enumerate(sorted(RAW.glob('*_raw_daily.json.gz')), 1):
        symbol = path.name.removesuffix('_raw_daily.json.gz').replace('_', '.')
        bars = load(path)
        for segment in sorted({x['segment_id'] for x in bars}):
            local = [x for x in bars if x['segment_id'] == segment]
            if len(local) < 60:
                continue
            ref, ind = reference(local), independent(local)
            pairs = [('swing_high', ref['swings']['highs'], ind['swings']['highs']),
                     ('swing_low', ref['swings']['lows'], ind['swings']['lows']),
                     ('structure', ref['structure'], ind['structure']), ('fvg', ref['fvg'], ind['fvg']),
                     ('sweep', ref['sweep'], ind['sweep']), ('ob', ref['ob'], ind['ob'])]
            for stage, a, b in pairs:
                aa, bb = {key(stage,x) for x in a}, {key(stage,x) for x in b}
                counts[f'{stage}_reference'] += len(aa); counts[f'{stage}_independent'] += len(bb); counts[f'{stage}_matched'] += len(aa & bb)
                for disposition, values in [('REFERENCE_EXTRA', aa-bb), ('INDEPENDENT_EXTRA', bb-aa)]:
                    counts[f'{stage}_{disposition}'] += len(values)
                    for item in sorted(values)[:10]: mismatches.append({'symbol':symbol,'segment_id':segment,'stage':stage,'disposition':disposition,'key':repr(item)})
            for e in ind['structure']:
                if e['confirm_visible_at'] > e['index']: causal['STRUCTURE_FUTURE_PIVOT'] += 1
            for ob in ind['ob']:
                if not (ob['index'] < ob['anchor_event_idx'] and ob['anchor_event_idx']-ob['index'] <= OB_BACK): causal['OB_NONCAUSAL_ANCHOR'] += 1
            obs = {x['anchor_event_idx']:x for x in ind['ob'] if x['direction']=='bull'}
            for e in ind['structure']:
                if e['direction'] == 'bull' and e['type'] in {'BOS','CHOCH'} and e['index'] in obs:
                    ob = obs[e['index']]
                    seeds.append({'symbol':symbol,'segment_id':segment,'event_type':e['type'],'event_idx':e['index'],'event_date':local[e['index']]['t'],
                                  'swing_confirm_idx':e['confirm_visible_at'],'ob_idx':ob['index'],'ob_date':local[ob['index']]['t'],
                                  'zone_low':ob['zone_low'],'zone_high':ob['zone_high'],'semantic_contract':'raw_daily confirmed swing > bull BOS/CHOCH > backward nearest bearish OB',
                                  'tradable':False,'buy_enabled':False})
        if n % 500 == 0: print(json.dumps({'processed':n,'total':len(list(RAW.glob('*_raw_daily.json.gz'))),'seeds':len(seeds)}),flush=True)
    fields = ['symbol','segment_id','event_type','event_idx','event_date','swing_confirm_idx','ob_idx','ob_date','zone_low','zone_high','semantic_contract','tradable','buy_enabled']
    with (OUT/'v380_raw_daily_bull_poi_seeds.csv').open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(seeds)
    with (OUT/'v380_semantic_differential_mismatches.csv').open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=['symbol','segment_id','stage','disposition','key']); w.writeheader();w.writerows(mismatches)
    mismatch_total=sum(v for k,v in counts.items() if k.endswith('_EXTRA'))
    report={'version':'V380_RAW_DAILY_INDEPENDENT_SEMANTIC_ORACLE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),
            'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
            'contract':{'swing':'unique 3-left/3-right pivot visible at pivot+3','structure':'close breaks confirmed swing by 0.2%','ob':'backward nearest opposite candle within 10 bars','fvg':'3-bar non-overlap >=0.05%','sweep':'confirmed swing wick pierce 0.3% then close reclaim','segments':'all calculations reset at V379 raw-source anomaly boundaries'},
            'stage_counts':dict(counts),'causality_failures':dict(causal),'mismatch_total':mismatch_total,'semantic_valid_daily_bull_poi_seeds':len(seeds),
            'decision':'SEMANTIC_DIFFERENTIAL_PASS__MTF_REPLAY_ALLOWED' if mismatch_total==0 and not causal else 'SEMANTIC_DIFFERENTIAL_FAIL__STOP_BEFORE_MTF_REPLAY',
            'artifacts':{'seeds':str(OUT/'v380_raw_daily_bull_poi_seeds.csv'),'mismatches':str(OUT/'v380_semantic_differential_mismatches.csv'),'latest':str(LATEST)}}
    text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v380_report.json').write_text(text);LATEST.write_text(text);print(text)

if __name__=='__main__': main()
