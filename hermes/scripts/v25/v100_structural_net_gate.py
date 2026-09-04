#!/usr/bin/env python3
"""V100: V98 signal/entry unchanged + SMC structural TP2/TP3 contract + net>=0.8% success gate.

Key contract:
- Filter by structural RR/quality BEFORE a row enters the active selection pool.
- Backtest/report success uses net_pnl_pct >= NET_SUCCESS_PCT, not tiny profit > 0.
- Production pool is A only; B/C/weak environments are observation only.
"""
from __future__ import annotations

import json
from pathlib import Path
from collections import Counter
from typing import Any, Dict, List

SRC_DIR = Path('/root/.hermes/smc_opt_v98_reachable_5r_probability_gate')
OUT_DIR = Path('/root/.hermes/smc_opt_v100_structural_net_gate')
OUT_DIR.mkdir(parents=True, exist_ok=True)

TRADES_IN = SRC_DIR / 'v98_structural_trades.json'
PICKS_IN = SRC_DIR / 'v98_active_picks.json'
ENGINE = 'V100_STRUCTURAL_NET_5R_GATE'
NET_SUCCESS_PCT = 0.8
FEE_PCT = 0.12


def fnum(x: Any, default: float = 0.0) -> float:
    try:
        if x in (None, ''):
            return default
        return float(x)
    except Exception:
        return default


def is_a_v98(r: Dict[str, Any]) -> bool:
    return r.get('production_grade_v98') == 'A_PRODUCTION' or r.get('production_grade') == 'A_PRODUCTION'


def weak_environment(r: Dict[str, Any]) -> bool:
    market = r.get('market_state') or ''
    sub = r.get('v90_recovery_substate') or ''
    pd = r.get('pd_zone') or ''
    vol = fnum(r.get('volatility_pct'))
    risk = fnum(r.get('risk_pct'))
    if market in ('BEAR_RISK', 'ACCUMULATION'):
        return True
    if market == 'RECOVERY' and pd != 'DEEP_DISCOUNT':
        return True
    if market == 'RECOVERY' and (vol > 0.8 or risk > 1.0):
        return True
    if sub.startswith('WEAK') or sub in ('FAILED_RECOVERY', 'NO_RECLAIM'):
        return True
    return False


def has_structure_contract(r: Dict[str, Any]) -> bool:
    return fnum(r.get('risk_pct')) > 0 and fnum(r.get('tp2_rr')) >= 5.0 and fnum(r.get('tp3_rr')) >= 8.0


def expected_net_at_tp2(r: Dict[str, Any]) -> float:
    ep = fnum(r.get('entry_price'))
    tp2 = fnum(r.get('tp2'))
    return (tp2 / ep - 1) * 100 - FEE_PCT if ep and tp2 else 0.0


def expected_net_at_tp3(r: Dict[str, Any]) -> float:
    ep = fnum(r.get('entry_price'))
    tp3 = fnum(r.get('tp3'))
    return (tp3 / ep - 1) * 100 - FEE_PCT if ep and tp3 else 0.0


def v100_tier(r: Dict[str, Any]) -> str:
    if not is_a_v98(r):
        return 'REJECT_NOT_V98_A'
    if not has_structure_contract(r):
        return 'REJECT_NO_5R_8R_STRUCTURE_CONTRACT'
    if expected_net_at_tp2(r) < NET_SUCCESS_PCT:
        return 'REJECT_TP2_NET_LT_0_8'
    if weak_environment(r):
        return 'WEAK_ENV_WATCH_ONLY'

    market = r.get('market_state')
    event = r.get('event_type')
    pd = r.get('pd_zone')
    tp2 = fnum(r.get('tp2_rr'))
    tp3 = fnum(r.get('tp3_rr'))
    vol = fnum(r.get('volatility_pct'))
    risk = fnum(r.get('risk_pct'))

    if market == 'MIXED' and event == 'SSL_SWEEP_CHOCH_REVERSAL' and tp2 <= 5.2 and vol <= 0.8 and risk <= 1.0:
        return 'A_PRODUCTION_CORE'
    if market == 'MIXED' and pd == 'DISCOUNT' and tp2 <= 5.2 and vol <= 0.8 and risk <= 1.0:
        return 'B_OBSERVE_HIGH_WR'
    if pd == 'DEEP_DISCOUNT' and tp2 <= 5.5 and tp3 <= 14:
        return 'C_ROBUST_OBSERVE_ONLY'
    return 'WATCH_ONLY_LOW_WR'


