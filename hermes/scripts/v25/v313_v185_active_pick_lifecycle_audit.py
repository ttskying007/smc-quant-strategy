#!/usr/bin/env python3
"""V313 no-write audit: live lifecycle of V185 active picks.

Purpose: after V312 checkpoint said production is closed, verify the currently
active picks against latest local K-line cache without modifying production,
frontend, or watchlist artifacts. This catches stale bars_since_entry, missing
SL/TP contracts, zone death, and current PnL drift.
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
OUT = AUDIT / f'v313_v185_active_pick_lifecycle_audit_no_write_{TS}'
LATEST = AUDIT / 'v313_v185_active_pick_lifecycle_audit_latest.json'
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
    bars = load_json(kline_path(symbol), [])
    out = []
    for b in bars:
        d = dkey(b.get('t') or b.get('date'))
        o = fnum(b.get('o')); h = fnum(b.get('h')); l = fnum(b.get('l')); c = fnum(b.get('c'))
        if d and None not in (o, h, l, c):
            out.append({'date': d, 'o': o, 'h': h, 'l': l, 'c': c, 'v': fnum(b.get('v'), 0.0)})
    return sorted(out, key=lambda x: x['date'])


def audit_row(r: dict[str, Any]) -> dict[str, Any]:
    sym = str(r.get('symbol') or '')
    ed = dkey(r.get('entry_date') or r.get('pick_date'))
    entry = fnum(r.get('entry_price'))
    zone_low = fnum(r.get('zone_low'))
    zone_high = fnum(r.get('zone_high'))
    risk_pct = fnum(r.get('risk_pct'))
    bars = load_bars(sym)
    latest_date = bars[-1]['date'] if bars else ''
    after = [b for b in bars if b['date'] >= ed]
    tradable_after = [b for b in bars if b['date'] > ed]  # T+1 executable exit/management bars
    if not bars or not after or entry is None:
        return {
            'symbol': sym, 'entry_date': ed, 'latest_date': latest_date,
            'status': 'MISSING_KLINE_OR_ENTRY', 'stored_bars_since_entry': r.get('bars_since_entry'),
        }
    cur = bars[-1]
    highs = [b['h'] for b in tradable_after] or [cur['h']]
    lows = [b['l'] for b in tradable_after] or [cur['l']]
    closes = [b['c'] for b in tradable_after] or [cur['c']]
    actual_bars = len(tradable_after)
    pnl = (cur['c'] / entry - 1.0) * 100.0
    mfe = (max(highs) / entry - 1.0) * 100.0
    mae = (min(lows) / entry - 1.0) * 100.0
    zone_dead_closes = 0
    zone_low_touched = False
    zone_recovered_latest = None
    first_zone_dead = ''
    first_zone_touch = ''
    if zone_low:
        for b in tradable_after:
            if b['l'] <= zone_low and not first_zone_touch:
                first_zone_touch = b['date']
            if b['c'] < zone_low:
                zone_dead_closes += 1
                if not first_zone_dead:
                    first_zone_dead = b['date']
        zone_low_touched = bool(first_zone_touch)
        zone_recovered_latest = cur['c'] >= zone_low
    stale_bars = None
    stored_bars = fnum(r.get('bars_since_entry'))
    if stored_bars is not None:
        stale_bars = int(actual_bars - stored_bars)
    row_sl = fnum(r.get('sl') or r.get('sl_price'))
    derived_sl = row_sl if row_sl is not None else (entry * (1.0 - risk_pct / 100.0) if risk_pct is not None else (zone_low if zone_low else None))
    derived_rr_to_mfe = None
    if risk_pct and risk_pct > 0:
        derived_rr_to_mfe = mfe / risk_pct
    missing_fields = [k for k in ('sl', 'tp1', 'tp2', 'tp3', 'rr') if r.get(k) in ('', None)]
    state = 'OK_HOLD'
    if zone_dead_closes >= 1 and not zone_recovered_latest:
        state = 'ZONE_DEAD_UNRECOVERED'
    elif pnl <= -5:
        state = 'DEEP_DRAWDOWN'
    elif actual_bars >= 10 and pnl < 0:
        state = 'STALE_NEGATIVE_HOLD'
    elif actual_bars >= 10 and mfe > 8 and pnl < 2:
        state = 'MFE_GIVEN_BACK'
    elif actual_bars >= 10:
        state = 'STALE_REVIEW_NEEDED'
    return {
        'symbol': sym,
        'entry_date': ed,
        'latest_date': latest_date,
        'stored_bars_since_entry': r.get('bars_since_entry'),
        'actual_t1_bars_since_entry': actual_bars,
        'stale_bars_delta': stale_bars,
        'entry_price': round(entry, 4),
        'latest_close': round(cur['c'], 4),
        'current_pnl_pct': round(pnl, 4),
        'mfe_pct': round(mfe, 4),
        'mae_pct': round(mae, 4),
        'risk_pct': round(risk_pct, 4) if risk_pct is not None else None,
        'derived_sl': round(derived_sl, 4) if derived_sl is not None else None,
        'derived_rr_to_mfe': round(derived_rr_to_mfe, 4) if derived_rr_to_mfe is not None else None,
        'zone_low': zone_low,
        'zone_high': zone_high,
        'zone_low_touched_t1': zone_low_touched,
        'first_zone_touch_date': first_zone_touch,
        'zone_dead_close_count_t1': zone_dead_closes,
        'first_zone_dead_date': first_zone_dead,
        'zone_recovered_latest': zone_recovered_latest,
        'missing_contract_fields': missing_fields,
        'state': state,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    active = load_json(ACTIVE, [])
    rows = [audit_row(r) for r in active]
    (OUT / 'v313_active_rows.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    summary = {
        'version': 'V313_V185_ACTIVE_PICK_LIFECYCLE_AUDIT_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'active_count': len(active),
        'latest_market_date': max([r.get('latest_date') or '' for r in rows] or ['']),
        'state_counts': dict(Counter(r.get('state') for r in rows)),
        'missing_contract_rows': sum(1 for r in rows if r.get('missing_contract_fields')),
        'stale_bars_rows': sum(1 for r in rows if (r.get('stale_bars_delta') or 0) > 0),
        'zone_dead_unrecovered_rows': sum(1 for r in rows if r.get('state') == 'ZONE_DEAD_UNRECOVERED'),
        'negative_rows': sum(1 for r in rows if (r.get('current_pnl_pct') or 0) < 0),
        'avg_current_pnl_pct': round(sum((r.get('current_pnl_pct') or 0) for r in rows) / len(rows), 4) if rows else 0,
        'avg_mfe_pct': round(sum((r.get('mfe_pct') or 0) for r in rows) / len(rows), 4) if rows else 0,
        'rows': rows,
        'decision': 'NO_PRODUCTION_CHANGE__ACTIVE_LIFECYCLE_REVIEW_REQUIRED' if rows else 'NO_ACTIVE_ROWS',
        'artifacts': {'summary': str(OUT / 'v313_summary.json'), 'rows': str(OUT / 'v313_active_rows.json'), 'latest': str(LATEST)},
    }
    (OUT / 'v313_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
