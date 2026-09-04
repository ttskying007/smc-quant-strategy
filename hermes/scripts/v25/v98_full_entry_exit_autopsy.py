#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path('/root/.hermes')
TRADE_PATH = ROOT / 'smc_opt_v98_reachable_5r_probability_gate' / 'v98_structural_trades.json'
KLINE_DIR = ROOT / 'kline_cache'
OUT_DIR = ROOT / 'smc_opt_v98_reachable_5r_probability_gate'
OUT_JSON = OUT_DIR / 'v98_full_entry_exit_autopsy.json'
OUT_CSV = OUT_DIR / 'v98_trade_autopsy_rows.csv'
MAX_FUTURE = 40


def num(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == '':
            return default
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def date_key(v: Any) -> str:
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def year(v: Any) -> str:
    d = date_key(v)
    return d[:4] if len(d) >= 4 else 'UNKNOWN'


def bar_date(b: Dict[str, Any]) -> str:
    return date_key(b.get('t') or b.get('date'))


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text())


def kline_path(symbol: str) -> Path:
    stem = symbol.replace('.', '_')
    for suffix in ('daily_750', 'daily_300'):
        p = KLINE_DIR / f'{stem}_{suffix}.json'
        if p.exists():
            return p
    return KLINE_DIR / f'{stem}_daily_750.json'


def pct(a: int, b: int) -> float:
    return round(a / b * 100, 2) if b else 0.0


def q(vals: List[float], p: float) -> float:
    vals = sorted(v for v in vals if math.isfinite(v))
    if not vals:
        return 0.0
    i = int(round((len(vals) - 1) * p))
    return round(vals[max(0, min(i, len(vals)-1))], 4)