def public_grade(tier: str) -> str:
    if tier == 'A_PRODUCTION_CORE':
        return 'A_PRODUCTION'
    if tier == 'B_OBSERVE_HIGH_WR':
        return 'B_OBSERVE'
    if tier == 'C_ROBUST_OBSERVE_ONLY':
        return 'C_WATCH_ONLY'
    if tier == 'WEAK_ENV_WATCH_ONLY':
        return 'D_WEAK_ENV_WATCH_ONLY'
    return 'D_REJECT_OR_WATCH'


def net_pnl(r: Dict[str, Any]) -> float:
    return fnum(r.get('pnl_pct')) - FEE_PCT


def apply_frontend_contract(x: Dict[str, Any]) -> Dict[str, Any]:
    x['engine'] = ENGINE
    x['entry_semantic_v98'] = x.get('entry_semantic_v98') or x.get('entry_semantic')
    x['entry_semantic'] = 'PRE_RECLAIM_ZONE_MID_LIMIT_ANTICIPATION'
    x['entry_layer'] = 'L1_ANTICIPATION'
    x['pick_date'] = x.get('pick_date') or x.get('select_date') or x.get('pickDate') or x.get('conf_date') or x.get('entry_date') or x.get('signal_date')
    x['join_date'] = x.get('join_date') or x.get('joined_date') or x.get('joinDate') or x.get('entry_date') or x.get('pick_date')
    x['pickDate'] = x.get('pickDate') or x.get('pick_date')
    x['joinDate'] = x.get('joinDate') or x.get('join_date')
    x['selectDate'] = x.get('selectDate') or x.get('pick_date')
    x['entryDate'] = x.get('entryDate') or x.get('entry_date') or x.get('join_date')
    x['选股日期'] = x.get('选股日期') or x.get('pick_date')
    x['加入日期'] = x.get('加入日期') or x.get('join_date')

    zone = x.get('zone') if isinstance(x.get('zone'), dict) else {}
    x['zone_type'] = x.get('zone_type') or x.get('poi_type') or x.get('signal_type') or zone.get('type') or 'DEMAND_ZONE'
    x['zoneType'] = x.get('zoneType') or x.get('zone_type')
    zl = fnum(x.get('zone_low') or x.get('execution_zone_low') or x.get('raw_zone_low') or x.get('dz_low') or zone.get('low'))
    zh = fnum(x.get('zone_high') or x.get('execution_zone_high') or x.get('raw_zone_high') or x.get('dz_high') or zone.get('high'))
    if zl:
        x['zone_low'] = x.get('zone_low') or zl
        x['zoneLow'] = x.get('zoneLow') or zl
    if zh:
        x['zone_high'] = x.get('zone_high') or zh
        x['zoneHigh'] = x.get('zoneHigh') or zh
    if not x.get('zone') and zl and zh:
        x['zone'] = f'{zl:.4f}~{zh:.4f}'
    if not x.get('cost_line'):
        x['cost_line'] = x.get('smart_money_cost') or (round((zl + zh) / 2, 4) if zl and zh else x.get('entry_price'))
    x['smart_money_cost'] = x.get('smart_money_cost') or x.get('cost_line') or x.get('entry_price')
    x['costLine'] = x.get('costLine') or x.get('cost_line')
    if x.get('volatility_pct') in (None, ''):
        x['volatility_pct'] = x.get('v25_atr_pct') or x.get('atr_pct') or x.get('risk_pct')
    x['volatility'] = x.get('volatility') if x.get('volatility') not in (None, '') else x.get('volatility_pct')
    x['volatilityPct'] = x.get('volatilityPct') or x.get('volatility_pct')
    x['v25_vol_class'] = x.get('v25_vol_class') or x.get('vol_class') or f"RISK {fnum(x.get('risk_pct')):.2f}%"
    x['volClass'] = x.get('volClass') or x.get('v25_vol_class')
    return x


