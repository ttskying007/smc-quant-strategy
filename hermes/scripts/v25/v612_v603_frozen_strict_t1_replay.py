#!/usr/bin/env python3
"""One immutable V611 replay of V603 VALID_CHAIN identities.

Reads the V611 preregistration and source-isolated Sina m15 OHLC.  It never
selects, filters, or changes seeds using outcome data.  It writes research-only
results and must be run once; a failure closes the ontology without variants.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina/m15'
PREREG = AUDIT / 'v611_v603_frozen_execution_preregistration.json'
OUT = AUDIT / f'v612_v603_one_frozen_strict_t1_replay_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v612_v603_one_frozen_strict_t1_replay_latest.json'
LEFT = RIGHT = 3
FEE_PCT = 0.20
BUFFER = 0.003


def f(v):
    try:
        x = float(v)
        return x if math.isfinite(x) and x > 0 else None
    except (TypeError, ValueError):
        return None


def load(symbol):
    p = RAW / f'{symbol.replace(".", "_")}_m15.json.gz'
    raw = json.load(gzip.open(p, 'rt', encoding='utf-8'))
    rows = []
    for x in raw:
        o, h, l, c = (f(x.get(k)) for k in ('o', 'h', 'l', 'c'))
        t = str(x.get('t') or '')
        if len(t) == 14 and None not in (o, h, l, c):
            rows.append({'t': t, 'd': t[:8], 'o': o, 'h': h, 'l': l, 'c': c})
    return sorted(rows, key=lambda x: x['t'])


def highs(rows):
    out = []
    for i in range(LEFT, len(rows) - RIGHT):
        if rows[i]['h'] > max(x['h'] for x in rows[i-LEFT:i]) and rows[i]['h'] >= max(x['h'] for x in rows[i+1:i+RIGHT+1]):
            out.append(i)
    return out


def target_at_entry(rows, entry_i, price):
    """Nearest prior right-confirmed high still unconsumed at the entry bar."""
    candidates = []
    # The entry bar's high/low/close is unknown at its open, so all target
    # discovery and consumption checks stop strictly before entry_i.
    for p in highs(rows[:entry_i]):
        if p + RIGHT >= entry_i or rows[p]['h'] <= price:
            continue
        # It must have remained unconsumed through the last completed pre-entry bar.
        if any(x['h'] >= rows[p]['h'] for x in rows[p + RIGHT + 1:entry_i]):
            continue
        candidates.append(p)
    return min(candidates, key=lambda p: rows[p]['h']) if candidates else None


def run_seed(seed, rows):
    by_t = {x['t']: i for i, x in enumerate(rows)}
    entry_i = by_t.get(seed['entry_time'])
    if entry_i is None or entry_i == 0:
        return None, 'EXCLUDED_MISSING_ENTRY_BAR'
    entry = rows[entry_i]
    if entry['o'] <= 0:
        return None, 'EXCLUDED_NONPOSITIVE_ENTRY_OPEN'
    stop_anchor = min(float(seed['sweep_low']), float(seed['ob_low']))
    stop = stop_anchor * (1 - BUFFER)
    target_i = target_at_entry(rows, entry_i, entry['o'])
    if target_i is None:
        return None, 'EXCLUDED_NO_PREENTRY_STRUCTURAL_TARGET'
    target = rows[target_i]['h']
    rr = (target - entry['o']) / (entry['o'] - stop)
    if rr < 1.5:
        return None, 'EXCLUDED_PLANNED_RR_LT_1_5'
    exit_row = None
    reason = 'OPEN_UNOBSERVED'
    for bar in rows[entry_i + 1:]:
        if bar['d'] == entry['d']:
            continue
        if bar['o'] <= stop:
            exit_row, reason, exit_px = bar, 'SL_GAP_T1', bar['o']; break
        if bar['o'] >= target:
            exit_row, reason, exit_px = bar, 'TP_GAP_T1', bar['o']; break
        hit_stop, hit_target = bar['l'] <= stop, bar['h'] >= target
        if hit_stop and hit_target:
            exit_row, reason, exit_px = bar, 'SL_TP_COLLISION_STOP_FIRST', stop; break
        if hit_stop:
            exit_row, reason, exit_px = bar, 'SL_T1', stop; break
        if hit_target:
            exit_row, reason, exit_px = bar, 'TP_T1', target; break
    if exit_row is None:
        return {
            'symbol': seed['symbol'], 'entry_time': entry['t'], 'entry_date': entry['d'], 'entry_price': entry['o'],
            'stop_price': stop, 'stop_anchor': stop_anchor, 'target_time': rows[target_i]['t'], 'target_price': target,
            'planned_rr': rr, 'exit_time': '', 'exit_date': '', 'exit_price': '', 'exit_reason': reason, 'net_pnl_pct': '',
        }, None
    net = (exit_px / entry['o'] - 1) * 100 - FEE_PCT
    return {
        'symbol': seed['symbol'], 'entry_time': entry['t'], 'entry_date': entry['d'], 'entry_price': entry['o'],
        'stop_price': stop, 'stop_anchor': stop_anchor, 'target_time': rows[target_i]['t'], 'target_price': target,
        'planned_rr': rr, 'exit_time': exit_row['t'], 'exit_date': exit_row['d'], 'exit_price': exit_px,
        'exit_reason': reason, 'net_pnl_pct': net,
    }, None


def main():
    contract = json.load(open(PREREG, encoding='utf-8'))
    if contract['authorization']['decision'] != 'V611_PREREGISTRATION_COMPLETE__ONE_FROZEN_RESEARCH_REPLAY_AUTHORIZED__NO_VARIANTS_NO_PRODUCTION':
        raise RuntimeError('preregistration not authorized')
    source = Path(contract['semantic_input']['chain_audit_csv'])
    rows = list(csv.DictReader(open(source, encoding='utf-8')))
    seeds = [r for r in rows if r['terminal_status'] == 'VALID_CHAIN']
    OUT.mkdir(parents=True, exist_ok=False)
    trades, excluded = [], Counter()
    grouped = defaultdict(list)
    for seed in seeds: grouped[seed['symbol']].append(seed)
    for symbol, group in grouped.items():
        bars = load(symbol)
        # serial position per symbol: chronological seed; no overlapping open positions.
        last_exit = ''
        for seed in sorted(group, key=lambda x: x['entry_time']):
            if last_exit and seed['entry_time'] <= last_exit:
                excluded['EXCLUDED_SERIAL_POSITION_OPEN'] += 1; continue
            trade, reason = run_seed(seed, bars)
            if reason:
                excluded[reason] += 1; continue
            trades.append(trade)
            if trade['exit_time']:
                last_exit = trade['exit_time']
    closed = [t for t in trades if t['exit_time']]
    net = [float(t['net_pnl_pct']) for t in closed]
    wins = [x for x in net if x > 0]
    losses = [x for x in net if x <= 0]
    yearly = {}
    for year in sorted({t['entry_date'][:4] for t in closed}):
        xs = [float(t['net_pnl_pct']) for t in closed if t['entry_date'].startswith(year)]
        yearly[year] = {'n': len(xs), 'wr_pct': 100 * sum(x > 0 for x in xs) / len(xs) if xs else None, 'avg_net_pct': sum(xs) / len(xs) if xs else None}
    fields = list(trades[0]) if trades else ['symbol']
    with open(OUT / 'v612_frozen_t1_trades.csv', 'w', newline='', encoding='utf-8') as h:
        w = csv.DictWriter(h, fieldnames=fields); w.writeheader(); w.writerows(trades)
    t1 = sum(bool(t['exit_time']) and t['exit_date'] <= t['entry_date'] for t in trades)
    report = {
        'version': 'V612_V603_ONE_FROZEN_STRICT_T1_REPLAY', 'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'preregistration': str(PREREG), 'seed_count': len(seeds), 'executed_or_open_count': len(trades),
        'closed_count': len(closed), 'open_unobserved_count': len(trades)-len(closed), 'excluded': dict(excluded),
        'metrics': {'wr_pct': 100*len(wins)/len(net) if net else None, 'avg_net_pct': sum(net)/len(net) if net else None,
                    'profit_factor': sum(wins)/abs(sum(losses)) if losses and sum(losses) else None,
                    'payoff': (sum(wins)/len(wins))/(abs(sum(losses))/len(losses)) if wins and losses else None,
                    'yearly': yearly, 'exit_reasons': dict(Counter(t['exit_reason'] for t in trades))},
        't1_violations': t1,
        'decision': 'V612_FROZEN_REPLAY_COMPLETE__INDEPENDENT_METRIC_AUDIT_REQUIRED__NO_VARIANTS_NO_PRODUCTION',
        'artifacts': {'dir': str(OUT), 'trades': str(OUT / 'v612_frozen_t1_trades.csv')},
    }
    text=json.dumps(report,ensure_ascii=False,indent=2); (OUT/'v612_report.json').write_text(text); LATEST.write_text(text); print(text)

if __name__ == '__main__': main()
