#!/usr/bin/env python3
"""V556: no-write, pre-entry mechanism attribution for V555 frozen rows.

Every mechanism tag is built only from bars known before the next-day entry:
- daily demand mitigation before BOS;
- BOS acceptance/failure before entry;
- whether V553's 15m "MSS" broke a confirmed pre-touch swing;
- whether the structural target was already consumed before entry.
Outcomes are read only after tags are frozen, to cross-tab SL/TP/TIME results.
"""
from __future__ import annotations
import csv, gzip, json, math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
RAW = ROOT/'intraday_cache/raw_multitf_v536/source_raw/sina'
AUD = ROOT/'smc_audit'
V553 = AUD/'v553_daily_candidate_mtf_lineage_latest.json'
V555 = AUD/'v555_daily_m15_takeover_frozen_t1_diagnostic_latest.json'
OUT = AUD/f'v556_v555_sl_mechanism_attribution_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD/'v556_v555_sl_mechanism_attribution_latest.json'


def num(value: Any) -> float | None:
    try:
        value = float(value)
        return value if math.isfinite(value) and value > 0 else None
    except (TypeError, ValueError):
        return None


def load(path: Path, frame: str) -> list[dict]:
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as handle: raw = json.load(handle)
    except (OSError, ValueError): return []
    out = []
    for row in raw if isinstance(raw, list) else []:
        stamp = str(row.get('t') or '')
        day = str(row.get('d') or stamp[:8])[:8]
        vals = [num(row.get(k)) for k in ('o','h','l','c')]
        if (len(stamp) == 14 if frame == 'm15' else len(day) == 8) and all(v is not None for v in vals):
            out.append({'t': stamp if frame == 'm15' else day, 'd': day, 'o': vals[0], 'h': vals[1], 'l': vals[2], 'c': vals[3]})
    return sorted(out, key=lambda x: x['t'])


def confirmed_swing_high(rows: list[dict], index: int, right_end: int) -> bool:
    return index >= 3 and index + 3 <= right_end and rows[index]['h'] > max(x['h'] for x in rows[index-3:index]) and rows[index]['h'] >= max(x['h'] for x in rows[index+1:index+4])


def target_anchor(rows: list[dict], entry_i: int, target: float) -> int | None:
    """Locate V555's already-frozen target without recomputing its selector."""
    matches = [i for i in range(3, entry_i - 3)
               if abs(rows[i]['h'] - target) <= 1e-6 and confirmed_swing_high(rows, i, entry_i - 1)]
    return matches[0] if matches else None


def stat(rows: list[dict]) -> dict:
    exits = Counter(r['exit_reason'] for r in rows)
    sl = exits['SL']
    return {'n': len(rows), 'sl': sl, 'tp': exits['TP_STRUCTURAL'], 'time': exits['TIME20'], 'sl_pct': round(100*sl/len(rows), 4) if rows else None}


