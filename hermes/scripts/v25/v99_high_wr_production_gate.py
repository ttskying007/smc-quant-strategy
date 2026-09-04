#!/usr/bin/env python3
"""V99: V98 signal/entry preserved + bar-by-bar profit protection + semantic field repair + weak RECOVERY downgrade."""
from __future__ import annotations

import json
from pathlib import Path
from collections import Counter
from typing import Any, Dict, List

from v81_full_market_scan import KLINE_DIR, load_json
from v91_shadow_zone_entry_scanner import bar_date, num

SRC_DIR = Path('/root/.hermes/smc_opt_v98_reachable_5r_probability_gate')
OUT_DIR = Path('/root/.hermes/smc_opt_v99_high_wr_gate')
OUT_DIR.mkdir(parents=True, exist_ok=True)

TRADES_IN = SRC_DIR / 'v98_structural_trades.json'
PICKS_IN = SRC_DIR / 'v98_active_picks.json'
ENGINE = 'V99_PROFIT_PROTECT_HIGH_WR_GATE'
MAX_HOLD = 80


def fnum(x: Any, default: float = 0.0) -> float:
    try:
        if x in (None, ''):
            return default
        return float(x)
    except Exception:
        return default


def kline_path(symbol: str) -> Path:
    return KLINE_DIR / f"{symbol.replace('.', '_')}_daily_750.json"


def is_a_v98(r: Dict[str, Any]) -> bool:
    return r.get('production_grade_v98') == 'A_PRODUCTION' or r.get('production_grade') == 'A_PRODUCTION'


def weak_recovery(r: Dict[str, Any]) -> bool:
    market = r.get('market_state') or ''
    sub = r.get('v90_recovery_substate') or ''
    pd = r.get('pd_zone') or ''
    vol = fnum(r.get('volatility_pct'))
    risk = fnum(r.get('risk_pct'))
    event = r.get('event_type') or ''
    if market == 'RECOVERY' and pd != 'DEEP_DISCOUNT':
        return True
    if market == 'RECOVERY' and (vol > 0.8 or risk > 1.0) and event != 'SSL_SWEEP_CHOCH_REVERSAL':
        return True
    if sub.startswith('WEAK') or sub in ('FAILED_RECOVERY', 'NO_RECLAIM'):
        return True
    return False


def v99_tier(r: Dict[str, Any]) -> str:
    if not is_a_v98(r):
        return 'REJECT_NOT_V98_A'
    market = r.get('market_state')
    event = r.get('event_type')
    pd = r.get('pd_zone')
    tp2 = fnum(r.get('tp2_rr'))
    tp3 = fnum(r.get('tp3_rr'))
    vol = fnum(r.get('volatility_pct'))
    risk = fnum(r.get('risk_pct'))
    if weak_recovery(r):
        return 'RECOVERY_WEAK_DOWNGRADED'
    if market == 'MIXED' and event == 'SSL_SWEEP_CHOCH_REVERSAL' and tp2 <= 5.2 and vol <= 0.8 and risk <= 1.0:
        return 'A_HIGH_WR_PRODUCTION'
    if market == 'MIXED' and pd == 'DISCOUNT' and tp2 <= 5.2 and vol <= 0.8 and risk <= 1.0:
        return 'B_HIGH_WR_OBSERVE'
    if pd == 'DEEP_DISCOUNT' and tp2 <= 5.5 and tp3 <= 14:
        return 'C_ROBUST_OBSERVE'
    return 'WATCH_ONLY_LOW_WR'


def public_grade(tier: str) -> str:
    if tier == 'A_HIGH_WR_PRODUCTION':
        return 'A_PRODUCTION'
    if tier == 'B_HIGH_WR_OBSERVE':
        return 'B_LIGHT_OR_OBSERVE'
    if tier == 'C_ROBUST_OBSERVE':
        return 'C_WATCH_ONLY'
    if tier == 'RECOVERY_WEAK_DOWNGRADED':
        return 'D_RECOVERY_WEAK_WATCH_ONLY'
    return 'D_REJECT_OR_WATCH'


