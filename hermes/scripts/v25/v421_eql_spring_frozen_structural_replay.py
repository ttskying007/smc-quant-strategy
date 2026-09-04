#!/usr/bin/env python3
"""V421 one frozen T+1 structural replay of V420 EQL spring candidates.

Execution is immutable: takeover-confirmed -> next-session open; SL below spring
low by 0.5%; TP at the nearest higher confirmed pre-entry swing high; otherwise
20-session time exit. Ambiguous intraday bars resolve SL first. No search.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean, median

ROOT = Path('/root/.hermes')
AUD, KDIR = ROOT / 'smc_audit', ROOT / 'kline_cache'
SOURCE = AUD / 'v420_eql_spring_sos_lps_latest.json'
OUT = AUD / f'v421_eql_spring_frozen_structural_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v421_eql_spring_frozen_structural_replay_latest.json'
FEE_PCT, MAX_HOLD = 0.2, 20


def f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else 0.0
    except (TypeError, ValueError):
        return 0.0


def day(b):
    return ''.join(c for c in str(b.get('t') or b.get('date') or '') if c.isdigit())[:8]


def load(sym):
    try:
        raw = json.loads((KDIR / f"{sym.replace('.', '_')}_daily_750.json").read_text())
    except Exception:
        return []
    return sorted([b for b in raw if day(b) and all(f(b.get(k)) > 0 for k in ('o', 'h', 'l', 'c'))], key=day)


def confirmed_highs(ks, visible_i):
    out = []
    for i in range(3, min(len(ks) - 3, visible_i - 2)):
        hi = f(ks[i]['h'])
        if i + 3 <= visible_i and all(hi > f(ks[j]['h']) for j in range(i - 3, i + 4) if j != i):
            out.append((i, hi))
    return out


def metrics(rows):
    if not rows:
        return {'n': 0}
    pnl = [r['net_pnl_pct'] for r in rows]
    wins, losses = [x for x in pnl if x > 0], [x for x in pnl if x <= 0]
    gross_win, gross_loss = sum(wins), abs(sum(losses))
    return {
        'n': len(rows), 'win_rate_pct': round(len(wins) / len(rows) * 100, 4),
        'avg_net_pnl_pct': round(mean(pnl), 4), 'median_net_pnl_pct': round(median(pnl), 4),
        'profit_factor': round(gross_win / gross_loss, 4) if gross_loss else None,
        'avg_win_pct': round(mean(wins), 4) if wins else None,
        'avg_loss_pct': round(mean(losses), 4) if losses else None,
        'payoff_ratio': round(mean(wins) / abs(mean(losses)), 4) if wins and losses and mean(losses) else None,
        'sl_rate_pct': round(sum(r['exit_reason'].startswith('SL') for r in rows) / len(rows) * 100, 4),
        'tp_rate_pct': round(sum(r['exit_reason'] == 'STRUCTURAL_TP' for r in rows) / len(rows) * 100, 4),
        'time_exit_rate_pct': round(sum(r['exit_reason'] == 'TIME_EXIT_20S' for r in rows) / len(rows) * 100, 4),
        'avg_planned_rr': round(mean(r['planned_rr'] for r in rows if r['planned_rr'] is not None), 4) if any(r['planned_rr'] is not None for r in rows) else None,
        'target_coverage_pct': round(sum(r['tp_price'] is not None for r in rows) / len(rows) * 100, 4),
        'avg_hold_sessions': round(mean(r['hold_sessions'] for r in rows), 2),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    src = json.loads(SOURCE.read_text())
    with Path(src['artifacts']['rows']).open(newline='', encoding='utf-8') as h:
        seeds = [r for r in csv.DictReader(h) if r['lifecycle_state'] == 'TAKEOVER_CONFIRMED']
    rows, skipped, cache = [], Counter(), {}
    for s in seeds:
        sym = s['symbol']
        if sym not in cache:
            cache[sym] = load(sym)
        ks = cache[sym]
        takeover = next((i for i, b in enumerate(ks) if day(b) == s['takeover_date']), None)
        if takeover is None or takeover + 1 >= len(ks):
            skipped['NO_T1_ENTRY'] += 1; continue
        entry_i, entry = takeover + 1, f(ks[takeover + 1]['o'])
        if entry_i + 1 >= len(ks):
            skipped['NO_T1_EXIT_SESSION'] += 1; continue
        sl = f(s['spring_low']) * 0.995
        if not (entry > sl > 0):
            skipped['INVALID_STRUCTURAL_RISK'] += 1; continue
        targets = [price for _, price in confirmed_highs(ks, takeover) if price > entry]
        tp = min(targets) if targets else None
        risk = entry - sl
        planned_rr = (tp - entry) / risk if tp is not None else None
        exit_i = min(len(ks) - 1, entry_i + MAX_HOLD)
        exit_price, reason = f(ks[exit_i]['c']), 'TIME_EXIT_20S'
        for i in range(entry_i + 1, min(len(ks), entry_i + MAX_HOLD + 1)):
            o, lo, hi = f(ks[i]['o']), f(ks[i]['l']), f(ks[i]['h'])
            if o <= sl:
                exit_i, exit_price, reason = i, o, 'SL_GAP'; break
            if lo <= sl:
                exit_i, exit_price, reason = i, sl, 'SL_HIT'; break
            if tp is not None and hi >= tp:
                exit_i, exit_price, reason = i, tp, 'STRUCTURAL_TP'; break
        gross = (exit_price / entry - 1) * 100
        net = gross - FEE_PCT
        rows.append({
            **{k: s[k] for k in ('symbol','combo_key','pool_low1_date','pool_low2_date','spring_date','sos_date','takeover_date','spring_low','range_high','zone_low','zone_high')},
            'entry_date': day(ks[entry_i]), 'entry_price': round(entry, 6),
            'sl_price': round(sl, 6), 'tp_price': round(tp, 6) if tp is not None else None,
            'planned_rr': round(planned_rr, 6) if planned_rr is not None else None,
            'exit_date': day(ks[exit_i]), 'exit_price': round(exit_price, 6), 'exit_reason': reason,
            'hold_sessions': exit_i - entry_i, 'gross_pnl_pct': round(gross, 6), 'fee_pct': FEE_PCT,
            'net_pnl_pct': round(net, 6), 'won': net > 0, 't1_violation': exit_i <= entry_i,
        })
    row_path = OUT / 'v421_trade_rows.csv'
    fields = list(rows[0]) if rows else ['symbol','combo_key']
    with row_path.open('w', newline='') as h:
        w = csv.DictWriter(h, fieldnames=fields); w.writeheader(); w.writerows(rows)
    by_year = {year: metrics([r for r in rows if r['entry_date'].startswith(year)]) for year in ('2023','2024','2025','2026')}
    report = {
        'version': 'V421_EQL_SPRING_FROZEN_STRUCTURAL_REPLAY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'source': str(SOURCE),
        'frozen_execution_contract': 'takeover -> next-session open; SL=spring_low*0.995; TP=nearest higher confirmed pre-entry swing high; conservative SL-first; 20-session time exit; 0.2% cost',
        'candidate_takeovers': len(seeds), 'replayed': len(rows), 'skipped': dict(skipped),
        'overall': metrics(rows), 'by_entry_year': by_year,
        'exit_reasons': dict(Counter(r['exit_reason'] for r in rows)),
        'invariants': {'all_t1_compliant': all(not r['t1_violation'] for r in rows),
                       'no_parameter_or_exit_search': True, 'one_frozen_replay': True},
        'decision': 'RESEARCH_ONLY__ASSESS_ECONOMIC_AND_YEARLY_STABILITY_BEFORE_ANY_PROMOTION',
        'artifacts': {'out_dir': str(OUT), 'rows': str(row_path), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v421_report.json').write_text(text); LATEST.write_text(text); print(text)


if __name__ == '__main__':
    main()
