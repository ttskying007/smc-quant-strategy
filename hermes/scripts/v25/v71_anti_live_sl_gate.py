#!/usr/bin/env python3
"""V71 anti-live-SL gate on V66 results.

Isolated candidate only. Does not modify V66 production.
Hardens live execution against: entry above zone, SL too close to zone low,
and next-bar gap-through-SL risk.
"""
from __future__ import annotations
import json, pathlib, statistics, collections
from datetime import datetime

ROOT = pathlib.Path('/root/.hermes')
SRC = ROOT / 'smc_opt_v66/v66_trades.json'
OUT = ROOT / 'smc_opt_v71'
AUDIT = ROOT / 'smc_audit'
OUT.mkdir(exist_ok=True)
AUDIT.mkdir(exist_ok=True)

MIN_SL_BELOW_ZONE_PCT = 1.0
MAX_ENTRY_ABOVE_ZONE_HIGH_PCT = 0.8
MAX_RISK_PCT = 6.0
MAX_NEXT_OPEN_GAP_DOWN_PCT = 2.5

def f(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d

def load(path, default):
    try:
        return json.loads(pathlib.Path(path).read_text())
    except Exception:
        return default

def kline_path(symbol):
    code, ex = str(symbol).split('.')
    return ROOT / f'kline_cache/{code}_{ex}_daily_300.json'

def dkey(v):
    return ''.join(ch for ch in str(v or '') if ch.isdigit())[:8]

def load_bars(symbol):
    rows = load(kline_path(symbol), []) or []
    out = []
    for b in rows:
        date = dkey(b.get('t') or b.get('date'))
        if not date:
            continue
        out.append({
            'date': date,
            'open': f(b.get('o') or b.get('open')),
            'high': f(b.get('h') or b.get('high')),
            'low': f(b.get('l') or b.get('low')),
            'close': f(b.get('c') or b.get('close')),
        })
    return out

def bar_by_date(symbol, date):
    date = dkey(date)
    for b in load_bars(symbol):
        if b['date'] == date:
            return b
    return None

def metrics(rows):
    if not rows:
        return {'n': 0}
    pnl = [f(r.get('pnl_pct')) for r in rows]
    wins = [x for x in pnl if x > 0]
    losses = [-x for x in pnl if x <= 0]
    exit_counts = collections.Counter(r.get('exit_reason') for r in rows)
    return {
        'n': len(rows),
        'wr': round(len(wins) / len(rows) * 100, 2),
        'sl_rate': round(sum(exit_counts.get(x, 0) for x in ('SL_HIT', 'GAP_SL_HIT')) / len(rows) * 100, 2),
        'avg_pnl': round(statistics.mean(pnl), 3),
        'avg_win': round(statistics.mean(wins), 3) if wins else 0,
        'avg_loss': round(statistics.mean(losses), 3) if losses else 0,
        'realized_rr': round((statistics.mean(wins) / statistics.mean(losses)), 3) if wins and losses else 0,
        'exit_counts': dict(exit_counts),
    }

def gate(t):
    reasons = []
    ep = f(t.get('entry_price'))
    sl = f(t.get('sl'))
    zl = f(t.get('raw_zone_low'))
    zh = f(t.get('raw_zone_high'))
    risk = f(t.get('risk_pct'))
    if zl and zh and zl > zh:
        zl, zh = zh, zl
    if not (ep and sl and zl and zh):
        reasons.append('MISSING_PRICE_OR_ZONE')
        return False, reasons, {}
    entry_above_zh = (ep / zh - 1) * 100
    sl_below_zl = (zl / sl - 1) * 100
    if entry_above_zh > MAX_ENTRY_ABOVE_ZONE_HIGH_PCT:
        reasons.append('ENTRY_TOO_FAR_ABOVE_ZONE_HIGH')
    if sl_below_zl < MIN_SL_BELOW_ZONE_PCT:
        reasons.append('SL_BUFFER_BELOW_ZONE_LT_1PCT')
    if risk > MAX_RISK_PCT:
        reasons.append('RISK_GT_6PCT')
    entry_bar = bar_by_date(t.get('symbol'), t.get('entry_date'))
    if entry_bar and ep:
        gap_down = (ep / entry_bar['open'] - 1) * 100 if entry_bar['open'] else 0
        if gap_down > MAX_NEXT_OPEN_GAP_DOWN_PCT:
            reasons.append('T1_ENTRY_GAP_DOWN_RISK')
    diag = {'entry_above_zone_high_pct': round(entry_above_zh, 3), 'sl_below_zone_low_pct': round(sl_below_zl, 3), 'risk_pct': risk}
    return not reasons, reasons, diag

def main():
    src = load(SRC, []) or []
    kept, rejected = [], []
    for t in src:
        ok, reasons, diag = gate(t)
        nt = dict(t)
        nt['engine'] = 'V71_ANTI_LIVE_SL_GATE'
        nt['definition_version'] = 'V71_ANTI_LIVE_SL_GATE'
        nt['v71_gate_reasons'] = reasons
        nt['v71_live_sl_diag'] = diag
        if ok:
            kept.append(nt)
        else:
            nt['pick_scope'] = 'REJECTED_V71_ANTI_LIVE_SL'
            nt['reject_reason'] = ';'.join(reasons)
            rejected.append(nt)
    picks = []
    for t in kept:
        picks.append({
            'symbol': t.get('symbol'), 'name': t.get('name',''),
            'pick_date': t.get('signal_date'), 'entry_date': t.get('entry_date'),
            'join_date': t.get('entry_date'), 'price': t.get('entry_price'),
            'entry_price': t.get('entry_price'), 'sl': t.get('sl'),
            'risk_pct': t.get('risk_pct'), 'zone_type': t.get('zone_type'),
            'conf_type': t.get('conf_type'), 'v59_setup_family': t.get('v59_setup_family'),
            'cost_line': t.get('v25_cost_line') or t.get('entry_price'),
            'volatility_pct': t.get('risk_pct'), 'pnl_pct': t.get('pnl_pct'),
            'exit_reason': t.get('exit_reason'), 'pick_scope': 'V71_CANDIDATE',
            'is_active_pick': t.get('entry_date','') >= '2026-01-01',
        })
    report = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'source': str(SRC), 'n_source': len(src), 'n_trades': len(kept), 'n_rejected': len(rejected),
        'thresholds': {
            'min_sl_below_zone_pct': MIN_SL_BELOW_ZONE_PCT,
            'max_entry_above_zone_high_pct': MAX_ENTRY_ABOVE_ZONE_HIGH_PCT,
            'max_risk_pct': MAX_RISK_PCT,
            'max_next_open_gap_down_pct': MAX_NEXT_OPEN_GAP_DOWN_PCT,
        },
        'base_metrics': metrics(src), 'v71_metrics': metrics(kept),
        'reject_counts': dict(collections.Counter(';'.join(r.get('v71_gate_reasons') or []) for r in rejected)),
        'rejected_loss_roots': dict(collections.Counter(r.get('exit_reason') for r in rejected if f(r.get('pnl_pct')) <= 0)),
    }
    (OUT / 'v71_trades.json').write_text(json.dumps(kept, ensure_ascii=False, indent=2))
    (OUT / 'v71_rejected.json').write_text(json.dumps(rejected, ensure_ascii=False, indent=2))
    (OUT / 'v71_picks.json').write_text(json.dumps(picks, ensure_ascii=False, indent=2))
    (OUT / 'v71_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (AUDIT / 'v71_anti_live_sl_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