def stats(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    wins = sum(1 for r in rows if num(r.get('pnl_pct')) > 0)
    pnls = [num(r.get('pnl_pct')) for r in rows]
    holds = [num(r.get('hold_bars_realized')) for r in rows]
    return {
        'n': n,
        'wins': wins,
        'losses': n - wins,
        'wr': pct(wins, n),
        'avg_pnl': round(sum(pnls) / n, 4) if n else 0,
        'median_pnl': q(pnls, 0.5),
        'cum_pnl': round(sum(pnls), 4),
        'sl_rate': pct(sum(1 for r in rows if r.get('exit_reason') == 'SL_HIT'), n),
        'tp2_rate': pct(sum(1 for r in rows if r.get('exit_reason') == 'TP2_MAIN_HIT'), n),
        'time_stop_rate': pct(sum(1 for r in rows if r.get('exit_reason') == 'TIME_STOP'), n),
        'avg_hold': round(sum(holds) / n, 2) if n else 0,
        'exit_counts': dict(Counter(r.get('exit_reason') for r in rows)),
    }


def entry_bucket(row: Dict[str, Any], ks: List[Dict[str, Any]]) -> Dict[str, Any]:
    ep = num(row.get('entry_price'))
    sl = num(row.get('sl'))
    risk = max(ep - sl, 1e-9)
    zl = num(row.get('zone_low'))
    zh = num(row.get('zone_high'))
    width = max(zh - zl, 1e-9)
    entry_pos = (ep - zl) / width if zl and zh else 999.0
    entry_idx = int(num(row.get('entry_idx'), -1))
    touch_idx = int(num(row.get('touch_idx'), -1))
    reclaim_idx = int(num(row.get('reclaim_idx'), -1))
    window = ks[entry_idx:min(len(ks), entry_idx + 11)] if 0 <= entry_idx < len(ks) else []
    lows = [num(b.get('l')) for b in window]
    highs = [num(b.get('h')) for b in window]
    min10 = min(lows) if lows else ep
    max10 = max(highs) if highs else ep
    better_lower_r = max(0.0, (ep - min10) / risk)
    immediate_adverse_r = max(0.0, (ep - min10) / risk)
    immediate_favorable_r = max(0.0, (max10 - ep) / risk)
    flags: List[str] = []
    if reclaim_idx >= 0 and entry_idx >= 0 and entry_idx < reclaim_idx:
        flags.append('ENTRY_BEFORE_RECLAIM_EARLY')
    if entry_pos > 0.75:
        flags.append('ENTRY_PRICE_HIGH_IN_ZONE')
    if entry_pos > 1.0:
        flags.append('ENTRY_ABOVE_ZONE_CHASE')
    if better_lower_r >= 0.5 and min10 > sl:
        flags.append('ENTRY_EARLY_BETTER_LOWER_FILL_WITHOUT_SL')
    if immediate_adverse_r >= 1.0 and row.get('exit_reason') == 'SL_HIT' and num(row.get('hold_bars_realized')) <= 5:
        flags.append('ENTRY_TOO_EARLY_FAST_SL')
    if reclaim_idx >= 0 and entry_idx > reclaim_idx + 3:
        flags.append('ENTRY_TIME_LATE_AFTER_RECLAIM')
    if not flags:
        flags.append('ENTRY_OK')
    return {
        'entry_pos_in_zone': round(entry_pos, 4),
        'entry_timing_delta_reclaim': entry_idx - reclaim_idx if reclaim_idx >= 0 and entry_idx >= 0 else 999,
        'entry_better_lower_r_10b': round(better_lower_r, 4),
        'entry_favorable_r_10b': round(immediate_favorable_r, 4),
        'entry_flags': flags,
    }


def exit_bucket(row: Dict[str, Any], ks: List[Dict[str, Any]]) -> Dict[str, Any]:
    ep = num(row.get('entry_price'))
    sl = num(row.get('sl'))
    risk = max(ep - sl, 1e-9)
    exit_idx = int(num(row.get('exit_idx'), -1))
    tp2 = num(row.get('tp2'))
    tp3 = num(row.get('tp3'))
    reason = row.get('exit_reason')
    future = ks[exit_idx + 1:min(len(ks), exit_idx + 1 + MAX_FUTURE)] if 0 <= exit_idx < len(ks) else []
    max_future_h = max([num(b.get('h')) for b in future], default=num(row.get('exit_price')))
    min_future_l = min([num(b.get('l')) for b in future], default=num(row.get('exit_price')))
    future_up_r = max(0.0, (max_future_h - num(row.get('exit_price'))) / risk)
    future_down_r = max(0.0, (num(row.get('exit_price')) - min_future_l) / risk)
    mfe_r = num(row.get('mfe_r'))
    mae_r = num(row.get('mae_r'))
    hold = num(row.get('hold_bars_realized'))
    flags: List[str] = []
    if reason == 'TP2_MAIN_HIT':
        if tp3 and max_future_h >= tp3:
            flags.append('EXIT_EARLY_TP2_THEN_TP3_WITHIN_40B')
        elif future_up_r >= 2.0:
            flags.append('EXIT_EARLY_TP2_LEFT_2R_PLUS')
        else:
            flags.append('EXIT_OK_TP2')
    elif reason == 'SL_HIT':
        if mfe_r >= 5.0:
            flags.append('EXIT_TOO_LATE_GAVE_BACK_5R_TO_SL')
        elif mfe_r >= 2.0:
            flags.append('EXIT_TOO_LATE_GAVE_BACK_2R_TO_SL')
        elif hold <= 5:
            flags.append('EXIT_FAST_SL_SIGNAL_OR_ENTRY_FAIL')
        else:
            flags.append('EXIT_OK_STRUCTURAL_SL')
    elif reason == 'TIME_STOP':
        if mfe_r >= 2.0:
            flags.append('EXIT_TOO_LATE_TIME_STOP_AFTER_2R_MFE')
        elif max_future_h >= tp2 if tp2 else False:
            flags.append('EXIT_EARLY_TIME_STOP_THEN_TP2')
        elif future_up_r >= 2.0:
            flags.append('EXIT_EARLY_TIME_STOP_LEFT_2R_PLUS')
        else:
            flags.append('EXIT_OK_TIME_STOP')
    else:
        flags.append('EXIT_OTHER')
    return {
        'future_up_r_40b': round(future_up_r, 4),
        'future_down_r_40b': round(future_down_r, 4),
        'future_tp3_hit_after_exit': bool(tp3 and max_future_h >= tp3),
        'future_tp2_hit_after_exit': bool(tp2 and max_future_h >= tp2),
        'exit_flags': flags,
        'mfe_r': round(mfe_r, 4),
        'mae_r': round(mae_r, 4),
        'hold_bars_realized': round(hold, 0),
    }


def bucket_table(rows: List[Dict[str, Any]], key: str, limit: int = 30) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[str(r.get(key) or '')].append(r)
    ranked = sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True)[:limit]
    return {k: stats(v) for k, v in ranked}


