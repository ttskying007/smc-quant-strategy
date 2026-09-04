#!/usr/bin/env python3
"""V324 no-write: V185 delayed-confirmation entry audit.

V315-V323 closed scalar filters, exits, raw daily supply, breadth overlays, and
60min historical execution. This audit tests a different execution hypothesis:
V185 selection remains unchanged, but the system delays entry until the first or
second post-selection daily bar proves demand still holds above the zone.

Important: confirmation uses only bars that have closed before the delayed entry
open. No production/frontend/watchlist writes.
"""
from __future__ import annotations

import json, math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median

ROOT = Path('/root/.hermes')
KDIR = ROOT / 'kline_cache'
AUD = ROOT / 'smc_audit'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUD / f'v324_v185_delayed_confirmation_entry_no_write_{TS}'
LATEST = AUD / 'v324_v185_delayed_confirmation_entry_latest.json'
V185 = ROOT / 'smc_opt_v185_combined_production_candidate' / 'v185_trades.json'

# Production gate is intentionally strict and comparable to the current target.
GATE = {
    'n_min': 300,
    'min_year_n_min': 40,
    'wr_min': 87.0,
    'avg_min': 6.8,
    'year_wr_min': 84.0,
    'micro_max': 1.0,
    't1': 0,
}


def f(x, default=None):
    try:
        if x in (None, ''):
            return default
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def dkey(v) -> str:
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def pct(a, b):
    if a is None or b in (None, 0):
        return None
    return (a / b - 1.0) * 100.0


def kline_path(symbol: str) -> Path:
    code, ex = symbol.split('.')
    p = KDIR / f'{code}_{ex}_daily_750.json'
    if p.exists():
        return p
    return KDIR / f'{code}_{ex}_daily_300.json'


def load_bars(symbol: str):
    p = kline_path(symbol)
    try:
        data = json.load(open(p))
    except Exception:
        return []
    if isinstance(data, dict):
        for k in ('data', 'bars', 'klines'):
            if isinstance(data.get(k), list):
                data = data[k]
                break
    out = []
    for b in data if isinstance(data, list) else []:
        o, h, l, c = f(b.get('o')), f(b.get('h')), f(b.get('l')), f(b.get('c'))
        t = dkey(b.get('t') or b.get('date') or b.get('day'))
        if t and None not in (o, h, l, c):
            out.append({'t': t, 'o': o, 'h': h, 'l': l, 'c': c, 'v': f(b.get('v'), 0)})
    return sorted(out, key=lambda x: x['t'])


def find_idx(bars, date_s):
    for i, b in enumerate(bars):
        if b['t'] == date_s:
            return i
    return None


def finish(src, variant, entry_bar, exit_bar, entry, sl, tp, pnl, reason, exit_price, hold_bars, best, worst, risk):
    out = dict(src)
    out.update({
        'variant': variant,
        'entry_date': entry_bar['t'],
        'exit_date': exit_bar['t'],
        'entry_price': round(entry, 4),
        'exit_price': round(exit_price, 4),
        'sl': round(sl, 4),
        'tp': round(tp, 4),
        'rr': round((tp - entry) / risk, 4) if risk > 0 else None,
        'hold_bars': hold_bars,
        'pnl_pct': round(pnl, 4),
        'exit_reason': reason,
        'same_day_exit_violation': entry_bar['t'] == exit_bar['t'],
        'mfe_pct': round(pct(best, entry), 4),
        'mae_pct': round(pct(worst, entry), 4),
        'mfe_r': round((best - entry) / risk, 4) if risk > 0 else None,
        'mae_r': round((worst - entry) / risk, 4) if risk > 0 else None,
    })
    return out