def apply_frontend_contract(x: Dict[str, Any]) -> Dict[str, Any]:
    x['entry_semantic_v98'] = x.get('entry_semantic_v98') or x.get('entry_semantic')
    x['entry_semantic'] = 'PRE_RECLAIM_ZONE_MID_LIMIT_ANTICIPATION'
    x['entry_layer'] = 'L1_ANTICIPATION'
    reclaim_idx = fnum(x.get('reclaim_idx'), -1)
    entry_idx = fnum(x.get('entry_idx'), -1)
    x['confirmation_status'] = 'RECLAIM_CONFIRMED_AFTER_ENTRY' if reclaim_idx > entry_idx >= 0 else 'RECLAIM_NOT_AFTER_ENTRY'

    x['pick_date'] = x.get('pick_date') or x.get('select_date') or x.get('pickDate') or x.get('选股日期') or x.get('entry_date')
    x['join_date'] = x.get('join_date') or x.get('entry_date') or x.get('joinDate') or x.get('加入日期')
    x['pickDate'] = x.get('pickDate') or x.get('pick_date')
    x['joinDate'] = x.get('joinDate') or x.get('join_date')
    x['selectDate'] = x.get('selectDate') or x.get('pick_date')
    x['entryDate'] = x.get('entryDate') or x.get('entry_date') or x.get('join_date')
    x['选股日期'] = x.get('选股日期') or x.get('pick_date')
    x['加入日期'] = x.get('加入日期') or x.get('join_date')

    x['zone_type'] = x.get('zone_type') or x.get('poi_type') or x.get('signal_type') or 'DEMAND_OB'
    zl, zh = fnum(x.get('zone_low')), fnum(x.get('zone_high'))
    if (not x.get('zone')) and zl and zh:
        x['zone'] = f'{zl:.4f}~{zh:.4f}'
    if not x.get('cost_line'):
        x['cost_line'] = x.get('smart_money_cost') or round((zl + zh) / 2, 4) if zl and zh else x.get('entry_price')
    if not x.get('smart_money_cost'):
        x['smart_money_cost'] = x.get('cost_line') or x.get('entry_price')
    if x.get('volatility_pct') in (None, ''):
        x['volatility_pct'] = x.get('volatility') if x.get('volatility') not in (None, '') else fnum(x.get('risk_pct'))
    if x.get('volatility') in (None, ''):
        x['volatility'] = x.get('volatility_pct')
    return x


def simulate_profit_protect(ks: List[Dict[str, Any]], row: Dict[str, Any]) -> Dict[str, Any]:
    entry_idx = int(fnum(row.get('entry_idx'), -1))
    ep = fnum(row.get('entry_price'))
    sl0 = fnum(row.get('sl'))
    tp1 = fnum(row.get('tp1'))
    tp2 = fnum(row.get('tp2'))
    tp3 = fnum(row.get('tp3'))
    risk = ep - sl0
    if entry_idx < 0 or ep <= 0 or risk <= 0 or entry_idx >= len(ks) - 1:
        return row

    active_sl = sl0
    active_sl_mode = 'STRUCTURAL_SL'
    hit1 = False
    exit_idx = min(len(ks) - 1, entry_idx + MAX_HOLD)
    exit_price = ep
    reason = 'TIME_STOP'
    max_h = ep
    min_l = ep
    trail_events: List[Dict[str, Any]] = []

    for i in range(entry_idx + 1, min(len(ks), entry_idx + MAX_HOLD + 1)):
        h = fnum(ks[i].get('h'))
        l = fnum(ks[i].get('l'))
        c = fnum(ks[i].get('c'))
        max_h = max(max_h, h)
        min_l = min(min_l, l)
        mfe_r_live = (max_h - ep) / risk

        if mfe_r_live >= 5 and active_sl < ep + 2 * risk:
            active_sl = ep + 2 * risk
            active_sl_mode = 'V99_PROTECT_MFE5_LOCK_2R'
            trail_events.append({'idx': i, 'date': bar_date(ks[i]), 'mfe_r': round(mfe_r_live, 4), 'active_sl': round(active_sl, 4), 'mode': active_sl_mode})
        elif mfe_r_live >= 2 and active_sl < ep + 0.25 * risk:
            active_sl = ep + 0.25 * risk
            active_sl_mode = 'V99_PROTECT_MFE2_LOCK_0_25R'
            trail_events.append({'idx': i, 'date': bar_date(ks[i]), 'mfe_r': round(mfe_r_live, 4), 'active_sl': round(active_sl, 4), 'mode': active_sl_mode})

        if l <= active_sl:
            exit_idx = i
            exit_price = active_sl
            reason = 'V99_PROFIT_PROTECT_STOP' if active_sl > sl0 else 'SL_HIT'
            break
        if tp1 and h >= tp1:
            hit1 = True
        if tp2 and h >= tp2:
            exit_idx = i
            exit_price = tp2
            reason = 'TP2_MAIN_HIT'
            break
        if tp3 and h >= tp3:
            exit_idx = i
            exit_price = tp3
            reason = 'TP3_RUNNER_HIT'
            break
        exit_price = c

    pnl = (exit_price / ep - 1) * 100 if ep else 0
    out = dict(row)
    out.update({
        'engine': ENGINE,
        'contract_source': 'V99_FROM_V98_SIGNAL_ENTRY_PROFIT_PROTECT',
        'v99_profit_protect': True,
        'v99_profit_protect_rule': 'BAR_BY_BAR_MFE>=2R_LOCK_0.25R__MFE>=5R_LOCK_2R',
        'active_sl': round(active_sl, 4),
        'active_sl_mode': active_sl_mode,
        'exit_idx': exit_idx,
        'exit_date': bar_date(ks[exit_idx]),
        'exit_price': round(exit_price, 4),
        'exit_reason_v98': row.get('exit_reason'),
        'pnl_pct_v98': row.get('pnl_pct'),
        'exit_reason': reason,
        'pnl_pct': round(pnl, 4),
        'hit_tp1': hit1,
        'hit_tp2': reason in ('TP2_MAIN_HIT', 'TP3_RUNNER_HIT'),
        'mfe_r': round((max_h - ep) / risk, 4),
        'mae_r': round((ep - min_l) / risk, 4),
        'hold_bars_realized': exit_idx - entry_idx,
        'v99_trail_events': trail_events[:10],
        'v99_pnl_delta': round(pnl - fnum(row.get('pnl_pct')), 4),
    })
    return out