def main() -> None:
    trades = load_json(TRADE_PATH, [])
    prod = [r for r in trades if r.get('production_grade') == 'A_PRODUCTION']
    kcache: Dict[str, List[Dict[str, Any]]] = {}
    audit_rows: List[Dict[str, Any]] = []
    bad = Counter()
    for r in prod:
        sym = str(r.get('symbol'))
        if sym not in kcache:
            p = kline_path(sym)
            kcache[sym] = load_json(p, []) or []
        ks = kcache[sym]
        if not ks:
            bad['missing_kline'] += 1
            continue
        ei = int(num(r.get('entry_idx'), -1)); xi = int(num(r.get('exit_idx'), -1))
        if not (0 <= ei < len(ks) and 0 <= xi < len(ks)):
            bad['idx_out_of_range'] += 1
            continue
        er = entry_bucket(r, ks)
        xr = exit_bucket(r, ks)
        out = dict(r)
        out.update(er); out.update(xr)
        out['entry_year'] = year(r.get('entry_date'))
        out['exit_year'] = year(r.get('exit_date'))
        out['entry_date_match'] = date_key(r.get('entry_date')) == bar_date(ks[ei])
        out['exit_date_match'] = date_key(r.get('exit_date')) == bar_date(ks[xi])
        out['t1_violation'] = date_key(r.get('entry_date')) == date_key(r.get('exit_date')) or xi <= ei
        audit_rows.append(out)
    yearly: Dict[str, Any] = {}
    for y in sorted(set(r['entry_year'] for r in audit_rows)):
        yearly[y] = stats([r for r in audit_rows if r['entry_year'] == y])
    flag_counts = Counter()
    exit_flag_counts = Counter()
    for r in audit_rows:
        for f in r['entry_flags']:
            flag_counts[f] += 1
        for f in r['exit_flags']:
            exit_flag_counts[f] += 1
    early = [r for r in audit_rows if 'ENTRY_BEFORE_RECLAIM_EARLY' in r['entry_flags']]
    high = [r for r in audit_rows if 'ENTRY_PRICE_HIGH_IN_ZONE' in r['entry_flags'] or 'ENTRY_ABOVE_ZONE_CHASE' in r['entry_flags']]
    better = [r for r in audit_rows if 'ENTRY_EARLY_BETTER_LOWER_FILL_WITHOUT_SL' in r['entry_flags']]
    sell_early = [r for r in audit_rows if any(f.startswith('EXIT_EARLY') for f in r['exit_flags'])]
    sell_late = [r for r in audit_rows if any(f.startswith('EXIT_TOO_LATE') for f in r['exit_flags'])]
    report = {
        'input': str(TRADE_PATH),
        'all_rows': len(trades),
        'production_rows': len(prod),
        'audited_rows': len(audit_rows),
        'bad_rows': dict(bad),
        'overall': stats(audit_rows),
        'yearly_by_entry_year': yearly,
        'validation': {
            't1_violations': sum(1 for r in audit_rows if r['t1_violation']),
            'entry_date_mismatch': sum(1 for r in audit_rows if not r['entry_date_match']),
            'exit_date_mismatch': sum(1 for r in audit_rows if not r['exit_date_match']),
            'missing_required_core': sum(1 for r in audit_rows if any(r.get(k) in (None, '', 0) for k in ['entry_price','sl','tp2','tp3','zone_low','zone_high','pick_date','join_date'])),
        },
        'entry_flag_counts': dict(flag_counts),
        'entry_problem_stats': {
            'entry_before_reclaim_early': stats(early),
            'entry_high_or_above_zone': stats(high),
            'entry_better_lower_without_sl': stats(better),
        },
        'exit_flag_counts': dict(exit_flag_counts),
        'exit_problem_stats': {
            'sell_early': stats(sell_early),
            'sell_late': stats(sell_late),
        },
        'buckets': {
            'market_state': bucket_table(audit_rows, 'market_state'),
            'pd_zone': bucket_table(audit_rows, 'pd_zone'),
            'poi_type': bucket_table(audit_rows, 'poi_type'),
            'event_type': bucket_table(audit_rows, 'event_type'),
            'entry_flag_primary': bucket_table([{**r, 'entry_flag_primary': r['entry_flags'][0]} for r in audit_rows], 'entry_flag_primary'),
            'exit_flag_primary': bucket_table([{**r, 'exit_flag_primary': r['exit_flags'][0]} for r in audit_rows], 'exit_flag_primary'),
        },
        'worst_entry_examples': sorted([
            {k: r.get(k) for k in ['symbol','entry_date','exit_date','exit_reason','pnl_pct','entry_price','zone_low','zone_high','entry_pos_in_zone','entry_timing_delta_reclaim','entry_better_lower_r_10b','mfe_r','mae_r','market_state','pd_zone','poi_type','event_type','entry_flags','exit_flags']}
            for r in audit_rows if r.get('exit_reason') == 'SL_HIT'
        ], key=lambda x: (-num(x.get('entry_better_lower_r_10b')), num(x.get('pnl_pct'))))[:50],
        'worst_exit_examples': sorted([
            {k: r.get(k) for k in ['symbol','entry_date','exit_date','exit_reason','pnl_pct','entry_price','exit_price','tp2','tp3','future_up_r_40b','future_tp3_hit_after_exit','mfe_r','mae_r','hold_bars_realized','market_state','pd_zone','poi_type','event_type','entry_flags','exit_flags']}
            for r in audit_rows if any(f.startswith('EXIT_EARLY') or f.startswith('EXIT_TOO_LATE') for f in r.get('exit_flags', []))
        ], key=lambda x: (-num(x.get('future_up_r_40b')), -num(x.get('mfe_r'))))[:50],
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    fields = ['symbol','entry_year','entry_date','exit_date','exit_reason','pnl_pct','entry_price','sl','tp2','tp3','tp2_rr','tp3_rr','market_state','pd_zone','poi_type','event_type','entry_pos_in_zone','entry_timing_delta_reclaim','entry_better_lower_r_10b','future_up_r_40b','future_tp3_hit_after_exit','mfe_r','mae_r','hold_bars_realized','entry_flags','exit_flags']
    with OUT_CSV.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in audit_rows:
            row = {k: r.get(k) for k in fields}
            row['entry_flags'] = '|'.join(r.get('entry_flags', []))
            row['exit_flags'] = '|'.join(r.get('exit_flags', []))
            w.writerow(row)
    print(json.dumps({k: report[k] for k in ['all_rows','production_rows','audited_rows','overall','validation','entry_flag_counts','exit_flag_counts','yearly_by_entry_year']}, ensure_ascii=False, indent=2))
    print(f'WROTE {OUT_JSON}')
    print(f'WROTE {OUT_CSV}')


if __name__ == '__main__':
    main()
