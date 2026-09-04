#!/usr/bin/env python3
"""V681: ONE frozen strict-T+1 replay of V680 exact-match identities.

Selectors are frozen before this program starts: V680's identity set.  This
program never alters a chain, uses no indicator, and reads future bars only for
fixed exit observation after entry.  It writes research-only audit artifacts.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
M60 = ROOT / 'intraday_cache/sina_m60_v1'
DAILY = ROOT / 'intraday_cache/sina_raw_daily_v379'
V680 = AUDIT / 'v680_frozen_v678_v679_identity_comparison_latest.json'
OUT = AUDIT / f'v681_one_frozen_t1_structure_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v681_one_frozen_t1_structure_replay_latest.json'
FEE_RT = 0.002
IDENTITY_FIELDS = ('symbol', 'weekly_permission_time', 'daily_ssl_time', 'daily_break_time', 'daily_ob_time', 'daily_first_touch_time', 'h60_ssl_time', 'h60_break_time', 'h60_ob_time', 'h60_hold_time')

spec = importlib.util.spec_from_file_location('v677_core', ROOT / 'scripts/v25/v677_three_timeframe_semantic_source_audit.py')
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def read_csv(path: str) -> list[dict]:
    with Path(path).open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def identity(row: dict) -> tuple[str, ...]:
    return tuple(row[k] for k in IDENTITY_FIELDS)


def digest(items: set[tuple[str, ...]]) -> str:
    return hashlib.sha256('\n'.join('|'.join(x) for x in sorted(items)).encode()).hexdigest()


def ts_date(timestamp: str) -> str:
    return ''.join(c for c in timestamp[:10] if c.isdigit())


def idx(rows: list[dict]) -> dict[str, int]:
    return {row['t']: i for i, row in enumerate(rows)}


def target_at_entry(daily: list[dict], weekly: list[dict], entry_date: str, entry_price: float) -> tuple[str, float, str] | None:
    """Nearest higher confirmed weekly BSL, otherwise nearest daily swing high."""
    weekly_events = core.primitives_a(weekly, 'W')
    daily_events = core.primitives_a(daily, 'D')
    def candidates(events: set[tuple], kind: str) -> list[tuple[str, float, str]]:
        values = []
        for event in events:
            if event[1] != 'PIVOT_H':
                continue
            # event[3] is confirmation time, not pivot time; it must be visible at entry.
            confirm_date = event[3]
            if confirm_date < entry_date and event[4] > entry_price:
                values.append((kind, event[4], confirm_date))
        return values
    week = candidates(weekly_events, 'WEEKLY_BSL')
    choices = week if week else candidates(daily_events, 'DAILY_BSL')
    if not choices:
        return None
    kind, price, confirmed_at = min(choices, key=lambda x: x[1])
    return kind, price, confirmed_at


def replay_row(seed: dict, cache: dict[str, tuple[list[dict], list[dict], list[dict]]]) -> dict:
    symbol = seed['symbol']
    daily, h60, weekly = cache[symbol]
    hidx = idx(h60)
    try:
        entry_i = hidx[seed['next_h60_open_time']]
        h2_i = hidx[seed['h60_ssl_time']]
    except KeyError:
        return {**{k: seed[k] for k in IDENTITY_FIELDS}, 'terminal': 'ENTRY_OR_H2_TIME_NOT_IN_SOURCE'}
    entry_bar = h60[entry_i]
    entry = entry_bar['o']
    entry_date = ts_date(entry_bar['t'])
    stop = max(h60[h2_i]['l'], float(seed['daily_zone_low']))
    base = {**{k: seed[k] for k in IDENTITY_FIELDS}, 'entry_time': entry_bar['t'], 'entry_date': entry_date, 'entry_price': entry, 'structure_stop': stop, 'h2_raid_low': h60[h2_i]['l'], 'daily_poi_low': float(seed['daily_zone_low'])}
    if not (entry > stop > 0):
        return {**base, 'terminal': 'INVALID_PREENTRY_STRUCTURE_STOP'}
    target = target_at_entry(daily, weekly, entry_date, entry)
    if target is None:
        return {**base, 'terminal': 'NO_PREENTRY_STRUCTURAL_TARGET'}
    target_kind, target_price, target_confirm = target
    base.update({'target_kind': target_kind, 'structure_target': target_price, 'target_confirmed_at': target_confirm, 'planned_rr': (target_price - entry) / (entry - stop)})
    # Strict A-share T+1: no exit test is even performed on entry_date.
    t1_seen = False
    for bar in h60[entry_i + 1:]:
        bar_date = ts_date(bar['t'])
        if bar_date <= entry_date:
            continue
        t1_seen = True
        hit_stop = bar['l'] <= stop
        hit_target = bar['h'] >= target_price
        if hit_stop or hit_target:
            # Same completed bar ambiguity is fixed by preregistered conservative stop-first.
            exit_price = stop if hit_stop else target_price
            gross = (exit_price / entry - 1.0) * 100.0
            return {**base, 'terminal': 'STOP_HIT' if hit_stop else 'TARGET_HIT', 'exit_time': bar['t'], 'exit_date': bar_date, 'exit_price': exit_price, 'gross_pct': gross, 'net_pct': gross - FEE_RT * 100.0, 'hold_60m_bars': hidx[bar['t']] - entry_i, 't1_exit_ok': True}
    return {**base, 'terminal': 'SOURCE_END_OPEN' if t1_seen else 'NO_T1_BAR_AFTER_ENTRY', 't1_exit_ok': True}


def metric(rows: list[dict]) -> dict:
    closed = [x for x in rows if x.get('terminal') in {'STOP_HIT', 'TARGET_HIT'}]
    values = [float(x['net_pct']) for x in closed]
    wins = [x for x in values if x > 0]
    losses = [x for x in values if x <= 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    return {'n_closed': len(closed), 'wins': len(wins), 'losses': len(losses), 'net_wr_pct': len(wins) / len(closed) * 100 if closed else None, 'net_avg_pct': sum(values) / len(values) if values else None, 'profit_factor': gross_profit / gross_loss if gross_loss else None, 'payoff': (sum(wins) / len(wins)) / abs(sum(losses) / len(losses)) if wins and losses else None, 'gross_avg_pct': sum(float(x['gross_pct']) for x in closed) / len(closed) if closed else None}


def main() -> None:
    gate = json.loads(V680.read_text())
    if gate.get('decision') != 'V680_IDENTITY_EXACT_MATCH__ONE_FROZEN_T1_REPLAY_AUTHORIZED':
        raise SystemExit('V680 did not authorize this single frozen replay')
    rows = [x for x in read_csv(gate['v678_artifact']) if x.get('terminal') == 'SEED_READY']
    frozen = {identity(x) for x in rows}
    if len(rows) != 1579 or len(frozen) != 1579 or digest(frozen) != gate['v678_sha256']:
        raise SystemExit('frozen identity contract mismatch')
    OUT.mkdir(parents=True, exist_ok=False)
    cache = {}
    for symbol in sorted({x['symbol'] for x in rows}):
        code, exchange = symbol.split('.')
        daily = core.daily_rows(DAILY / f'{code}_{exchange}_raw_daily.json.gz')
        h60, bad = core.m60_rows(M60 / f'{code}_{exchange}_m60_sina.json.gz', {x['t']: x['segment'] for x in daily})
        if bad:
            raise RuntimeError(f'{symbol}: unexpected m60 bad days')
        cache[symbol] = (daily, h60, core.weekly_rows(daily))
    replay = [replay_row(row, cache) for row in rows]
    replay_ids = {identity(x) for x in replay}
    t1_violation = sum(1 for x in replay if x.get('exit_date') and x['exit_date'] <= x['entry_date'])
    counts = Counter(x['terminal'] for x in replay)
    overall = metric(replay)
    yearly = {}
    for year in sorted({x.get('entry_date', '')[:4] for x in replay if x.get('entry_date')}):
        yearly[year] = metric([x for x in replay if x.get('entry_date', '').startswith(year)])
    eligible_years = {y: m for y, m in yearly.items() if m['n_closed'] > 0}
    gate_pass = (overall['n_closed'] >= 1000 and all(m['n_closed'] >= 300 for m in eligible_years.values()) and (overall['net_wr_pct'] or -1) >= 55.0 and (overall['net_avg_pct'] or -999) >= .50 and (overall['profit_factor'] or 0) >= 1.15 and (overall['payoff'] or 0) >= .70 and all((m['net_avg_pct'] or -999) > 0 for m in eligible_years.values()) and t1_violation == 0 and replay_ids == frozen)
    fields = sorted({k for row in replay for k in row})
    csv_path = OUT / 'v681_frozen_replay_rows.csv'
    with csv_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(replay)
    report = {'version': 'V681_ONE_FROZEN_STRICT_T1_STRUCTURE_REPLAY', 'generated_at': datetime.now().isoformat(timespec='seconds'), 'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False, 'frozen_identity_sha256': digest(frozen), 'identity_count': len(frozen), 'identity_preserved': replay_ids == frozen, 'entry': 'next H4-hold 60m open', 'stop': 'max(H2 raid low, daily POI low)', 'target': 'nearest higher pre-entry confirmed weekly BSL; otherwise daily BSL', 'same_bar_conflict': 'STOP_FIRST', 'fee_round_trip_pct': FEE_RT * 100, 't1_violation_count': t1_violation, 'terminal_counts': dict(counts), 'overall_closed_metrics': overall, 'yearly_closed_metrics': yearly, 'predeclared_gate': {'n_closed_gte_1000': overall['n_closed'] >= 1000, 'each_year_closed_gte_300': all(m['n_closed'] >= 300 for m in eligible_years.values()), 'net_wr_gte_55': (overall['net_wr_pct'] or -1) >= 55.0, 'net_avg_gte_0_50': (overall['net_avg_pct'] or -999) >= .50, 'pf_gte_1_15': (overall['profit_factor'] or 0) >= 1.15, 'payoff_gte_0_70': (overall['payoff'] or 0) >= .70, 'each_year_net_avg_positive': all((m['net_avg_pct'] or -999) > 0 for m in eligible_years.values()), 'strict_t1_zero': t1_violation == 0, 'identity_preserved': replay_ids == frozen}, 'decision': 'V681_FROZEN_REPLAY_PASS__PRODUCTION_PRE_AUDIT_ONLY' if gate_pass else 'V681_FROZEN_REPLAY_FAIL__CLOSE_ONTOLOGY__NO_VARIANTS', 'artifact': str(csv_path)}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v681_report.json').write_text(text, encoding='utf-8'); LATEST.write_text(text, encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
