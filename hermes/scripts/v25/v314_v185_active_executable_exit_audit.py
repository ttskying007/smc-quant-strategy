#!/usr/bin/env python3
"""V314 no-write audit: executable exit status of V185 active picks.

This script does NOT modify production/frontend/watchlist files. It replays each
currently active V185 pick on local daily K-line cache with the V185 executable
contract (T+1 only, SL, TP=1.5R from materialized tp1, max_hold) and reports
whether any "active" row is already mechanically closed by its own contract.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

BASE = Path('/root/.hermes')
KDIR = BASE / 'kline_cache'
V185_DIR = BASE / 'smc_opt_v185_combined_production_candidate'
AUDIT = BASE / 'smc_audit'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v314_v185_active_executable_exit_audit_no_write_{TS}'
LATEST = AUDIT / 'v314_v185_active_executable_exit_audit_latest.json'
ACTIVE = V185_DIR / 'v185_active_picks.json'


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def dkey(v: Any) -> str:
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def fnum(v: Any, default: float | None = None) -> float | None:
    try:
        if v in ('', None):
            return default
        return float(v)
    except Exception:
        return default


def kline_path(symbol: str) -> Path:
    code, suf = symbol.split('.')
    return KDIR / f'{code}_{suf}_daily_750.json'


def load_bars(symbol: str) -> list[dict[str, Any]]:
    rows = load_json(kline_path(symbol), [])
    out = []
    for b in rows:
        d = dkey(b.get('t') or b.get('date'))
        o = fnum(b.get('o')); h = fnum(b.get('h')); l = fnum(b.get('l')); c = fnum(b.get('c'))
        if d and None not in (o, h, l, c):
            out.append({'date': d, 'o': o, 'h': h, 'l': l, 'c': c})
    return sorted(out, key=lambda x: x['date'])


def replay_exit(row: dict[str, Any]) -> dict[str, Any]:
    sym = str(row.get('symbol') or '')
    entry_date = dkey(row.get('entry_date') or row.get('pick_date') or row.get('select_date'))
    entry = fnum(row.get('entry_price') or row.get('price'))
    sl = fnum(row.get('sl') or row.get('sl_price'))
    tp = fnum(row.get('tp1') or row.get('tp') or row.get('tp2'))
    max_hold = int(fnum(row.get('max_hold'), 10) or 10)
    zone_low = fnum(row.get('zone_low') or row.get('dz_low'))
    zone_high = fnum(row.get('zone_high') or row.get('dz_high'))
    bars = load_bars(sym)
    t1 = [b for b in bars if entry_date and b['date'] > entry_date]
    latest = bars[-1] if bars else None
    base = {
        'symbol': sym,
        'entry_date': entry_date,
        'entry_price': entry,
        'sl': sl,
        'tp1': tp,
        'max_hold': max_hold,
        'zone_low': zone_low,
        'zone_high': zone_high,
        'latest_date': latest['date'] if latest else '',
        'latest_close': latest['c'] if latest else None,
        't1_bars': len(t1),
        'contract_complete': all(x is not None for x in (entry, sl, tp)) and bool(entry_date),
        'same_day_exit_violation': False,
    }
    if not base['contract_complete'] or not t1:
        base.update({'mechanical_state': 'UNREPLAYABLE_OR_NO_T1_BAR', 'exit_date': '', 'exit_reason': '', 'exit_price': None, 'pnl_pct': None, 'hold_bars': 0})
        return base

    assert entry is not None and sl is not None and tp is not None
    exit_bar = None
    exit_reason = ''
    exit_price = None
    hold_bars = 0
    for i, b in enumerate(t1, start=1):
        hold_bars = i
        # Conservative same-bar ordering: if both SL and TP touched, count SL first.
        if b['l'] <= sl:
            exit_bar = b; exit_reason = 'SL'; exit_price = sl; break
        if b['h'] >= tp:
            exit_bar = b; exit_reason = 'TP'; exit_price = tp; break
        if i >= max_hold:
            exit_bar = b; exit_reason = 'TIME'; exit_price = b['c']; break
    if exit_bar is None:
        cur = latest or t1[-1]
        pnl = (cur['c'] / entry - 1) * 100
        mfe = (max(b['h'] for b in t1) / entry - 1) * 100
        mae = (min(b['l'] for b in t1) / entry - 1) * 100
        zone_dead = bool(zone_low is not None and cur['c'] < zone_low)
        base.update({
            'mechanical_state': 'STILL_OPEN_BY_CONTRACT',
            'exit_date': '', 'exit_reason': '', 'exit_price': None,
            'pnl_pct': round(pnl, 4), 'mfe_pct': round(mfe, 4), 'mae_pct': round(mae, 4),
            'hold_bars': len(t1), 'zone_dead_latest': zone_dead,
            'recommended_action': 'REVIEW_ZONE_DEAD' if zone_dead else 'HOLD_OR_MANUAL_REVIEW',
        })
        return base

    pnl = (exit_price / entry - 1) * 100
    mfe_until_exit = (max(b['h'] for b in t1[:hold_bars]) / entry - 1) * 100
    mae_until_exit = (min(b['l'] for b in t1[:hold_bars]) / entry - 1) * 100
    base.update({
        'mechanical_state': 'SHOULD_BE_CLOSED_BY_CONTRACT',
        'exit_date': exit_bar['date'],
        'exit_reason': exit_reason,
        'exit_price': round(exit_price, 4),
        'pnl_pct': round(pnl, 4),
        'mfe_pct': round(mfe_until_exit, 4),
        'mae_pct': round(mae_until_exit, 4),
        'hold_bars': hold_bars,
        'same_day_exit_violation': exit_bar['date'] == entry_date,
        'recommended_action': f'CLOSE_RECONCILE_{exit_reason}_NO_WRITE',
    })
    return base


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    active = load_json(ACTIVE, [])
    rows = [replay_exit(r) for r in active]
    state_counts = Counter(r.get('mechanical_state') for r in rows)
    reason_counts = Counter(r.get('exit_reason') or 'OPEN' for r in rows)
    closed = [r for r in rows if r.get('mechanical_state') == 'SHOULD_BE_CLOSED_BY_CONTRACT']
    open_rows = [r for r in rows if r.get('mechanical_state') == 'STILL_OPEN_BY_CONTRACT']
    same_day = [r for r in rows if r.get('same_day_exit_violation')]
    summary = {
        'version': 'V314_V185_ACTIVE_EXECUTABLE_EXIT_AUDIT_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'source': str(ACTIVE),
        'active_count': len(active),
        'state_counts': dict(state_counts),
        'exit_reason_counts': dict(reason_counts),
        'should_be_closed_count': len(closed),
        'still_open_count': len(open_rows),
        'same_day_exit_violations': len(same_day),
        'closed_avg_pnl_pct': round(sum((r.get('pnl_pct') or 0) for r in closed) / len(closed), 4) if closed else 0,
        'open_avg_unrealized_pnl_pct': round(sum((r.get('pnl_pct') or 0) for r in open_rows) / len(open_rows), 4) if open_rows else 0,
        'rows': rows,
        'decision': 'ACTIVE_WATCHLIST_RECONCILIATION_REQUIRED_NO_WRITE' if closed else 'NO_MECHANICAL_CLOSE_REQUIRED_NO_WRITE',
        'artifacts': {
            'summary': str(OUT / 'v314_summary.json'),
            'rows': str(OUT / 'v314_rows.json'),
            'latest': str(LATEST),
        },
    }
    (OUT / 'v314_rows.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    (OUT / 'v314_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
