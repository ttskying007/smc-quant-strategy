#!/usr/bin/env python3
"""V420 no-outcome R3 generator: EQL liquidity-pool sweep -> CHOCH -> fresh OB."""
from __future__ import annotations

import csv
import importlib.util
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
KDIR, AUD = ROOT / 'kline_cache', ROOT / 'smc_audit'
OUT = AUD / f'v420_eql_pool_reversal_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v420_eql_pool_reversal_latest.json'
spec = importlib.util.spec_from_file_location('v27', ROOT / 'scripts/v25/smc_core_v27.py')
v27 = importlib.util.module_from_spec(spec); spec.loader.exec_module(v27)


def f(x):
    try:
        x = float(x); return x if math.isfinite(x) else 0.0
    except (TypeError, ValueError): return 0.0


def day(b): return ''.join(c for c in str(b.get('t') or b.get('date') or '') if c.isdigit())[:8]


def load(path):
    try: raw = json.loads(path.read_text())
    except Exception: return []
    return sorted([b for b in raw if day(b) and all(f(b.get(k)) > 0 for k in ('o','h','l','c'))], key=day)


def symbol(path):
    p = path.name.replace('_daily_750.json','').split('_')
    return f'{p[0]}.{p[1]}'


def lifecycle(ks, start, low, high):
    """Return lifecycle state plus ordered touch/reclaim/takeover indices."""
    touch = reclaim = None
    for i in range(start + 1, min(len(ks), start + 31)):
        b = ks[i]
        if f(b['c']) < low:
            return 'CANCEL_ZONE_INVALIDATED', touch, reclaim, i
        if touch is None:
            if f(b['l']) <= high:
                touch = i
        elif reclaim is None:
            if f(b['c']) > high:
                reclaim = i
        elif f(b['c']) > high and f(b['l']) >= low:
            return 'TAKEOVER_CONFIRMED', touch, reclaim, i
    observed = start + 30 < len(ks)
    if touch is None:
        return ('EXPIRE_NO_TOUCH_30B' if observed else 'WAIT_TOUCH_UNOBSERVED'), None, None, None
    if reclaim is None:
        return ('EXPIRE_NO_RECLAIM_30B' if observed else 'WAIT_RECLAIM_UNOBSERVED'), touch, None, None
    return ('EXPIRE_NO_HOLD_30B' if observed else 'WAIT_HOLD_UNOBSERVED'), touch, reclaim, None


def pool_sweeps(swings, sweeps):
    """A pool is two confirmed prior swing lows within the fixed 0.3% sweep band."""
    out = []
    for sweep in sweeps:
        if sweep.get('direction') != 'bull': continue
        i, price = sweep['index'], f(sweep['swept_swing_price'])
        peers = [x for x in swings['lows'] if x['confirm_idx'] < i and 0 < i-x['idx'] <= 60 and abs(f(x['price'])/price-1) <= .003]
        if len(peers) >= 2:
            out.append((sweep, sorted(peers, key=lambda x: x['idx'])[-2:]))
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows, counts = [], Counter()
    for path in sorted(KDIR.glob('*_daily_750.json')):
        ks = load(path)
        if len(ks) < 60: continue
        counts['symbols_scanned'] += 1
        swings = v27.confirmed_swings(ks)
        structure = v27.structure_signals(ks, swings)
        obs = v27.ob_signals(ks, structure)
        by_event = {}
        for ob in obs:
            if ob.get('direction') == 'bull': by_event.setdefault(ob['anchor_event_idx'], []).append(ob)
        for sweep, pool in pool_sweeps(swings, v27.sweep_signals(ks, swings)):
            si = sweep['index']
            for ev in structure:
                ei = ev['index']
                if ev.get('direction') != 'bull' or ev.get('type') != 'CHOCH' or not 1 <= ei-si <= 20: continue
                for ob in by_event.get(ei, []):
                    # A pre-event wick touch/close break means this is not the first post-event retest.
                    lo, hi, oi = f(ob['zone_low']), f(ob['zone_high']), ob['index']
                    if any(f(b['c']) < lo or f(b['l']) <= hi for b in ks[oi+1:ei]):
                        counts['PRE_EVENT_OB_NOT_FRESH'] += 1; continue
                    state, ti, ri, ci = lifecycle(ks, ei, lo, hi)
                    rows.append({'symbol':symbol(path),'combo_key':'R3_EQL_POOL_SSL_CHOCH_DEMAND_OB','lifecycle_state':state,
                        'sweep_idx':si,'sweep_date':day(ks[si]),'pool_low_a_idx':pool[0]['idx'],'pool_low_b_idx':pool[1]['idx'],
                        'event_idx':ei,'event_date':day(ks[ei]),'poi_idx':oi,'poi_date':day(ks[oi]),'poi_type':'DEMAND_OB',
                        'zone_low':round(lo,6),'zone_high':round(hi,6),'strict_lifecycle_start_idx':ei,
                        'touch_idx':'' if ti is None else ti,'reclaim_idx':'' if ri is None else ri,
                        'takeover_idx':'' if ci is None else ci,'takeover_date':day(ks[ci]) if state=='TAKEOVER_CONFIRMED' else '',
                        'semantic_contract':'two confirmed equal swing lows visible before SSL sweep -> bull CHOCH -> fresh backward demand OB -> lifecycle strictly after CHOCH',
                        'tradable':'false','buy_enabled':'false','outcome_fields_present':'false'})
    unique = {(r['symbol'],r['sweep_idx'],r['event_idx'],r['poi_idx']):r for r in rows}
    rows = list(unique.values()); stages = Counter(r['lifecycle_state'] for r in rows)
    with (OUT/'v420_rows.csv').open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=list(rows[0]) if rows else ['symbol']); w.writeheader(); w.writerows(rows)
    report={'version':'V420_EQL_POOL_REVERSAL_GENERATOR_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
        'contract':'R3 only: two confirmed equal-low swing pivots within 0.3%, then SSL sweep, bull CHOCH in 1..20 bars, fresh event-anchored demand OB, lifecycle begins next bar','counts':dict(counts),'candidates':len(rows),'lifecycle':dict(stages),'invariants':{'all_non_tradable':all(r['tradable']=='false' for r in rows),'no_outcomes':all(r['outcome_fields_present']=='false' for r in rows)},'decision':'R3_SEMANTIC_CANDIDATES_READY_FOR_ONE_FROZEN_T1_MARK_REPLAY_ONLY','artifacts':{'out_dir':str(OUT),'rows':str(OUT/'v420_rows.csv'),'latest':str(LATEST)}}
    text=json.dumps(report,ensure_ascii=False,indent=2); (OUT/'v420_report.json').write_text(text); LATEST.write_text(text); print(text)

if __name__=='__main__': main()