def normalize_row(r: Dict[str, Any], ks: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    base = dict(r)
    base['production_grade_v98'] = base.get('production_grade_v98') or base.get('production_grade')
    if ks:
        base = simulate_profit_protect(ks, base)
    tier = v99_tier(base)
    base['v99_tier'] = tier
    base['v99_gate_reason'] = {
        'A_HIGH_WR_PRODUCTION': 'MIXED+SSL_SWEEP+TP2<=5.2+VOL<=0.8+RISK<=1.0',
        'B_HIGH_WR_OBSERVE': 'MIXED+DISCOUNT+TP2<=5.2+VOL<=0.8+RISK<=1.0',
        'C_ROBUST_OBSERVE': 'DEEP_DISCOUNT+TP2<=5.5+TP3<=14',
        'RECOVERY_WEAK_DOWNGRADED': 'RECOVERY weak environment downgraded from tradable pool',
    }.get(tier, tier)
    base['production_grade'] = public_grade(tier)
    base['setup_status'] = tier
    base['is_active_pick'] = tier == 'A_HIGH_WR_PRODUCTION'
    base['pick_scope'] = 'ACTIVE_CANDIDATE' if tier == 'A_HIGH_WR_PRODUCTION' else ('WATCH_ONLY' if tier in ('B_HIGH_WR_OBSERVE', 'C_ROBUST_OBSERVE') else 'REJECTED_OR_DOWNGRADED')
    base['state'] = base['pick_scope']
    return apply_frontend_contract(base)


def stats(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {'n': 0}
    n = len(rows)
    wins = [r for r in rows if fnum(r.get('pnl_pct')) > 0]
    sl = [r for r in rows if r.get('exit_reason') == 'SL_HIT']
    protect = [r for r in rows if r.get('exit_reason') == 'V99_PROFIT_PROTECT_STOP']
    return {
        'n': n,
        'wr': round(len(wins) / n * 100, 2),
        'sl_rate': round(len(sl) / n * 100, 2),
        'protect_stop_rate': round(len(protect) / n * 100, 2),
        'avg_pnl': round(sum(fnum(r.get('pnl_pct')) for r in rows) / n, 4),
        'cum_pnl': round(sum(fnum(r.get('pnl_pct')) for r in rows), 4),
        'avg_delta_vs_v98': round(sum(fnum(r.get('v99_pnl_delta')) for r in rows) / n, 4),
        'years': yearly(rows),
    }


def yearly(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    out = {}
    for y in sorted({str(r.get('entry_date') or '')[:4] for r in rows if r.get('entry_date')}):
        rs = [r for r in rows if str(r.get('entry_date') or '')[:4] == y]
        if rs:
            n = len(rs)
            out[y] = {
                'n': n,
                'wr': round(sum(1 for r in rs if fnum(r.get('pnl_pct')) > 0) / n * 100, 2),
                'sl_rate': round(sum(1 for r in rs if r.get('exit_reason') == 'SL_HIT') / n * 100, 2),
                'avg_pnl': round(sum(fnum(r.get('pnl_pct')) for r in rs) / n, 4),
            }
    return out


def field_missing(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    keys = ['pick_date', 'join_date', '选股日期', '加入日期', 'zone', 'zone_type', 'cost_line', 'smart_money_cost', 'volatility_pct', 'volatility']
    return {k: sum(1 for r in rows if r.get(k) in (None, '', 0)) for k in keys}


def load_ks_cache(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    cache = {}
    for sym in sorted({r.get('symbol') for r in rows if r.get('symbol')}):
        p = kline_path(sym)
        if p.exists():
            cache[sym] = load_json(p)
    return cache


def main() -> None:
    raw_trades = json.loads(TRADES_IN.read_text())
    ks_cache = load_ks_cache(raw_trades)
    trades = [normalize_row(r, ks_cache.get(r.get('symbol'))) for r in raw_trades]

    raw_picks = json.loads(PICKS_IN.read_text()) if PICKS_IN.exists() else []
    picks = [normalize_row(r, ks_cache.get(r.get('symbol'))) for r in raw_picks]
    active_picks = [p for p in picks if p['v99_tier'] in ('A_HIGH_WR_PRODUCTION', 'B_HIGH_WR_OBSERVE', 'C_ROBUST_OBSERVE')]

    v98_report = json.loads((SRC_DIR / 'v98_report.json').read_text()) if (SRC_DIR / 'v98_report.json').exists() else {}
    tradable = [r for r in trades if r.get('v99_tier') in ('A_HIGH_WR_PRODUCTION', 'B_HIGH_WR_OBSERVE', 'C_ROBUST_OBSERVE')]
    t1_violations = sum(1 for r in trades if str(r.get('entry_date')) == str(r.get('exit_date')))
    report = {
        'engine': ENGINE,
        'latest_market_date': v98_report.get('latest_market_date') or v98_report.get('latest_date') or max([str(p.get('pick_date') or p.get('entry_date') or '')[:8] for p in active_picks], default=''),
        'latest_date': v98_report.get('latest_market_date') or v98_report.get('latest_date') or max([str(p.get('pick_date') or p.get('entry_date') or '')[:8] for p in active_picks], default=''),
        'source': str(TRADES_IN),
        'rules': {
            'signal_entry': 'UNCHANGED_FROM_V98',
            'profit_protect': 'bar-by-bar; after live MFE>=2R lock +0.25R, after live MFE>=5R lock +2R; no final-MFE lookahead',
            'entry_semantic': 'PRE_RECLAIM_ZONE_MID_LIMIT_ANTICIPATION / L1_ANTICIPATION',
            'recovery_downgrade': 'RECOVERY non-DEEP_DISCOUNT or weak/high-vol/high-risk non-SSL reversal downgraded',
            'A_HIGH_WR_PRODUCTION': 'V98 A + market_state=MIXED + event=SSL_SWEEP_CHOCH_REVERSAL + tp2_rr<=5.2 + volatility_pct<=0.8 + risk_pct<=1.0',
            'B_HIGH_WR_OBSERVE': 'V98 A + market_state=MIXED + pd_zone=DISCOUNT + tp2_rr<=5.2 + volatility_pct<=0.8 + risk_pct<=1.0',
            'C_ROBUST_OBSERVE': 'V98 A + pd_zone=DEEP_DISCOUNT + tp2_rr<=5.5 + tp3_rr<=14 + not weak RECOVERY',
        },
        'all_tiers': {tier: stats([r for r in trades if r.get('v99_tier') == tier]) for tier in sorted({r.get('v99_tier') for r in trades})},
        'tradable_ABC': stats(tradable),
        'tradable_A_only': stats([r for r in trades if r.get('v99_tier') == 'A_HIGH_WR_PRODUCTION']),
        'active_pick_counts': dict(Counter(p.get('v99_tier') for p in active_picks)),
        'active_pick_total': len(active_picks),
        'exit_counts_tradable': dict(Counter(r.get('exit_reason') for r in tradable)),
        't1_violations': t1_violations,
        'field_missing_active': field_missing(active_picks),
        'field_contract': ['pick_date', 'join_date', '选股日期', '加入日期', 'zone', 'zone_type', 'cost_line', 'smart_money_cost', 'volatility_pct', 'volatility'],
    }
    (OUT_DIR / 'v99_trades.json').write_text(json.dumps(trades, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v99_active_picks.json').write_text(json.dumps(active_picks, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v99_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
