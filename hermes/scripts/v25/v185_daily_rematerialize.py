#!/usr/bin/env python3
"""V185 daily production artifact rematerialization.

This is intentionally not a strategy-research script. It validates and refreshes
V185 production artifacts so cron reports, ops diagnostics, API/default routing,
and morning push all use the same V185 contract.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import pathlib
from collections import Counter

ROOT = pathlib.Path('/root/.hermes')
KDIR = ROOT / 'kline_cache'
V185_DIR = ROOT / 'smc_opt_v185_combined_production_candidate'
AUDIT_DIR = ROOT / 'smc_audit'
ENGINE = 'V185_COMBINED_V175_PLUS_TRUE_TAKEOVER_CHILD'

TRADES = V185_DIR / 'v185_trades.json'
PICKS = V185_DIR / 'v185_picks.json'
ACTIVE = V185_DIR / 'v185_active_picks.json'
REPORT = V185_DIR / 'v185_report.json'
CAUSALITY_AUDIT = AUDIT_DIR / 'v432_v185_causality_provenance_latest.json'

OUTCOME_FIELDS = (
    'exit_date', 'exit_idx', 'exit_price', 'exit_reason', 'hold_bars',
    'mae_pct', 'mfe_pct', 'pnl_pct', 'rr_realized', 'won', 'partial_taken',
)


def load(path: pathlib.Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def dkey(v) -> str:
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def fnum(v, default=0.0) -> float:
    try:
        if v in ('', None):
            return default
        return float(v)
    except Exception:
        return default


def kline_path(symbol: str) -> pathlib.Path | None:
    try:
        code, suf = str(symbol).split('.')
    except ValueError:
        return None
    return KDIR / f'{code}_{suf}_daily_750.json'


def load_symbol_bars(symbol: str) -> list[dict]:
    path = kline_path(symbol)
    if not path or not path.exists():
        return []
    rows = load(path, [])
    bars = []
    for b in rows:
        d = dkey(b.get('t') or b.get('date'))
        o, h, l, c = fnum(b.get('o'), None), fnum(b.get('h'), None), fnum(b.get('l'), None), fnum(b.get('c'), None)
        if d and None not in (o, h, l, c):
            bars.append({'date': d, 'o': o, 'h': h, 'l': l, 'c': c})
    return sorted(bars, key=lambda x: x['date'])


def active_lifecycle_fields(row: dict) -> dict:
    """Materialize non-outcome execution contract fields for active picks.

    V185's historical contract is TP=1.5R, max_hold=10, SL=zone_low-1%,
    T+1 exits only. These are pre-entry/design fields, not realized outcomes.
    """
    r = dict(row)
    ep = fnum(r.get('entry_price') or r.get('price'), None)
    zl = fnum(r.get('zone_low') or r.get('dz_low'), None)
    zh = fnum(r.get('zone_high') or r.get('dz_high'), None)
    if ep is not None:
        r['entry_price'] = round(ep, 4)
        r['price'] = r.get('price') or round(ep, 4)
    if zl is not None:
        r['zone_low'] = round(zl, 4)
        r['dz_low'] = r.get('dz_low') or round(zl, 4)
    if zh is not None:
        r['zone_high'] = round(zh, 4)
        r['dz_high'] = r.get('dz_high') or round(zh, 4)
    if ep is not None and zl is not None and zh is not None:
        r['cost_line'] = r.get('cost_line') or round((zl + zh) / 2, 4)
        r['smart_money_cost'] = r.get('smart_money_cost') or r['cost_line']
        sl = fnum(r.get('sl') or r.get('sl_price'), None)
        if sl is None:
            sl = zl * 0.99
        risk_pct = fnum(r.get('risk_pct') or r.get('sl_pct'), None)
        if sl and sl < ep:
            # Active dry-run rows often carry pre-buffer zone risk. Once the
            # formal V185 SL contract is materialized, risk_pct must always be
            # consistent with the executable SL shown to the frontend.
            risk_pct = (ep / sl - 1.0) * 100.0
        if risk_pct is not None and (sl is None or sl >= ep):
            sl = ep * (1.0 - risk_pct / 100.0)
        if sl is not None:
            r['sl'] = round(sl, 4)
            r['sl_price'] = round(sl, 4)
        if risk_pct is not None:
            r['risk_pct'] = round(risk_pct, 4)
            r['sl_pct'] = round(risk_pct, 4)
            r['volatility_pct'] = r.get('volatility_pct') or round(risk_pct, 4)
        if sl is not None and sl < ep:
            tp = ep + (ep - sl) * 1.5
            for field in ('tp', 'tp1', 'tp2', 'tp3'):
                r[field] = r.get(field) or round(tp, 4)
            r['rr'] = r.get('rr') or 1.5
            r['r_mult'] = r.get('r_mult') or 1.5
    r['max_hold'] = r.get('max_hold') or 10
    r['execution_contract'] = r.get('execution_contract') or 'TP=1.5R; max_hold=10 bars; SL=zone_low-1%; T+1 exit starts entry_idx+1'
    r['combo_tp_rule'] = r.get('combo_tp_rule') or 'TP=1.5R / max_hold=10 bars preserved from V172 economics.'
    r['combo_sl_rule'] = r.get('combo_sl_rule') or 'SL below demand OB zone low with V172/V167 buffer; T+1 exit enforcement preserved.'
    bars = load_symbol_bars(str(r.get('symbol') or ''))
    ed = dkey(r.get('entry_date') or r.get('pick_date'))
    t1_bars = [b for b in bars if b['date'] > ed] if ed else []
    if t1_bars:
        r['bars_since_entry'] = len(t1_bars)
        latest = t1_bars[-1]
        r['latest_kline_date'] = latest['date']
        r['latest_close'] = round(latest['c'], 4)
        if ep:
            r['unrealized_pnl_pct'] = round((latest['c'] / ep - 1.0) * 100.0, 4)
        if zl is not None:
            zone_dead = latest['c'] < zl
            r['zone_recovered_latest'] = not zone_dead
            if zone_dead:
                r['monitor_status'] = 'ZONE_DEAD_UNRECOVERED_REVIEW'
                r['live_guard_status'] = 'ZONE_DEAD_UNRECOVERED_REVIEW'
            elif len(t1_bars) >= int(fnum(r.get('max_hold'), 10)):
                r['monitor_status'] = 'STALE_MAX_HOLD_REVIEW'
                r['live_guard_status'] = 'STALE_MAX_HOLD_REVIEW'
    return r


def replay_active_exit(row: dict) -> dict:
    """Replay one active row under the executable V185 contract.

    Returns a non-mutating close record if the row should already be closed by
    T+1 SL/TP/max_hold; otherwise returns {}. Conservative same-bar ordering:
    SL before TP when both touch in one daily bar.
    """
    sym = str(row.get('symbol') or '')
    ed = dkey(row.get('entry_date') or row.get('pick_date') or row.get('select_date'))
    ep = fnum(row.get('entry_price') or row.get('price'), None)
    sl = fnum(row.get('sl') or row.get('sl_price'), None)
    tp = fnum(row.get('tp1') or row.get('tp') or row.get('tp2'), None)
    max_hold = int(fnum(row.get('max_hold'), 10) or 10)
    if not sym or not ed or ep is None or sl is None or tp is None:
        return {}
    bars = [b for b in load_symbol_bars(sym) if b['date'] > ed]  # T+1 only
    if not bars:
        return {}
    for i, b in enumerate(bars, start=1):
        reason = ''
        price = None
        if b['l'] <= sl:
            reason, price = 'SL', sl
        elif b['h'] >= tp:
            reason, price = 'TP', tp
        elif i >= max_hold:
            reason, price = 'TIME', b['c']
        if reason:
            return {
                'symbol': sym,
                'entry_date': ed,
                'entry_price': round(ep, 4),
                'exit_date': b['date'],
                'exit_reason': reason,
                'exit_price': round(price, 4),
                'pnl_pct': round((price / ep - 1.0) * 100.0, 4),
                'hold_bars': i,
                'same_day_exit_violation': b['date'] == ed,
                'source': 'V185_ACTIVE_RECONCILE',
            }
    return {}


def latest_market_date_for_rows(rows: list[dict]) -> str:
    dates = []
    for r in rows:
        bars = load_symbol_bars(str(r.get('symbol') or ''))
        if bars:
            dates.append(bars[-1]['date'])
    return max(dates) if dates else ''


def latest_global_kline_date() -> str:
    refresh = load(ROOT / 'smc_monitor/kline_refresh_latest.json', {})
    vals = [dkey(k) for k in (refresh.get('latest_counts') or {}).keys()]
    vals = [v for v in vals if v]
    return max(vals) if vals else ''


def write_json(path: pathlib.Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def write_csv(path: pathlib.Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys: list[str] = []
    seen = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                keys.append(key)
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def normalize_active_row(row: dict) -> dict:
    r = active_lifecycle_fields(row)
    r['engine'] = ENGINE
    r['production_eligible_v185'] = True
    r['v185_combined_production_candidate'] = True
    r['production_write'] = True
    r['frontend_write'] = True
    r['watchlist_write'] = True
    r['is_active_pick'] = True
    r['pick_scope'] = r.get('pick_scope') or 'ACTIVE_CANDIDATE'
    r['setup_status'] = r.get('setup_status') or 'ACTIVE_CANDIDATE'
    r['status'] = r.get('status') or r.get('setup_status') or 'ACTIVE_CANDIDATE'
    r['monitor_status'] = r.get('monitor_status') or 'ACTIVE_CANDIDATE'
    r['live_guard_status'] = r.get('live_guard_status') or 'PENDING_LIVE_GUARD'
    r['pick_date'] = dkey(r.get('pick_date') or r.get('entry_date'))
    r['select_date'] = dkey(r.get('select_date') or r.get('pick_date') or r.get('entry_date')) or r['pick_date']
    r['join_date'] = dkey(r.get('join_date') or r.get('pick_date') or r.get('entry_date')) or r['pick_date']
    for field in OUTCOME_FIELDS:
        r[field] = ''
    return r


def metrics(trades: list[dict]) -> dict:
    n = len(trades)
    wins = sum(1 for r in trades if str(r.get('won')).lower() == 'true' or fnum(r.get('pnl_pct')) > 0)
    pnl = [fnum(r.get('pnl_pct')) for r in trades]
    same_day = sum(1 for r in trades if dkey(r.get('entry_date')) and dkey(r.get('entry_date')) == dkey(r.get('exit_date')))
    years = Counter((dkey(r.get('entry_date')) or '0000')[:4] for r in trades if dkey(r.get('entry_date')))
    year_wr = {}
    for y in sorted(years):
        rows = [r for r in trades if (dkey(r.get('entry_date')) or '0000')[:4] == y]
        yw = sum(1 for r in rows if str(r.get('won')).lower() == 'true' or fnum(r.get('pnl_pct')) > 0)
        year_wr[y] = round(yw / len(rows) * 100, 2) if rows else 0
    return {
        'n': n,
        'wr': round(wins / n * 100, 2) if n else 0,
        'avg': round(sum(pnl) / n, 4) if n else 0,
        'min_year_n': min(years.values()) if years else 0,
        'year_counts': dict(years),
        'year_wr': year_wr,
        'all_year_wr_min': min(year_wr.values()) if year_wr else 0,
        'micro_profit_pct': round(sum(1 for x in pnl if 0 < x <= 1.0) / n * 100, 2) if n else 0,
        'same_day_exit_violations': same_day,
        'exit_counts': dict(Counter(r.get('exit_reason') or '' for r in trades)),
        'total_pnl': round(sum(pnl), 4),
        'cum_pnl': round(sum(pnl), 4),
    }


def fail_closed_if_causality_rejected():
    audit = load(CAUSALITY_AUDIT, {})
    if audit.get('current_scanner_rebuild_allowed') is True:
        return
    now = dt.datetime.now().isoformat(timespec='seconds')
    report = load(REPORT, {})
    report.update({
        'version': 'V185',
        'decision': 'V185_REJECTED_CAUSALITY__RESEARCH_HISTORY_ONLY',
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'active_pick_count': 0,
        'last_rematerialized_at': now,
        'production_blocker': audit.get('decision') or 'MISSING_V432_CAUSALITY_PASS',
        'causality_audit': str(CAUSALITY_AUDIT),
    })
    write_json(ACTIVE, [])
    write_json(PICKS, [])
    write_json(REPORT, report)
    blocked = {
        'ok': False,
        'version': 'V185',
        'generated_at': now,
        'decision': 'FAIL_CLOSED_EMPTY_BOOK__V185_CAUSALITY_REJECTED',
        'production_write': False,
        'active_picks': 0,
        'causality_audit': audit,
    }
    write_json(AUDIT_DIR / 'v185_daily_rematerialize_latest.json', blocked)
    print(json.dumps(blocked, ensure_ascii=False))
    raise SystemExit(2)


def main():
    fail_closed_if_causality_rejected()
    trades = load(TRADES, [])
    active_src = load(ACTIVE, []) or load(PICKS, [])
    if not trades:
        raise RuntimeError(f'missing V185 trades: {TRADES}')

    normalized = [normalize_active_row(r) for r in active_src]
    previous_reconciled = load(V185_DIR / 'v185_reconciled_closed_active.json', [])
    closed_reconciled = []
    active = []
    for r in normalized:
        close_record = replay_active_exit(r)
        if close_record:
            closed_reconciled.append(close_record)
        else:
            active.append(r)
    report = load(REPORT, {})
    m = metrics(trades)
    active_pollution = sum(1 for r in active for field in OUTCOME_FIELDS if r.get(field) not in ('', None, False))
    reconciled_same_day = sum(1 for r in closed_reconciled if r.get('same_day_exit_violation'))
    if m['same_day_exit_violations'] or reconciled_same_day:
        raise RuntimeError(f'V185 T+1 violation: historical={m["same_day_exit_violations"]}, active_reconciled={reconciled_same_day}')
    if active_pollution:
        raise RuntimeError(f'V185 active outcome pollution: {active_pollution}')

    now = dt.datetime.now().isoformat(timespec='seconds')
    archive_latest = max([dkey(r.get('latest_date') or r.get('exit_date')) for r in previous_reconciled if dkey(r.get('latest_date') or r.get('exit_date'))] or [''])
    latest_market_date = latest_market_date_for_rows(normalized) or latest_global_kline_date() or archive_latest or report.get('latest_market_date') or max([dkey(r.get('pick_date') or r.get('entry_date')) for r in normalized] or [''])
    archive_by_key = {}
    for rec in previous_reconciled + closed_reconciled:
        key = (rec.get('symbol'), dkey(rec.get('entry_date')), dkey(rec.get('exit_date')), rec.get('exit_reason'))
        archive_by_key[key] = rec
    reconciled_archive = list(archive_by_key.values())
    report.update({
        'version': 'V185',
        'engine': ENGINE,
        'decision': 'V185_DAILY_REMATERIALIZE_PASS',
        'last_rematerialized_at': now,
        'production_write': True,
        'frontend_write': True,
        'watchlist_write': True,
        'production_stats': m,
        'metrics': m,
        'n_trades': len(trades),
        'total_trades': len(trades),
        'win_rate': m['wr'],
        'avg_pnl': m['avg'],
        'total_pnl': m['total_pnl'],
        'active_pick_count': len(active),
        'active_reconciled_closed_count': len(reconciled_archive),
        'active_reconciled_closed_new_count': len(closed_reconciled),
        'active_reconciled_exit_counts': dict(Counter(r.get('exit_reason') or '' for r in reconciled_archive)),
        'active_by_entry_date': dict(Counter(dkey(r.get('pick_date') or r.get('entry_date')) for r in active)),
        'active_outcome_pollution': active_pollution,
        'historical_same_day_exit': m['same_day_exit_violations'],
        'latest_market_date': latest_market_date,
        'cron_productionized': True,
        'daily_rematerialize_script': str(pathlib.Path(__file__)),
    })

    write_json(ACTIVE, active)
    write_json(PICKS, active)
    write_json(REPORT, report)
    write_json(V185_DIR / 'v185_reconciled_closed_active.json', reconciled_archive)
    write_csv(V185_DIR / 'v185_active_picks.csv', active)

    audit = {
        'ok': True,
        'version': 'V185',
        'engine': ENGINE,
        'generated_at': now,
        'trades': len(trades),
        'active_picks': len(active),
        'active_reconciled_closed': len(reconciled_archive),
        'active_reconciled_closed_new': len(closed_reconciled),
        'active_reconciled_exit_counts': dict(Counter(r.get('exit_reason') or '' for r in reconciled_archive)),
        'latest_market_date': latest_market_date,
        'metrics': m,
        'active_outcome_pollution': active_pollution,
        'artifacts': {'trades': str(TRADES), 'active': str(ACTIVE), 'picks': str(PICKS), 'report': str(REPORT), 'reconciled_closed_active': str(V185_DIR / 'v185_reconciled_closed_active.json')},
    }
    write_json(AUDIT_DIR / 'v185_daily_rematerialize_latest.json', audit)
    write_json(AUDIT_DIR / f'v185_daily_rematerialize_{dt.datetime.now().strftime("%Y%m%d_%H%M%S")}.json', audit)
    print(json.dumps(audit, ensure_ascii=False))


if __name__ == '__main__':
    main()
