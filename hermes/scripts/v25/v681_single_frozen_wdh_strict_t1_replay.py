#!/usr/bin/env python3
"""V681: one frozen, outcome-blind-authorized W->D->60m structural replay.

This program is intentionally downstream of V680 only.  It never generates,
filters, or ranks chains; it replays every frozen SEED_READY identity exactly
once using the pre-registered execution contract in V681.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
DAILY = ROOT / 'intraday_cache/sina_raw_daily_v379'
M60 = ROOT / 'intraday_cache/sina_m60_v1'
V678 = AUD / 'v678_outcome_blind_wdh_state_machine_seeds_latest.json'
V680 = AUD / 'v680_frozen_v678_v679_identity_comparison_latest.json'
OUT = AUD / f'v681_single_frozen_wdh_strict_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v681_single_frozen_wdh_strict_t1_replay_latest.json'
FEE_PCT = 0.20
FIELDS = ('symbol', 'weekly_permission_time', 'daily_ssl_time', 'daily_break_time', 'daily_ob_time', 'daily_first_touch_time', 'h60_ssl_time', 'h60_break_time', 'h60_ob_time', 'h60_hold_time')
GATE = {'n': 1000, 'each_available_year_n': 300, 'net_wr_pct': 55.0, 'avg_net_pnl_pct': 0.50, 'profit_factor': 1.15, 'payoff': 0.70, 'mean_closed_per_active_month_gt': 4.0, 't1_violations': 0}

spec = importlib.util.spec_from_file_location('v677_core', ROOT / 'scripts/v25/v677_three_timeframe_semantic_source_audit.py')
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def day(t: str) -> str:
    return ''.join(c for c in str(t) if c.isdigit())[:8]


def f(value: object) -> float:
    try:
        value = float(value)
        return value if math.isfinite(value) else 0.0
    except (TypeError, ValueError):
        return 0.0


def identity(row: dict) -> tuple[str, ...]:
    return tuple(row.get(k, '') for k in FIELDS)


def digest(items: set[tuple[str, ...]]) -> str:
    return hashlib.sha256('\n'.join('|'.join(x) for x in sorted(items)).encode()).hexdigest()


def active_unconsumed_highs(rows: list[dict], events: set[tuple], entry_time: str) -> list[dict]:
    """Confirmed pivot highs visible before entry and not raided before entry."""
    idx = {r['t']: n for n, r in enumerate(rows)}
    entry_i = idx[entry_time]
    out = []
    for ev in events:
        if ev[1] != 'PIVOT_H':
            continue
        pivot_time, confirm_time, price = ev[2], ev[3], f(ev[4])
        if confirm_time >= entry_time or price <= 0:
            continue
        pivot_i, confirm_i = idx[pivot_time], idx[confirm_time]
        if max(r['h'] for r in rows[confirm_i + 1:entry_i + 1]) >= price:
            continue
        out.append({'price': price, 'pivot_time': pivot_time, 'confirm_time': confirm_time})
    return out


def structural_target(daily: list[dict], entry_time: str, entry: float) -> dict | None:
    # Entry is intraday: the current daily/weekly candles are not complete and
    # therefore cannot define, consume, or confirm the pre-entry target.
    weekly = core.weekly_rows(daily)
    weekly_events = core.primitives_a(weekly, 'W')
    daily_events = core.primitives_a(daily, 'D')
    entry_date = day(entry_time)
    prior_week = [x['t'] for x in weekly if x['t'] < entry_date]
    if prior_week:
        weekly_highs = [x for x in active_unconsumed_highs(weekly, weekly_events, max(prior_week)) if x['price'] > entry]
        if weekly_highs:
            x = min(weekly_highs, key=lambda y: y['price'])
            return {**x, 'source': 'WEEKLY_BSL'}
    prior_day = [x['t'] for x in daily if x['t'] < entry_date]
    if prior_day:
        daily_highs = [x for x in active_unconsumed_highs(daily, daily_events, max(prior_day)) if x['price'] > entry]
        if daily_highs:
            x = min(daily_highs, key=lambda y: y['price'])
            return {**x, 'source': 'DAILY_BSL_FALLBACK'}
    return None


def replay(seed: dict, daily: list[dict], h60: list[dict]) -> dict:
    hidx = {r['t']: n for n, r in enumerate(h60)}
    entry_i = hidx.get(seed['next_h60_open_time'])
    ssl_i = hidx.get(seed['h60_ssl_time'])
    base = {'entry_time': seed.get('next_h60_open_time', ''), 'entry_date': day(seed.get('next_h60_open_time', ''))}
    if entry_i is None or ssl_i is None:
        return {**base, 'status': 'MISSING_FROZEN_H60_BAR'}
    entry = f(h60[entry_i]['o'])
    sl = min(f(h60[ssl_i]['l']), f(seed['daily_zone_low']))
    if not (entry > sl > 0):
        return {**base, 'status': 'INVALID_PREENTRY_STRUCTURAL_STOP', 'entry_price': entry, 'sl_price': sl}
    target = structural_target(daily, h60[entry_i]['t'], entry)
    risk_pct = (entry / sl - 1.0) * 100.0
    if target is None:
        return {**base, 'status': 'NO_PREENTRY_STRUCTURAL_TARGET', 'entry_price': entry, 'sl_price': sl, 'risk_pct': risk_pct}
    tp = target['price']
    planned_rr = (tp - entry) / (entry - sl)
    executable = [j for j in range(entry_i + 1, len(h60)) if day(h60[j]['t']) > day(h60[entry_i]['t'])]
    if not executable:
        return {**base, 'status': 'NO_T1_EXIT_BAR', 'entry_price': entry, 'sl_price': sl, 'tp_price': tp, 'target_source': target['source'], 'risk_pct': risk_pct, 'planned_rr': planned_rr}
    for j in executable:
        b = h60[j]
        o, lo, hi = f(b['o']), f(b['l']), f(b['h'])
        if o <= sl:
            return closed(base, entry, sl, tp, risk_pct, planned_rr, target, b, j - entry_i, o, 'SL_GAP_T1', False)
        if o >= tp:
            return closed(base, entry, sl, tp, risk_pct, planned_rr, target, b, j - entry_i, o, 'TP_GAP_T1', False)
        hit_sl, hit_tp = lo <= sl, hi >= tp
        if hit_sl and hit_tp:
            return closed(base, entry, sl, tp, risk_pct, planned_rr, target, b, j - entry_i, sl, 'SL_TP_COLLISION_STOP_FIRST_T1', True)
        if hit_sl:
            return closed(base, entry, sl, tp, risk_pct, planned_rr, target, b, j - entry_i, sl, 'STRUCTURAL_SL_T1', False)
        if hit_tp:
            return closed(base, entry, sl, tp, risk_pct, planned_rr, target, b, j - entry_i, tp, 'STRUCTURAL_TP_T1', False)
    return {**base, 'status': 'SOURCE_END_OPEN', 'entry_price': entry, 'sl_price': sl, 'tp_price': tp, 'target_source': target['source'], 'target_pivot_time': target['pivot_time'], 'target_confirm_time': target['confirm_time'], 'risk_pct': risk_pct, 'planned_rr': planned_rr}


def closed(base, entry, sl, tp, risk_pct, planned_rr, target, exit_bar, hold_bars, exit_price, reason, collision):
    gross = (exit_price / entry - 1.0) * 100.0
    net = gross - FEE_PCT
    return {**base, 'status': 'CLOSED', 'entry_price': round(entry, 6), 'sl_price': round(sl, 6), 'tp_price': round(tp, 6), 'target_source': target['source'], 'target_pivot_time': target['pivot_time'], 'target_confirm_time': target['confirm_time'], 'risk_pct': round(risk_pct, 6), 'planned_rr': round(planned_rr, 6), 'exit_time': exit_bar['t'], 'exit_date': day(exit_bar['t']), 'exit_price': round(exit_price, 6), 'exit_reason': reason, 'hold_bars': hold_bars, 'gross_pnl_pct': round(gross, 6), 'fee_pct': FEE_PCT, 'net_pnl_pct': round(net, 6), 't1_violation': day(exit_bar['t']) <= base['entry_date'], 'same_bar_collision': collision}


def metrics(rows: list[dict]) -> dict:
    if not rows:
        return {'n': 0, 'net_wr_pct': 0, 'avg_net_pnl_pct': 0, 'profit_factor': 0, 'payoff': 0}
    net = [f(r['net_pnl_pct']) for r in rows]
    win, loss = [x for x in net if x > 0], [x for x in net if x <= 0]
    return {'n': len(rows), 'net_wr_pct': round(100 * len(win) / len(rows), 4), 'avg_net_pnl_pct': round(sum(net) / len(net), 4), 'median_net_pnl_pct': round(statistics.median(net), 4), 'cum_net_pnl_pct': round(sum(net), 4), 'avg_win_pct': round(sum(win) / len(win), 4) if win else 0, 'avg_loss_pct': round(sum(loss) / len(loss), 4) if loss else 0, 'profit_factor': round(sum(win) / abs(sum(loss)), 4) if loss and sum(loss) else 0, 'payoff': round((sum(win) / len(win)) / abs(sum(loss) / len(loss)), 4) if win and loss and sum(loss) else 0}


def load_symbol(symbol: str) -> tuple[list[dict], list[dict]]:
    code, exchange = symbol.split('.')
    daily = core.daily_rows(DAILY / f'{code}_{exchange}_raw_daily.json.gz')
    h60, bad = core.m60_rows(M60 / f'{code}_{exchange}_m60_sina.json.gz', {x['t']: x['segment'] for x in daily})
    if bad:
        raise ValueError(f'unexpected_m60_bad_days:{len(bad)}')
    return daily, h60


def main() -> None:
    v680 = json.loads(V680.read_text())
    if v680.get('decision') != 'V680_IDENTITY_EXACT_MATCH__ONE_FROZEN_T1_REPLAY_AUTHORIZED':
        raise SystemExit('V680 did not authorize replay')
    v678 = json.loads(V678.read_text())
    with open(v678['artifact'], newline='', encoding='utf-8') as h:
        seeds = [x for x in csv.DictReader(h) if x.get('terminal') == 'SEED_READY']
    frozen = {identity(x) for x in seeds}
    if len(seeds) != len(frozen) or digest(frozen) != v680.get('v678_sha256'):
        raise SystemExit('frozen V678 identity digest/count failed')
    OUT.mkdir(parents=True, exist_ok=False)
    cache, rows, errors = {}, [], []
    for n, seed in enumerate(seeds, 1):
        sym = seed['symbol']
        try:
            if sym not in cache:
                cache[sym] = load_symbol(sym)
            daily, h60 = cache[sym]
            rows.append({**seed, **replay(seed, daily, h60)})
        except Exception as exc:
            errors.append({'symbol': sym, 'identity': '|'.join(identity(seed)), 'reason': f'{type(exc).__name__}:{exc}'})
        if n % 250 == 0:
            print(f'V681 progress {n}/{len(seeds)} rows={len(rows)} errors={len(errors)}', flush=True)
    closed_rows = [x for x in rows if x.get('status') == 'CLOSED']
    yearly = {y: metrics([x for x in closed_rows if x['entry_date'].startswith(y)]) for y in sorted({x['entry_date'][:4] for x in closed_rows})}
    monthly_counts = Counter(x['entry_date'][:6] for x in closed_rows)
    active_month_mean = sum(monthly_counts.values()) / len(monthly_counts) if monthly_counts else 0
    t1 = sum(bool(x.get('t1_violation')) for x in closed_rows)
    overall = metrics(closed_rows)
    yearly_ok = bool(yearly) and all(v['n'] >= GATE['each_available_year_n'] and v['avg_net_pnl_pct'] > 0 for v in yearly.values())
    gate = (not errors and overall['n'] >= GATE['n'] and overall['net_wr_pct'] >= GATE['net_wr_pct'] and overall['avg_net_pnl_pct'] >= GATE['avg_net_pnl_pct'] and overall['profit_factor'] >= GATE['profit_factor'] and overall['payoff'] >= GATE['payoff'] and active_month_mean > GATE['mean_closed_per_active_month_gt'] and yearly_ok and t1 == 0)
    csv_path = OUT / 'v681_frozen_replay_rows.csv'
    fields = sorted({k for x in rows for k in x})
    with csv_path.open('w', newline='', encoding='utf-8') as h:
        w = csv.DictWriter(h, fieldnames=fields); w.writeheader(); w.writerows(rows)
    report = {'version': 'V681_SINGLE_FROZEN_WDH_STRICT_T1_REPLAY_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'), 'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False, 'authorization': v680['decision'], 'frozen_seed_count': len(seeds), 'frozen_identity_sha256': digest(frozen), 'contract': {'entry': 'next 60m open after H4 hold', 'stop': 'min(actual H2 raid-bar low, daily POI low)', 'target': 'nearest unconsumed pre-entry confirmed weekly BSL; daily BSL fallback only', 'exit': 'strict T+1; gap-aware; collision=stop-first; no time stop; source-end remains open', 'round_trip_fee_pct': FEE_PCT, 'search_count': 1}, 'status_counts': dict(Counter(x.get('status') for x in rows)), 'closed_overall': overall, 'closed_by_entry_year': yearly, 'closed_by_entry_month': dict(sorted(monthly_counts.items())), 'mean_closed_per_active_month': round(active_month_mean, 4), 'exit_reason_counts': dict(Counter(x.get('exit_reason') for x in closed_rows)), 'invariants': {'replayed_plus_errors_equals_frozen': len(rows) + len(errors) == len(seeds), 't1_violations': t1, 'same_bar_collisions_stop_first': sum(bool(x.get('same_bar_collision')) for x in closed_rows), 'one_frozen_replay': True, 'no_selector_or_parameter_search': True, 'errors': len(errors), 'error_samples': errors[:50]}, 'promotion_gate': GATE, 'promotion_gate_pass': gate, 'decision': 'V681_FULL_CHAIN_REPLAY_GATE_PASS__PRODUCTION_PREAUDIT_ALLOWED' if gate else 'V681_FULL_CHAIN_REPLAY_GATE_FAIL__CLOSE_WDH_ONTOLOGY_NO_VARIANTS', 'artifacts': {'out_dir': str(OUT), 'rows': str(csv_path), 'latest': str(LATEST)}}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v681_report.json').write_text(text, encoding='utf-8')
    LATEST.write_text(text, encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