def normalize_row(r: Dict[str, Any]) -> Dict[str, Any]:
    base = dict(r)
    base['production_grade_v98'] = base.get('production_grade_v98') or base.get('production_grade')
    base['fee_pct'] = FEE_PCT
    base['net_pnl_pct'] = round(net_pnl(base), 4)
    base['net_success'] = base['net_pnl_pct'] >= NET_SUCCESS_PCT
    base['gross_success'] = fnum(base.get('pnl_pct')) > 0
    base['expected_tp2_net_pct'] = round(expected_net_at_tp2(base), 4)
    base['expected_tp3_net_pct'] = round(expected_net_at_tp3(base), 4)
    base['tp2_rr_gate'] = fnum(base.get('tp2_rr')) >= 5.0
    base['tp3_rr_gate'] = fnum(base.get('tp3_rr')) >= 8.0
    tier = v100_tier(base)
    base['v100_tier'] = tier
    base['v100_gate_reason'] = {
        'A_PRODUCTION_CORE': 'pre-selection structural gate: V98_A + TP2_R>=5 + TP3_R>=8 + TP2 net>=0.8% + MIXED SSL_SWEEP + low vol/risk',
        'B_OBSERVE_HIGH_WR': 'observe only: high WR but not production core',
        'C_ROBUST_OBSERVE_ONLY': 'observe only: robust sample but lower net WR than A/B',
        'WEAK_ENV_WATCH_ONLY': 'BEAR_RISK/ACCUMULATION/weak RECOVERY downgraded before active selection',
        'REJECT_TP2_NET_LT_0_8': 'pre-selection rejection: structural TP2 net profit below 0.8%',
    }.get(tier, tier)
    base['production_grade'] = public_grade(tier)
    base['setup_status'] = tier
    base['is_active_pick'] = tier == 'A_PRODUCTION_CORE'
    base['pick_scope'] = 'ACTIVE_CANDIDATE' if tier == 'A_PRODUCTION_CORE' else ('WATCH_ONLY' if tier in ('B_OBSERVE_HIGH_WR', 'C_ROBUST_OBSERVE_ONLY', 'WEAK_ENV_WATCH_ONLY') else 'REJECTED')
    base['state'] = base['pick_scope']
    return apply_frontend_contract(base)