def simulate(src, bars, entry_i, entry, sl, rr, max_hold, variant):
    if entry_i is None or entry_i >= len(bars) - 1 or entry <= 0 or sl <= 0 or sl >= entry:
        return None
    risk = entry - sl
    tp = entry + risk * rr
    best = -1e18
    worst = 1e18
    # A-share T+1 by construction: first exit check is after entry date.
    for k in range(entry_i + 1, min(len(bars), entry_i + 1 + max_hold)):
        b = bars[k]
        best = max(best, b['h'])
        worst = min(worst, b['l'])
        if b['o'] <= sl:
            return finish(src, variant, bars[entry_i], b, entry, sl, tp, pct(b['o'], entry), 'GAP_SL', b['o'], k - entry_i, best, worst, risk)
        if b['l'] <= sl:
            return finish(src, variant, bars[entry_i], b, entry, sl, tp, pct(sl, entry), 'SL', sl, k - entry_i, best, worst, risk)
        if b['h'] >= tp:
            return finish(src, variant, bars[entry_i], b, entry, sl, tp, pct(tp, entry), 'TP', tp, k - entry_i, best, worst, risk)
    k = min(len(bars) - 1, entry_i + max_hold)
    if k <= entry_i:
        return None
    b = bars[k]
    best = max(best, b['h'])
    worst = min(worst, b['l'])
    return finish(src, variant, bars[entry_i], b, entry, sl, tp, pct(b['c'], entry), 'TIME', b['c'], k - entry_i, best, worst, risk)


def bar_features(row, b, prior_entry, zone_high, sl):
    rng = b['h'] - b['l']
    close_pos = (b['c'] - b['l']) / (rng + 1e-9)
    return {
        'bull': b['c'] > b['o'],
        'close_above_entry': b['c'] >= prior_entry,
        'close_above_zone_high': b['c'] >= zone_high,
        'low_above_sl': b['l'] > sl,
        'low_above_zone_low': b['l'] >= f(row.get('zone_low'), f(row.get('dz_low'), 0)),
        'close_pos_ge_55': close_pos >= 0.55,
        'close_pos_ge_65': close_pos >= 0.65,
        'close_gain_ge_1pct': pct(b['c'], prior_entry) is not None and pct(b['c'], prior_entry) >= 1.0,
    }