def main() -> None:
    lineage = json.loads(V553.read_text())
    replay = json.loads(V555.read_text())
    with Path(lineage['artifacts']['candidate_lineage_csv']).open(newline='', encoding='utf-8') as f:
        candidates = {(r['symbol'], r['event_date'], r['reclaim_date'], r['planned_entry_date']): r for r in csv.DictReader(f) if r['m15_confirmation_label'] == 'M15_TAKEOVER_CONFIRMED'}
    with Path(replay['artifacts']['trades']).open(newline='', encoding='utf-8') as f:
        trades = list(csv.DictReader(f))
    OUT.mkdir(parents=True, exist_ok=False)
    daily_cache, m15_cache = {}, {}
    rows, missing = [], []
    for trade in trades:
        key = (trade['symbol'], trade['event_date'], trade['reclaim_date'], trade['entry_date'])
        c = candidates.get(key)
        if not c:
            missing.append({**trade, 'reason': 'LINEAGE_IDENTITY_MISSING'}); continue
        sym = trade['symbol']
        daily = daily_cache.setdefault(sym, load(RAW/'daily'/f'{sym.replace(".", "_")}_daily.json.gz', 'daily'))
        m15 = m15_cache.setdefault(sym, load(RAW/'m15'/f'{sym.replace(".", "_")}_m15.json.gz', 'm15'))
        by_day = defaultdict(list)
        for bar in m15: by_day[bar['d']].append(bar)
        event_i = next((i for i,x in enumerate(daily) if x['d'] == trade['event_date']), None)
        zone_i = next((i for i,x in enumerate(daily) if x['d'] == c['zone_date']), None)
        entry_i = next((i for i,x in enumerate(daily) if x['d'] == trade['entry_date']), None)
        if None in (event_i, zone_i, entry_i) or event_i < 20:
            missing.append({**trade, 'reason': 'DAILY_ANCHOR_MISSING'}); continue
        zone_low, zone_high = float(c['zone_low']), float(c['zone_high'])
        bos_level = max(x['h'] for x in daily[event_i-20:event_i])
        prior = daily[zone_i+1:event_i]
        demand_wick_touched = any(x['l'] <= zone_high for x in prior)
        demand_deeply_consumed = any(x['l'] <= zone_low for x in prior)
        bos_failed_before_entry = any(x['c'] <= bos_level for x in daily[event_i+1:entry_i])
        session = by_day[c['reclaim_date']]
        touch_i = next((i for i,x in enumerate(session) if x['l'] <= zone_high and x['h'] >= zone_low), None)
        anchor_i = None if touch_i is None else max(range(touch_i+1), key=lambda i: session[i]['h'])
        m15_anchor_confirmed = bool(anchor_i is not None and confirmed_swing_high(session, anchor_i, touch_i))
        target = float(trade['target'])
        target_i = target_anchor(daily, entry_i, target)
        target_consumed_before_entry = bool(target_i is not None and any(x['h'] >= target for x in daily[target_i+1:entry_i]))
        lookback = daily[entry_i-20:entry_i]
        range_pos = (float(trade['entry']) - min(x['l'] for x in lookback)) / max(max(x['h'] for x in lookback) - min(x['l'] for x in lookback), 1e-12)
        tags = []
        if demand_deeply_consumed: tags.append('DEMAND_DEEPLY_CONSUMED_PRE_BOS')
        elif demand_wick_touched: tags.append('DEMAND_PARTIALLY_MITIGATED_PRE_BOS')
        if bos_failed_before_entry: tags.append('BOS_NOT_ACCEPTED_BEFORE_ENTRY')
        if not m15_anchor_confirmed: tags.append('M15_MSS_BREAKS_UNCONFIRMED_INTERNAL_HIGH')
        if target_consumed_before_entry: tags.append('OVERHEAD_STRUCTURAL_TARGET_ALREADY_CONSUMED')
        rows.append({**trade, 'zone_date': c['zone_date'], 'bos_level': round(bos_level,6),
            'demand_wick_touched_pre_bos': demand_wick_touched, 'demand_deeply_consumed_pre_bos': demand_deeply_consumed,
            'bos_failed_before_entry': bos_failed_before_entry, 'm15_mss_anchor_confirmed_3l3r': m15_anchor_confirmed,
            'target_consumed_before_entry': target_consumed_before_entry, 'entry_prior20_range_position': round(range_pos,6),
            'preentry_mechanism_tags': '|'.join(tags) if tags else 'NO_PREENTRY_DEFECT_TAG'})
    assert len(rows) + len(missing) == len(trades)
    features = ['demand_wick_touched_pre_bos','demand_deeply_consumed_pre_bos','bos_failed_before_entry','m15_mss_anchor_confirmed_3l3r','target_consumed_before_entry']
    feature_table = {}
    for feature in features:
        feature_table[feature] = {str(value): stat([r for r in rows if str(r[feature]) == str(value)]) for value in (True, False)}
    signatures = defaultdict(list)
    for r in rows: signatures[r['preentry_mechanism_tags']].append(r)
    signature_table = [{'signature': k, **stat(v), 'n_2025': len([r for r in v if r['year']=='2025']), 'n_2026': len([r for r in v if r['year']=='2026'])} for k,v in signatures.items()]
    signature_table.sort(key=lambda x: (-x['sl'], -x['n'], x['signature']))
    year_feature = {}
    for year in ('2025','2026'):
        year_rows = [r for r in rows if r['year']==year]
        year_feature[year] = {'overall': stat(year_rows), **{feature: {str(value): stat([r for r in year_rows if str(r[feature]) == str(value)]) for value in (True, False)} for feature in features}}
    loss = [r for r in rows if r['exit_reason']=='SL']
    report = {'version':'V556_V555_SL_MECHANISM_ATTRIBUTION_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'research_only':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'scope':'Frozen V555 executable rows only. Mechanism tags are constructed before entry; V555 exit outcomes are only used to aggregate tags.',
      'pre_entry_definitions':{'demand_consumption':'A later daily bar between zone candle and BOS wicks into demand; deep means low reaches zone_low.','bos_not_accepted':'Between BOS and entry, a daily close is at/below the pre-BOS 20-session breakout level.','m15_internal_mss':'V553 M15 MSS is counted as structurally anchored only if its broken pre-touch high is a 3-left/3-right swing fully confirmed before touch.','target_consumed':'The nearest pre-entry confirmed daily swing target meeting V555 RR>=1.5 was traded through after its confirmation and before entry.','range_position':'Descriptive entry location in prior 20 daily sessions; not a filter.'},
      'coverage':{'v555_trades':len(trades),'attributed':len(rows),'missing':len(missing),'sl_rows':len(loss),'all_v555_sl_accounted':len(loss)==3368},
      'overall':stat(rows),'feature_outcome_crosstab':feature_table,'yearly_feature_crosstab':year_feature,'overlap_signatures':signature_table,
      'range_position_medians':{label: round(sorted(float(r['entry_prior20_range_position']) for r in group)[len(group)//2],6) for label,group in {'SL':loss,'NON_SL':[r for r in rows if r['exit_reason']!='SL'],'2025_SL':[r for r in loss if r['year']=='2025'],'2026_SL':[r for r in loss if r['year']=='2026']}.items() if group},
      'invariants':{'all_tags_pre_entry_only':True,'no_gate_or_parameter_search':True,'no_production_or_frontend_write':True,'tagged_plus_missing_equals_v555':len(rows)+len(missing)==len(trades)},
      'decision':'ATTRIBUTION_COMPLETE__DESCRIPTIVE_EVIDENCE_ONLY__NO_SELECTOR_OR_PRODUCTION_AUTHORIZATION',
      'artifacts':{'out_dir':str(OUT),'attributed_rows':str(OUT/'v556_attributed_v555_rows.csv'),'missing':str(OUT/'v556_missing.csv'),'latest':str(LATEST)}}
    for filename, data in [('v556_attributed_v555_rows.csv', rows), ('v556_missing.csv', missing)]:
        with (OUT/filename).open('w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(data[0]) if data else ['symbol']); w.writeheader(); w.writerows(data)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT/'v556_report.json').write_text(text); LATEST.write_text(text); print(text)

if __name__ == '__main__': main()