def yearly(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    out = {}
    for y in sorted({str(r.get('entry_date') or '')[:4] for r in rows if r.get('entry_date')}):
        rs = [r for r in rows if str(r.get('entry_date') or '')[:4] == y]
        if rs:
            out[y] = stats(rs, include_years=False)
    return out


def stats(rows: List[Dict[str, Any]], include_years: bool = True) -> Dict[str, Any]:
    if not rows:
        return {'n': 0}
    n = len(rows)
    net_wins = [r for r in rows if fnum(r.get('net_pnl_pct')) >= NET_SUCCESS_PCT]
    gross_wins = [r for r in rows if fnum(r.get('pnl_pct')) > 0]
    small_wins = [r for r in rows if 0 < fnum(r.get('net_pnl_pct')) < NET_SUCCESS_PCT]
    out = {
        'n': n,
        'net_wr_ge_0_8': round(len(net_wins) / n * 100, 2),
        'gross_wr_gt_0': round(len(gross_wins) / n * 100, 2),
        'small_profit_pollution_n': len(small_wins),
        'small_profit_pollution_rate': round(len(small_wins) / n * 100, 2),
        'sl_rate': round(sum(1 for r in rows if r.get('exit_reason') == 'SL_HIT') / n * 100, 2),
        'avg_net_pnl': round(sum(fnum(r.get('net_pnl_pct')) for r in rows) / n, 4),
        'avg_gross_pnl': round(sum(fnum(r.get('pnl_pct')) for r in rows) / n, 4),
        'cum_net_pnl': round(sum(fnum(r.get('net_pnl_pct')) for r in rows), 4),
    }
    if include_years:
        out['years'] = yearly(rows)
    return out


def field_missing(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    keys = ['pick_date', 'join_date', '选股日期', '加入日期', 'zone', 'zone_type', 'cost_line', 'smart_money_cost', 'volatility_pct', 'volatility', 'costLine', 'volClass']
    return {k: sum(1 for r in rows if r.get(k) in (None, '', 0)) for k in keys}


def main() -> None:
    raw_trades = json.loads(TRADES_IN.read_text())
    trades = [normalize_row(r) for r in raw_trades]
    raw_picks = json.loads(PICKS_IN.read_text()) if PICKS_IN.exists() else []
    picks = [normalize_row(r) for r in raw_picks]

    active_picks = [p for p in picks if p['v100_tier'] == 'A_PRODUCTION_CORE']
    watch_picks = [p for p in picks if p['v100_tier'] in ('B_OBSERVE_HIGH_WR', 'C_ROBUST_OBSERVE_ONLY', 'WEAK_ENV_WATCH_ONLY')]
    v98_report = json.loads((SRC_DIR / 'v98_report.json').read_text()) if (SRC_DIR / 'v98_report.json').exists() else {}
    report = {
        'engine': ENGINE,
        'version': 'V100',
        'latest_market_date': v98_report.get('latest_market_date') or v98_report.get('latest_date') or max([str(p.get('pick_date') or p.get('entry_date') or '')[:8] for p in picks], default=''),
        'latest_date': v98_report.get('latest_market_date') or v98_report.get('latest_date') or max([str(p.get('pick_date') or p.get('entry_date') or '')[:8] for p in picks], default=''),
        'source': str(TRADES_IN),
        'selection_contract': 'pre-selection gate, not post-backtest deletion: V98_A + structural TP2_R>=5 + TP3_R>=8 + expected TP2 net>=0.8%; A only enters active production picks',
        'net_success_contract': {'fee_pct': FEE_PCT, 'success_threshold_net_pct': NET_SUCCESS_PCT, 'win_definition': 'net_pnl_pct >= 0.8'},
        'rules': {
            'signal_entry': 'UNCHANGED_FROM_V98',
            'A_PRODUCTION_CORE': 'production only: MIXED + SSL_SWEEP_CHOCH_REVERSAL + TP2_R<=5.2 + vol<=0.8 + risk<=1.0 + structural/net gates',
            'B_OBSERVE_HIGH_WR': 'observe only, not production',
            'C_ROBUST_OBSERVE_ONLY': 'observe only, not production; sample is larger but net WR lower than A/B',
            'weak_environment': 'BEAR_RISK/ACCUMULATION/weak RECOVERY downgraded before active selection',
            'runner': 'TP2 is main structural target; TP3_R>=8 remains required as runner capacity, not tiny lock-win success',
        },
        'all_tiers': {tier: stats([r for r in trades if r.get('v100_tier') == tier]) for tier in sorted({r.get('v100_tier') for r in trades})},
        'production_A_only': stats([r for r in trades if r.get('v100_tier') == 'A_PRODUCTION_CORE']),
        'observe_BC': stats([r for r in trades if r.get('v100_tier') in ('B_OBSERVE_HIGH_WR', 'C_ROBUST_OBSERVE_ONLY')]),
        'active_pick_counts': dict(Counter(p.get('v100_tier') for p in active_picks)),
        'watch_pick_counts': dict(Counter(p.get('v100_tier') for p in watch_picks)),
        'active_pick_total': len(active_picks),
        'watch_pick_total': len(watch_picks),
        't1_violations': sum(1 for r in trades if str(r.get('entry_date')) == str(r.get('exit_date'))),
        'field_missing_active': field_missing(active_picks),
        'field_missing_watch': field_missing(watch_picks),
        'exit_counts_production': dict(Counter(r.get('exit_reason') for r in trades if r.get('v100_tier') == 'A_PRODUCTION_CORE')),
    }
    (OUT_DIR / 'v100_trades.json').write_text(json.dumps(trades, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v100_active_picks.json').write_text(json.dumps(active_picks, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v100_watch_picks.json').write_text(json.dumps(watch_picks, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v100_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
