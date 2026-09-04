#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

SRC = Path('/root/.hermes/smc_opt_v88_production_contract/v88_trades.json')
KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v95_exit_contract_autopsy')
OUT.mkdir(parents=True, exist_ok=True)

ENGINE = 'V95_EXIT_CONTRACT_AUTOPSY'
MAX_HOLD = 40
POST_WINDOWS = [3, 5, 10, 20]


def num(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == '':
            return default
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def d(b: Dict[str, Any]) -> str:
    return ''.join(ch for ch in str(b.get('t') or b.get('date') or '') if ch.isdigit())[:8]


def date_key(v: Any) -> str:
    return ''.join(ch for ch in str(v or '') if ch.isdigit())[:8]


def symkey(sym: str) -> str:
    return str(sym).replace('.', '_')


def kpath(sym: str) -> Path:
    return KLINE / f'{symkey(sym)}_daily_750.json'


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def bars_after(bars: List[Dict[str, Any]], date: str, n: int | None = None) -> List[Dict[str, Any]]:
    ds = date_key(date)
    out = [b for b in bars if d(b) > ds]
    return out if n is None else out[:n]


def bars_from_entry_t1(bars: List[Dict[str, Any]], entry_date: str, n: int = MAX_HOLD) -> List[Dict[str, Any]]:
    # A股T+1硬约束：退出模拟从买入日之后第一根日K开始。
    return bars_after(bars, entry_date, n)


def risk_price(row: Dict[str, Any]) -> float:
    return max(num(row.get('entry_price')) - num(row.get('sl')), 1e-9)


def risk_pct(row: Dict[str, Any]) -> float:
    ep = num(row.get('entry_price'))
    return risk_price(row) / ep * 100 if ep else 0.0


def post_exit_profile(row: Dict[str, Any], bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    exit_date = date_key(row.get('exit_date'))
    exit_price = num(row.get('exit_price')) or num(row.get('planned_exit_price')) or num(row.get('entry_price'))
    ep = num(row.get('entry_price'))
    r = risk_price(row)
    out: Dict[str, Any] = {}
    after_all = bars_after(bars, exit_date, max(POST_WINDOWS))
    for w in POST_WINDOWS:
        win = after_all[:w]
        if not win or exit_price <= 0:
            out[f'post_{w}d_max_high_ret_pct'] = None
            out[f'post_{w}d_min_low_ret_pct'] = None
            out[f'post_{w}d_close_ret_pct'] = None
            out[f'post_{w}d_max_high_r_from_entry'] = None
            out[f'post_{w}d_min_low_r_from_entry'] = None
            continue
        max_high = max(num(b.get('h')) for b in win)
        min_low = min(num(b.get('l')) for b in win)
        last_close = num(win[-1].get('c'))
        out[f'post_{w}d_max_high_ret_pct'] = round((max_high / exit_price - 1) * 100, 4)
        out[f'post_{w}d_min_low_ret_pct'] = round((min_low / exit_price - 1) * 100, 4)
        out[f'post_{w}d_close_ret_pct'] = round((last_close / exit_price - 1) * 100, 4)
        out[f'post_{w}d_max_high_r_from_entry'] = round((max_high - ep) / r, 4) if r > 0 else 0
        out[f'post_{w}d_min_low_r_from_entry'] = round((min_low - ep) / r, 4) if r > 0 else 0
    out['post_available_days'] = len(after_all)
    out['sold_early_20d_2r'] = bool((out.get('post_20d_max_high_r_from_entry') or -999) >= 2.0 and row.get('exit_reason') in {'RUNNER_TRAIL', 'TIME_STOP', 'SL_HIT'})
    out['sold_early_20d_3r'] = bool((out.get('post_20d_max_high_r_from_entry') or -999) >= 3.0 and row.get('exit_reason') in {'RUNNER_TRAIL', 'TIME_STOP', 'SL_HIT'})
    out['post_exit_crash_20d_minus1r'] = bool((out.get('post_20d_min_low_r_from_entry') or 999) <= -1.0)
    return out


def classify_sl(row: Dict[str, Any], prof: Dict[str, Any]) -> str:
    if row.get('exit_reason') != 'SL_HIT':
        return 'NOT_SL'
    max20 = prof.get('post_20d_max_high_r_from_entry')
    min20 = prof.get('post_20d_min_low_r_from_entry')
    if max20 is None:
        return 'SL_UNKNOWN_NO_POST_DATA'
    # 止损后20日内重新打到2R+：不是信号一定错，优先归为洗盘/止损位置问题。
    if max20 >= 2.0:
        if min20 is not None and min20 <= -2.0:
            return 'EARLY_ENTRY_THEN_WASHOUT_REBOUND'
        return 'WASHOUT_SL_REBOUNDED_TO_2R'
    # 止损后继续跌到-1R以下且没有重回入场：保护性SL有效。
    if (min20 is not None and min20 <= -1.0) and max20 < 0:
        return 'PROTECTIVE_SL_CONTINUED_DOWN'
    if max20 >= 0:
        return 'BORDERLINE_SL_RECLAIMED_ENTRY_NOT_2R'
    return 'PROTECTIVE_SL_NO_RECLAIM'


def simulate_v95(row: Dict[str, Any], daily: List[Dict[str, Any]]) -> Dict[str, Any]:
    ep = num(row.get('entry_price'))
    sl = num(row.get('sl'))
    tp1, tp2, tp3 = num(row.get('tp1')), num(row.get('tp2')), num(row.get('tp3'))
    risk = ep - sl
    if ep <= 0 or risk <= 0:
        return {'v95_valid': False, 'v95_reject': 'BAD_ENTRY_OR_RISK'}
    bars = bars_from_entry_t1(daily, row.get('entry_date'), MAX_HOLD)
    if not bars:
        return {'v95_valid': False, 'v95_reject': 'NO_POST_ENTRY_BARS'}

    legs: List[Dict[str, Any]] = []
    remaining = 1.0
    pnl = 0.0
    reason = 'TIME_STOP'
    exit_price = ep
    exit_date = d(bars[-1])
    hit = set()
    mfe_r = -999.0
    mae_r = 999.0
    high_water = ep
    runner_active = False
    runner_trail = None
    weights = [('TP1_HIT', tp1, 0.35), ('TP2_HIT', tp2, 0.35), ('TP3_TOUCH_RUNNER_CONTINUES', tp3, 0.0)]

    for i, b in enumerate(bars):
        bd = d(b)
        hi, lo, cl = num(b.get('h')), num(b.get('l')), num(b.get('c'))
        high_water = max(high_water, hi)
        mfe_r = max(mfe_r, (hi - ep) / risk)
        mae_r = min(mae_r, (lo - ep) / risk)

        if lo <= sl and not legs:
            pnl = (sl / ep - 1) * 100
            exit_price = sl
            exit_date = bd
            reason = 'SL_HIT'
            remaining = 0
            break

        for name, tp, w in weights:
            if name not in hit and tp > 0 and hi >= tp and remaining > 0:
                hit.add(name)
                if w > 0:
                    take = min(w, remaining)
                    pnl += take * (tp / ep - 1) * 100
                    remaining -= take
                    legs.append({'reason': name, 'price': round(tp, 4), 'weight': round(take, 4), 'date': bd})
                if name in {'TP2_HIT', 'TP3_TOUCH_RUNNER_CONTINUES'}:
                    runner_active = True

        if runner_active and remaining > 0:
            # V95核心：不是放大TP/SL，而是重建runner trailing。
            # TP2后先给趋势空间；3R后才用2R宽度动态跟踪，最低锁1R。
            if high_water >= ep + 3.0 * risk:
                runner_trail = max(ep + 1.0 * risk, high_water - 2.0 * risk)
            elif high_water >= ep + 2.0 * risk:
                runner_trail = max(ep, ep + 0.5 * risk)
            if runner_trail is not None and lo <= runner_trail:
                pnl += remaining * (runner_trail / ep - 1) * 100
                legs.append({'reason': 'V95_RUNNER_TRAIL', 'price': round(runner_trail, 4), 'weight': round(remaining, 4), 'date': bd})
                exit_price = runner_trail
                exit_date = bd
                reason = 'V95_RUNNER_TRAIL'
                remaining = 0
                break

        exit_price = cl
        exit_date = bd

    if remaining > 0:
        # 接入V93 TIME_STOP高MFE捕获：TIME_STOP且MFE>=1.5R，至少捕获50%MFE，上限3R。
        if mfe_r >= 1.5:
            target_r = min(max(mfe_r * 0.5, 1.5), 3.0)
            target_price = ep + target_r * risk
            pnl += remaining * (target_price / ep - 1) * 100
            legs.append({'reason': 'V95_TIME_STOP_MFE_50PCT_CAP_3R', 'price': round(target_price, 4), 'weight': round(remaining, 4), 'date': exit_date, 'target_r': round(target_r, 4)})
            exit_price = target_price
            reason = 'V95_TIME_STOP_MFE_50PCT_CAP_3R'
        else:
            pnl += remaining * (exit_price / ep - 1) * 100
            legs.append({'reason': 'V95_TIME_STOP_CLOSE', 'price': round(exit_price, 4), 'weight': round(remaining, 4), 'date': exit_date})
            reason = 'V95_TIME_STOP_CLOSE'
        remaining = 0

    return {
        'v95_valid': True,
        'v95_exit_reason': reason,
        'v95_exit_price': round(exit_price, 4),
        'v95_exit_date': exit_date,
        'v95_pnl_pct': round(pnl, 4),
        'v95_exit_legs': legs,
        'v95_hold_bars': len([b for b in bars if d(b) <= exit_date]),
        'v95_mfe_r': round(mfe_r if mfe_r != -999 else 0, 4),
        'v95_mae_r': round(mae_r if mae_r != 999 else 0, 4),
        'v95_t1_violation': date_key(row.get('entry_date')) >= date_key(exit_date),
    }


def metrics(rows: List[Dict[str, Any]], pnl_key='pnl_pct', reason_key='exit_reason') -> Dict[str, Any]:
    if not rows:
        return {'n': 0, 'wr': 0, 'avg': 0, 'cum': 0, 'sl_rate': 0, 'time_rate': 0, 'runner_rate': 0}
    vals = [num(r.get(pnl_key)) for r in rows]
    n = len(rows)
    return {
        'n': n,
        'wr': round(sum(v > 0 for v in vals) / n * 100, 2),
        'avg': round(sum(vals) / n, 4),
        'cum': round(sum(vals), 2),
        'sl_rate': round(sum(r.get(reason_key) == 'SL_HIT' for r in rows) / n * 100, 2),
        'time_rate': round(sum('TIME_STOP' in str(r.get(reason_key)) for r in rows) / n * 100, 2),
        'runner_rate': round(sum('RUNNER' in str(r.get(reason_key)) for r in rows) / n * 100, 2),
    }


def bucket(rows: List[Dict[str, Any]], key, pnl_key='pnl_pct', reason_key='exit_reason') -> Dict[str, Dict[str, Any]]:
    g: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        g[str(key(r))].append(r)
    return {k: metrics(v, pnl_key, reason_key) for k, v in sorted(g.items())}


def summarize_post(rows: List[Dict[str, Any]], reason: str) -> Dict[str, Any]:
    rs = [r for r in rows if r.get('exit_reason') == reason]
    if not rs:
        return {'n': 0}
    out: Dict[str, Any] = {'n': len(rs)}
    for w in POST_WINDOWS:
        vals = [num(r.get(f'post_{w}d_max_high_ret_pct')) for r in rs if r.get(f'post_{w}d_max_high_ret_pct') is not None]
        down = [num(r.get(f'post_{w}d_min_low_ret_pct')) for r in rs if r.get(f'post_{w}d_min_low_ret_pct') is not None]
        if vals:
            out[f'post_{w}d_avg_max_high_ret_pct'] = round(sum(vals) / len(vals), 4)
            out[f'post_{w}d_big_up_5pct_rate'] = round(sum(v >= 5 for v in vals) / len(vals) * 100, 2)
            out[f'post_{w}d_big_up_10pct_rate'] = round(sum(v >= 10 for v in vals) / len(vals) * 100, 2)
        if down:
            out[f'post_{w}d_avg_min_low_ret_pct'] = round(sum(down) / len(down), 4)
            out[f'post_{w}d_big_down_5pct_rate'] = round(sum(v <= -5 for v in down) / len(down) * 100, 2)
    return out


def main() -> None:
    trades = load_json(SRC, [])
    kcache: Dict[str, List[Dict[str, Any]]] = {}
    rows: List[Dict[str, Any]] = []
    missing_kline = []
    for r in trades:
        sym = r.get('symbol')
        if sym not in kcache:
            p = kpath(sym)
            kcache[sym] = load_json(p, [])
            if not kcache[sym]:
                missing_kline.append(sym)
        daily = kcache.get(sym, [])
        nr = dict(r)
        prof = post_exit_profile(r, daily) if daily else {}
        nr.update(prof)
        nr['sl_class_v95'] = classify_sl(r, prof)
        nr.update(simulate_v95(r, daily) if daily else {'v95_valid': False, 'v95_reject': 'NO_KLINE'})
        nr['v95_delta_pnl_pct'] = round(num(nr.get('v95_pnl_pct')) - num(nr.get('pnl_pct')), 4) if nr.get('v95_valid') else None
        rows.append(nr)

    valid = [r for r in rows if r.get('v95_valid')]
    runner = [r for r in rows if r.get('exit_reason') == 'RUNNER_TRAIL']
    timestop = [r for r in rows if r.get('exit_reason') == 'TIME_STOP']
    slhit = [r for r in rows if r.get('exit_reason') == 'SL_HIT']
    report = {
        'engine': ENGINE,
        'source': str(SRC),
        'backtest_window': {
            'entry_date_min': min(date_key(r.get('entry_date')) for r in trades) if trades else '',
            'entry_date_max': max(date_key(r.get('entry_date')) for r in trades) if trades else '',
            'exit_date_min': min(date_key(r.get('exit_date')) for r in trades) if trades else '',
            'exit_date_max': max(date_key(r.get('exit_date')) for r in trades) if trades else '',
            'trade_count': len(trades),
            'post_exit_windows_trading_days': POST_WINDOWS,
            'max_hold_trading_days': MAX_HOLD,
            't1_rule': 'exit simulation starts from first daily bar after entry_date',
        },
        'baseline_v88': metrics(rows),
        'v95_exit_contract': metrics(valid, 'v95_pnl_pct', 'v95_exit_reason'),
        'delta': {
            'avg_pnl_delta': round(metrics(valid, 'v95_pnl_pct', 'v95_exit_reason')['avg'] - metrics(rows)['avg'], 4),
            'cum_delta': round(metrics(valid, 'v95_pnl_pct', 'v95_exit_reason')['cum'] - metrics(rows)['cum'], 2),
        },
        'baseline_by_exit_reason': bucket(rows, lambda r: r.get('exit_reason')),
        'v95_by_exit_reason': bucket(valid, lambda r: r.get('v95_exit_reason'), 'v95_pnl_pct', 'v95_exit_reason'),
        'by_year_baseline': bucket(rows, lambda r: date_key(r.get('entry_date'))[:4]),
        'by_year_v95': bucket(valid, lambda r: date_key(r.get('entry_date'))[:4], 'v95_pnl_pct', 'v95_exit_reason'),
        'post_exit_autopsy': {
            'RUNNER_TRAIL': summarize_post(rows, 'RUNNER_TRAIL'),
            'TIME_STOP': summarize_post(rows, 'TIME_STOP'),
            'SL_HIT': summarize_post(rows, 'SL_HIT'),
        },
        'time_stop_v93_capture': {
            'n': len(timestop),
            'high_mfe_ge_1_5r': sum(num(r.get('mfe_r')) >= 1.5 for r in timestop),
            'v95_time_capture_rows': sum(r.get('v95_exit_reason') == 'V95_TIME_STOP_MFE_50PCT_CAP_3R' for r in rows),
            'baseline': metrics(timestop),
            'v95': metrics([r for r in rows if r.get('exit_reason') == 'TIME_STOP' and r.get('v95_valid')], 'v95_pnl_pct', 'v95_exit_reason'),
        },
        'sl_hit_classification': dict(Counter(r.get('sl_class_v95') for r in slhit)),
        'sl_hit_by_class': bucket(slhit, lambda r: r.get('sl_class_v95')),
        'top_sold_early_runner_20d': sorted(
            [r for r in runner if r.get('post_20d_max_high_ret_pct') is not None],
            key=lambda r: num(r.get('post_20d_max_high_ret_pct')), reverse=True
        )[:30],
        'top_sl_rebound_20d': sorted(
            [r for r in slhit if r.get('post_20d_max_high_ret_pct') is not None],
            key=lambda r: num(r.get('post_20d_max_high_r_from_entry')), reverse=True
        )[:30],
        'field_audit': {
            'missing_kline_count': len(set(missing_kline)),
            'v95_invalid_count': len(rows) - len(valid),
            'v95_t1_violations': sum(bool(r.get('v95_t1_violation')) for r in rows),
            'post_exit_no_20d_count': sum(num(r.get('post_available_days')) < 20 for r in rows),
        },
    }

    (OUT / 'v95_exit_autopsy_rows.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    (OUT / 'v95_exit_contract_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    with (OUT / 'v95_exit_autopsy_rows.csv').open('w', newline='') as fp:
        fields = sorted({k for r in rows for k in r.keys() if k != 'v95_exit_legs'})
        w = csv.DictWriter(fp, fieldnames=fields, extrasaction='ignore')
        w.writeheader(); w.writerows(rows)
    print(json.dumps({
        'engine': ENGINE,
        'baseline_v88': report['baseline_v88'],
        'v95_exit_contract': report['v95_exit_contract'],
        'delta': report['delta'],
        'post_exit_autopsy': report['post_exit_autopsy'],
        'time_stop_v93_capture': report['time_stop_v93_capture'],
        'sl_hit_classification': report['sl_hit_classification'],
        'field_audit': report['field_audit'],
        'out': str(OUT),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
