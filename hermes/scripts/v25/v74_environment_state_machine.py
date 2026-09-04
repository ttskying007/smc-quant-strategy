#!/usr/bin/env python3
"""V74 SMC environment state machine.

This layer deliberately sits above single-stock POI detection.  It classifies
whether demand zones are allowed to work before accepting OB/OB-FVG/Breaker/OTE
entries.  It is non-leaking: only breadth values already known on the entry date
and confirmed stock structure labels are used.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

V73_DIR = Path('/root/.hermes/smc_opt_v73_structural_env')
OUT_DIR = Path('/root/.hermes/smc_opt_v74_env_state_machine')
OUT_DIR.mkdir(parents=True, exist_ok=True)

VALID_DEMAND_ZONES = {
    'OB_Bull', 'OB_SMART_MONEY', 'OB_FVG_OVERLAP', 'BREAKER_BULL', 'BREAKER_OB', 'OTE_OB', 'OTE_OB_FVG'
}
VALID_PD_ZONES = {'DISCOUNT', 'OTE_DISCOUNT', 'STRUCTURE_LOW_RISK'}
VALID_REACTIONS = {'RECLAIM_HIGH', 'TWO_BAR_REACTION', 'IDM_BOUNCE', 'PB_BOUNCE'}
DEMAND_VALID_MARKETS = {'ACCUMULATION', 'RECOVERY', 'BULL_CONTINUATION'}
RISK_MARKETS = {'DISTRIBUTION', 'BEAR_RISK'}


def f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x or 0)
    except Exception:
        return default


def classify_market_env(row: Dict[str, Any]) -> str:
    """Classify broad SMC environment into demand-valid/risk states.

    Priority is important: distribution/bear risk must override bullish breadth,
    because V73 showed 2023 looked broad-bullish while demand zones failed.
    """
    bull = f(row.get('bull_breadth', row.get('market_bull_breadth')))
    bear = f(row.get('bear_breadth', row.get('market_bear_breadth')))
    rng = f(row.get('range_breadth', row.get('market_range_breadth')))
    bull_slope = f(row.get('bull_slope20', row.get('market_bull_slope20')))
    bear_slope = f(row.get('bear_slope20', row.get('market_bear_slope20')))
    range_slope = f(row.get('range_slope20', row.get('market_range_slope20')))

    if bear >= 0.42 and bull <= 0.36:
        return 'BEAR_RISK'
    if bull >= 0.40 and bull_slope <= -0.035 and (bear_slope >= 0.025 or bear >= 0.38):
        return 'DISTRIBUTION'
    if bull >= 0.40 and rng >= 0.34 and range_slope > 0 and bull_slope >= 0.18 and bear_slope <= -0.18:
        return 'DISTRIBUTION'
    if bull >= 0.44 and bear <= 0.36 and bull_slope >= -0.025:
        return 'BULL_CONTINUATION'
    if bull >= 0.34 and bull_slope >= 0.035 and bear <= 0.42:
        return 'RECOVERY'
    if rng >= 0.34 and abs(bull_slope) <= 0.025 and bear <= 0.40:
        return 'ACCUMULATION'
    if bear >= 0.38 and (bear_slope > 0.02 or bull_slope < -0.03):
        return 'BEAR_RISK'
    if bull >= 0.38 and range_slope > 0.02 and bull_slope < 0:
        return 'DISTRIBUTION'
    return 'MIXED'


def is_valid_demand_zone(trade: Dict[str, Any]) -> bool:
    z = str(trade.get('zone_type') or trade.get('sm_zone_type') or trade.get('signal_type') or '')
    if z == 'FVG_Bull' or z.startswith('FVG'):
        return False
    if z in VALID_DEMAND_ZONES:
        return True
    return ('OB' in z or 'BREAKER' in z) and 'FVG' != z


def classify_setup_story(trade: Dict[str, Any]) -> str:
    env = str(trade.get('market_state_v74') or trade.get('market_env') or '')
    stock = str(trade.get('stock_trend_state') or '')
    event = str(trade.get('stock_last_event') or '')
    reaction = str(trade.get('reaction_type') or '')

    if reaction not in VALID_REACTIONS:
        return 'NO_RECLAIM_CONFIRMATION'
    if env in RISK_MARKETS:
        return 'ENVIRONMENT_INVALIDATES_DEMAND'
    if stock in ('UP_CONTINUATION', 'COMPRESSION_RANGE') and event == 'BULL_BOS':
        return 'UP_CONTINUATION_BOS_POI_RECLAIM'
    if env in ('RECOVERY', 'ACCUMULATION') and stock in ('BULL_TRANSITION', 'DOWN_CONTINUATION', 'COMPRESSION_RANGE', 'EXPANSION_RANGE') and event == 'BULL_CHOCH':
        return 'DOWN_REVERSAL_SSL_CHOCH_POI_RECLAIM'
    if stock == 'BULL_TRANSITION' and event in ('BULL_CHOCH', 'BULL_BOS'):
        return 'BULL_TRANSITION_POI_RECLAIM'
    return 'UNCLASSIFIED_CONTEXT'


def passes_v74_core_gate(trade: Dict[str, Any]) -> bool:
    env = str(trade.get('market_state_v74') or '')
    if env not in DEMAND_VALID_MARKETS:
        return False
    if not is_valid_demand_zone(trade):
        return False
    if str(trade.get('reaction_type') or '') not in VALID_REACTIONS:
        return False
    if str(trade.get('pd_zone') or '') not in VALID_PD_ZONES:
        return False
    risk = f(trade.get('risk_pct'))
    if not (2.0 <= risk <= 6.0):
        return False
    return classify_setup_story(trade) in {
        'UP_CONTINUATION_BOS_POI_RECLAIM',
        'DOWN_REVERSAL_SSL_CHOCH_POI_RECLAIM',
        'BULL_TRANSITION_POI_RECLAIM',
    }


def metrics(ts: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(ts)
    if not rows:
        return {'n': 0, 'wr': 0, 'sl_rate': 0, 'tp_rate': 0, 'avg_pnl': 0, 'cum': 0, 'avg_win': 0, 'avg_loss': 0, 'payoff': 0, 'avg_hold': 0}
    wins = [t for t in rows if f(t.get('pnl_pct')) > 0]
    losses = [t for t in rows if f(t.get('pnl_pct')) <= 0]
    sl = [t for t in rows if t.get('exit_reason') == 'SL_HIT']
    tp = [t for t in rows if t.get('exit_reason') == 'TP1_HIT']
    avg = sum(f(t.get('pnl_pct')) for t in rows) / len(rows)
    aw = sum(f(t.get('pnl_pct')) for t in wins) / len(wins) if wins else 0
    al = sum(f(t.get('pnl_pct')) for t in losses) / len(losses) if losses else 0
    return {
        'n': len(rows), 'wr': round(len(wins) / len(rows) * 100, 2),
        'sl_rate': round(len(sl) / len(rows) * 100, 2), 'tp_rate': round(len(tp) / len(rows) * 100, 2),
        'avg_pnl': round(avg, 4), 'cum': round(sum(f(t.get('pnl_pct')) for t in rows), 2),
        'avg_win': round(aw, 4), 'avg_loss': round(al, 4),
        'payoff': round(aw / abs(al), 3) if al else 0,
        'avg_hold': round(sum(f(t.get('hold_bars')) for t in rows) / len(rows), 2),
    }


def bucket(rows: Iterable[Dict[str, Any]], key) -> Dict[str, Any]:
    g: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for t in rows:
        g[str(key(t))].append(t)
    return {k: metrics(v) for k, v in sorted(g.items())}


def add_env_slopes(env_by_date: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    dates = sorted(env_by_date)
    out: Dict[str, Dict[str, Any]] = {}
    for idx, dt in enumerate(dates):
        row = dict(env_by_date[dt])
        prev = env_by_date[dates[idx - 20]] if idx >= 20 else {}
        for name in ('bear', 'range'):
            cur = f(row.get(f'{name}_breadth'))
            old = f(prev.get(f'{name}_breadth')) if prev else cur
            row[f'{name}_slope20'] = round(cur - old, 4)
        row['market_state_v74'] = classify_market_env(row)
        out[dt] = row
    return out


def annotate_trades(trades: List[Dict[str, Any]], env: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for t in trades:
        nt = dict(t)
        ed = str(nt.get('entry_date') or nt.get('pick_date') or '')[:8]
        er = env.get(ed, {})
        nt['market_state_v74'] = er.get('market_state_v74', classify_market_env(nt))
        nt['market_bear_slope20'] = er.get('bear_slope20', 0)
        nt['market_range_slope20'] = er.get('range_slope20', 0)
        nt['setup_story_v74'] = classify_setup_story(nt)
        nt['v74_core_gate'] = passes_v74_core_gate(nt)
        return_reason = []
        if nt['market_state_v74'] not in DEMAND_VALID_MARKETS:
            return_reason.append('BAD_ENV')
        if not is_valid_demand_zone(nt):
            return_reason.append('BAD_POI')
        if str(nt.get('reaction_type') or '') not in VALID_REACTIONS:
            return_reason.append('NO_RECLAIM')
        if str(nt.get('pd_zone') or '') not in VALID_PD_ZONES:
            return_reason.append('BAD_PD')
        if not (2.0 <= f(nt.get('risk_pct')) <= 6.0):
            return_reason.append('BAD_RISK')
        if nt['setup_story_v74'] in ('UNCLASSIFIED_CONTEXT', 'ENVIRONMENT_INVALIDATES_DEMAND', 'NO_RECLAIM_CONFIRMATION'):
            return_reason.append('BAD_STORY')
        nt['v74_reject_reason'] = '+'.join(return_reason) if return_reason else 'PASS'
        out.append(nt)
    return out


def main() -> None:
    annotated_path = V73_DIR / 'v73_annotated_trades.json'
    env_path = V73_DIR / 'v73_env_by_date.json'
    trades = json.loads(annotated_path.read_text())
    env = add_env_slopes(json.loads(env_path.read_text()))
    annotated = annotate_trades(trades, env)
    selected = [t for t in annotated if t.get('v74_core_gate')]
    report = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'engine': 'V74_ENV_STATE_MACHINE_GATE_SEARCH',
        'hypothesis': 'Demand Zone validity requires environment state machine + separate continuation/reversal setup stories before POI entry.',
        'base_v71': metrics(annotated),
        'v73_selected_gate_reference': metrics([t for t in annotated if t.get('market_env') in ('BULL_ENV', 'RECOVERY_ENV') and t.get('stock_trend_state') in ('UP_CONTINUATION','BULL_TRANSITION','COMPRESSION_RANGE') and t.get('reaction_type') == 'RECLAIM_HIGH' and 2.0 <= f(t.get('risk_pct')) <= 6.0 and t.get('pd_zone') in VALID_PD_ZONES]),
        'v74_core_gate': metrics(selected),
        'buckets': {
            'year': bucket(selected, lambda t: str(t.get('entry_date',''))[:4]),
            'market_state_v74': bucket(selected, lambda t: t.get('market_state_v74')),
            'setup_story_v74': bucket(selected, lambda t: t.get('setup_story_v74')),
            'stock_trend_state': bucket(selected, lambda t: t.get('stock_trend_state')),
            'stock_last_event': bucket(selected, lambda t: t.get('stock_last_event')),
            'pd_zone': bucket(selected, lambda t: t.get('pd_zone')),
            'risk_bin': bucket(selected, lambda t: '<2' if f(t.get('risk_pct')) < 2 else ('2-4' if f(t.get('risk_pct')) < 4 else ('4-6' if f(t.get('risk_pct')) <= 6 else '>6'))),
            'exit_reason': bucket(selected, lambda t: t.get('exit_reason')),
        },
        'rejection': bucket(annotated, lambda t: t.get('v74_reject_reason')),
        'env_state_by_year_all_trades': bucket(annotated, lambda t: f"{str(t.get('entry_date',''))[:4]}:{t.get('market_state_v74')}"),
        'files': {
            'annotated': str(OUT_DIR / 'v74_annotated_trades.json'),
            'selected': str(OUT_DIR / 'v74_selected_trades.json'),
            'env': str(OUT_DIR / 'v74_env_by_date.json'),
            'report': str(OUT_DIR / 'v74_report.json'),
        },
    }
    (OUT_DIR / 'v74_env_by_date.json').write_text(json.dumps(env, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v74_annotated_trades.json').write_text(json.dumps(annotated, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v74_selected_trades.json').write_text(json.dumps(selected, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v74_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: report[k] for k in ('base_v71', 'v73_selected_gate_reference', 'v74_core_gate', 'buckets', 'files')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