def metrics(rows):
    if not rows:
        return {'n': 0}
    vals = [f(r.get('pnl_pct'), 0) for r in rows]
    yrs = defaultdict(list)
    for r, p in zip(rows, vals):
        yrs[dkey(r.get('entry_date'))[:4]].append(p)
    yc = {y: len(v) for y, v in sorted(yrs.items())}
    yw = {y: round(sum(x >= 0.8 for x in v) / len(v) * 100, 4) for y, v in sorted(yrs.items())}
    m = {
        'n': len(rows),
        'wr': round(sum(x >= 0.8 for x in vals) / len(vals) * 100, 4),
        'gross_wr': round(sum(x > 0 for x in vals) / len(vals) * 100, 4),
        'avg': round(mean(vals), 4),
        'median': round(median(vals), 4),
        'loss_pct': round(sum(x < 0 for x in vals) / len(vals) * 100, 4),
        'micro_profit_pct': round(sum(0 < x < 0.8 for x in vals) / len(vals) * 100, 4),
        'min_year_n': min(yc.values()) if yc else 0,
        'year_counts': yc,
        'year_wr': yw,
        'all_year_wr_min': round(min(yw.values()), 4) if yw else 0,
        'same_day_exit_violations': sum(bool(r.get('same_day_exit_violation')) for r in rows),
        'exit_counts': dict(Counter(str(r.get('exit_reason') or '') for r in rows)),
    }
    m['gate_status'] = 'PRODUCTION_PASS' if (
        m['n'] >= GATE['n_min'] and m['min_year_n'] >= GATE['min_year_n_min']
        and m['wr'] >= GATE['wr_min'] and m['avg'] >= GATE['avg_min']
        and m['all_year_wr_min'] >= GATE['year_wr_min'] and m['micro_profit_pct'] <= GATE['micro_max']
        and m['same_day_exit_violations'] == GATE['t1']
    ) else 'FAIL'
    return m


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source = json.load(open(V185))
    bars_cache = {sym: load_bars(sym) for sym in sorted({r['symbol'] for r in source})}
    variants = defaultdict(list)
    missing = 0
    skipped_no_next = 0

    # Conditions are intentionally mechanism-readable, not arbitrary thresholds.
    condition_sets = {
        'D1_BULL_HOLD_ZONE': (1, ['bull', 'close_above_zone_high', 'low_above_sl']),
        'D1_STRONG_HOLD_ZONE': (1, ['close_above_zone_high', 'low_above_sl', 'close_pos_ge_65']),
        'D1_CLOSE_ABOVE_ENTRY': (1, ['bull', 'close_above_entry', 'low_above_sl']),
        'D1_FULL_STRENGTH': (1, ['bull', 'close_above_entry', 'close_above_zone_high', 'low_above_sl', 'close_pos_ge_65']),
        'D2_TWO_BAR_HOLD_ZONE': (2, ['bull', 'close_above_zone_high', 'low_above_sl']),
        'D2_TWO_BAR_STRONG': (2, ['close_above_zone_high', 'low_above_sl', 'close_pos_ge_65']),
    }

    for row in source:
        sym = row['symbol']
        bars = bars_cache.get(sym) or []
        orig_date = dkey(row.get('entry_date'))
        orig_i = find_idx(bars, orig_date)
        if orig_i is None:
            missing += 1
            continue
        sl = f(row.get('sl'), f(row.get('sl_price')))
        zone_high = f(row.get('zone_high'), f(row.get('dz_high'), f(row.get('entry_price'))))
        if sl is None or zone_high is None:
            missing += 1
            continue
        # Same simple replay for original and delayed variants, so entry timing is isolated.
        orig_entry = bars[orig_i]['o']
        tr0 = simulate(row, bars, orig_i, orig_entry, sl, 1.5, 10, 'ORIGINAL_SIMPLE_1P5R_H10')
        if tr0:
            variants['ORIGINAL_SIMPLE_1P5R_H10'].append(tr0)

        for name, (confirm_n, conds) in condition_sets.items():
            if orig_i + confirm_n >= len(bars):
                skipped_no_next += 1
                continue
            ok = True
            # Require every confirmation bar to satisfy the same demand-hold condition.
            for j in range(orig_i, orig_i + confirm_n):
                feats = bar_features(row, bars[j], orig_entry, zone_high, sl)
                if not all(feats.get(c, False) for c in conds):
                    ok = False
                    break
            if not ok:
                continue
            entry_i = orig_i + confirm_n
            entry = bars[entry_i]['o']
            tr = simulate(row, bars, entry_i, entry, sl, 1.5, 10, name)
            if tr:
                variants[name].append(tr)

    ranked = []
    for name, rows in variants.items():
        m = metrics(rows)
        m['variant'] = name
        ranked.append(m)
    ranked.sort(key=lambda x: (x.get('gate_status') == 'PRODUCTION_PASS', x.get('wr', 0), x.get('avg', 0), x.get('all_year_wr_min', 0), x.get('n', 0)), reverse=True)
    passes = [x for x in ranked if x.get('gate_status') == 'PRODUCTION_PASS']
    best = ranked[0] if ranked else {}
    best_rows = variants.get(best.get('variant'), [])

    report = {
        'version': 'V324_V185_DELAYED_CONFIRMATION_ENTRY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'gate': GATE,
        'source': str(V185),
        'coverage': {
            'source_rows': len(source),
            'symbols': len(bars_cache),
            'missing_or_unmapped': missing,
            'skipped_no_next': skipped_no_next,
            'variants': len(variants),
        },
        'baseline_v185_reported': metrics(source),
        'frontier': ranked,
        'production_pass_count': len(passes),
        'production_pass_top10': passes[:10],
        'best': best,
        'decision': 'V324_PRODUCTION_PASS__REQUIRES_CURRENT_SCANNER_DRYRUN' if passes else 'V324_NO_PRODUCTION_PASS__DELAYED_CONFIRMATION_ENTRY_CLOSED',
        'artifacts': {
            'report': str(OUT / 'v324_report.json'),
            'best_rows': str(OUT / 'v324_best_rows.json'),
            'latest': str(LATEST),
        },
    }
    json.dump(report, open(OUT / 'v324_report.json', 'w'), ensure_ascii=False, indent=2)
    json.dump(best_rows, open(OUT / 'v324_best_rows.json', 'w'), ensure_ascii=False, indent=2)
    json.dump(report, open(LATEST, 'w'), ensure_ascii=False, indent=2)
    print(json.dumps({
        'latest': str(LATEST),
        'coverage': report['coverage'],
        'baseline_v185_reported': report['baseline_v185_reported'],
        'production_pass_count': len(passes),
        'decision': report['decision'],
        'best': best,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
