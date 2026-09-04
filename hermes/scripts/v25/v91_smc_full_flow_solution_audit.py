#!/usr/bin/env python3
"""V91 SMC full-flow audit and production-candidate selector.

Goal:
- Verify the exposed V88/V90 issues with a full 3-year, full-market audit.
- Keep the production-sized 90%+ WR candidate from V90.
- Separately identify an elite MTF/RR layer that follows the intended SMC stack:
  large timeframe trend -> medium timeframe signal -> small timeframe entry.

This script is report/selection only: it does not mutate V88/V90 baselines.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Tuple

from v81_full_market_scan import KLINE_DIR, load_json
from v90_daily_full_market_scanner import v88_contract_from_candidate

ROOT = Path('/root/.hermes')
V90_ROWS = ROOT / 'smc_opt_v90_daily_full_market_scanner/v90_3y_v86_gate_known_bsl_rows.json'
V87_ROWS = ROOT / 'smc_opt_v87_mtf_entry_rr_matrix/v87_matrix_rows.json'
V90_ACTIVE = ROOT / 'smc_opt_v90_daily_full_market_scanner/v90_active_picks.json'
OUT = ROOT / 'smc_opt_v91_smc_full_flow_solution'
OUT.mkdir(parents=True, exist_ok=True)

TARGET_WR = 90.0
TARGET_MIN_SAMPLE = 500
TARGET_MIN_AVG_R = 2.0
TARGET_MIN_PAYOFF_ELITE = 1.5

ELITE_COMBO = 'zone_limit|hybrid_tight|liq_then_2r_runner'
ELITE_FILTER = 'WEEKLY_BULL_DAILY_BULL'
PRODUCTION_FILTER = 'EXCLUDE_RECOVERY_ALL_WEAK_STATES'


def load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text())


def num(x: Any, default: float = 0.0) -> float:
    try:
        if x in (None, ''):
            return default
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def date_key(x: Any) -> str:
    s = ''.join(ch for ch in str(x or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def win(row: Dict[str, Any]) -> bool:
    return num(row.get('pnl_pct')) > 0


def metrics(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rs = list(rows)
    n = len(rs)
    if not n:
        return {'n': 0, 'wr': 0.0, 'avg_pnl': 0.0, 'cum': 0.0, 'avg_rr': 0.0, 'avg_realized_R': 0.0, 'payoff_ratio': 0.0, 'sl_rate': 0.0}
    pnls = [num(r.get('pnl_pct')) for r in rs]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    avg_rr_values = [num(r.get('rr')) for r in rs if num(r.get('rr')) > 0]
    realized_r = []
    for r, p in zip(rs, pnls):
        risk = num(r.get('risk_pct')) or num(r.get('risk_pct_v87')) or 0.0001
        realized_r.append(p / max(risk, 0.0001))
    return {
        'n': n,
        'wr': round(sum(p > 0 for p in pnls) / n * 100, 2),
        'avg_pnl': round(sum(pnls) / n, 4),
        'cum': round(sum(pnls), 2),
        'avg_rr': round(sum(avg_rr_values) / len(avg_rr_values), 4) if avg_rr_values else 0.0,
        'avg_realized_R': round(sum(realized_r) / len(realized_r), 4),
        'payoff_ratio': round((sum(wins) / len(wins)) / abs(sum(losses) / len(losses)), 4) if wins and losses else 0.0,
        'sl_rate': round(sum(str(r.get('exit_reason')) in {'SL_HIT', 'EXIT_POI_CLOSE_BREAK', 'EXIT_TREND_STRUCTURE_DAMAGE'} for r in rs) / n * 100, 2),
        'avg_mfe_r': round(sum(num(r.get('mfe_r')) for r in rs) / n, 4),
    }


def bucket(rows: Iterable[Dict[str, Any]], key: Callable[[Dict[str, Any]], Any]) -> Dict[str, Any]:
    g: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        g[str(key(r))].append(r)
    return {k: metrics(v) for k, v in sorted(g.items())}


def production_filter(row: Dict[str, Any]) -> bool:
    if row.get('market_state') != 'RECOVERY':
        return True
    return row.get('v90_recovery_substate') in {'RECOVERY_CONFIRMED_FAST_RECLAIM', 'RECOVERY_STABLE_HIGHER_LOW'}


def v87_combo(row: Dict[str, Any]) -> str:
    return f"{row.get('entry_mode')}|{row.get('sl_mode')}|{row.get('tp_mode')}"


def elite_filter(row: Dict[str, Any]) -> bool:
    return (
        v87_combo(row) == ELITE_COMBO
        and row.get('weekly_state') == 'BULL_CONTINUATION'
        and row.get('daily_state') == 'BULL_CONTINUATION'
    )


def no_bear_any_tf(row: Dict[str, Any]) -> bool:
    bad = {'BEAR_RISK', 'NO_M60', 'NO_WEEKLY', 'UNKNOWN'}
    return all(row.get(k) not in bad for k in ('weekly_state', 'daily_state', 'm60_state'))


def evaluate_v87_candidates(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    filters: Dict[str, Callable[[Dict[str, Any]], bool]] = {
        'ALL': lambda r: True,
        'MTF_SCORE_3': lambda r: num(r.get('mtf_score')) >= 3,
        'NO_BEAR_ANY_TF': no_bear_any_tf,
        'WEEKLY_BULL_DAILY_BULL': lambda r: r.get('weekly_state') == 'BULL_CONTINUATION' and r.get('daily_state') == 'BULL_CONTINUATION',
        'WEEKLY_BULL_REC_DAILY_BULL_REC_M60_BULL_REC': lambda r: r.get('weekly_state') in {'BULL_CONTINUATION','RECOVERY'} and r.get('daily_state') in {'BULL_CONTINUATION','RECOVERY'} and r.get('m60_state') in {'BULL_CONTINUATION','RECOVERY'},
        'MARKET_NOT_RECOVERY_ACCUM': lambda r: r.get('market_state') not in {'RECOVERY','ACCUMULATION'},
    }
    combos = sorted(set(v87_combo(r) for r in rows))
    out = []
    for combo in combos:
        base = [r for r in rows if v87_combo(r) == combo]
        for name, fn in filters.items():
            subset = [r for r in base if fn(r)]
            if len(subset) < 80:
                continue
            m = metrics(subset)
            years = bucket(subset, lambda r: date_key(r.get('entry_date'))[:4])
            m.update({
                'combo': combo,
                'filter': name,
                'wr90_ok': m['wr'] >= TARGET_WR,
                'avg_rr2_ok': m['avg_rr'] >= TARGET_MIN_AVG_R,
                'payoff15_ok': m['payoff_ratio'] >= TARGET_MIN_PAYOFF_ELITE,
                'sample500_ok': m['n'] >= TARGET_MIN_SAMPLE,
                'year': years,
            })
            m['elite_pass'] = bool(m['wr90_ok'] and m['avg_rr2_ok'] and m['payoff15_ok'])
            out.append(m)
    return sorted(out, key=lambda x: (x['elite_pass'], x['wr'], x['avg_rr'], x['payoff_ratio'], x['n']), reverse=True)


def field_audit(rows: List[Dict[str, Any]], keys: List[str]) -> Dict[str, int]:
    out = {}
    for k in keys:
        out[k] = sum(1 for r in rows if r.get(k) in (None, '', [], {}) or (k in {'entry_price','sl','tp1','tp2','tp3','rr','cost_line','volatility_pct','zone_low','zone_high'} and num(r.get(k)) <= 0))
    return out


def kline_path(symbol: str) -> Path:
    return KLINE_DIR / f"{str(symbol).replace('.', '_')}_daily_750.json"


def enrich_production_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach V88 scanner execution contract to historical V90 audit rows.

    The V90 3Y audit rows intentionally came from V85 simulated trades and only
    held signal/replay fields. For release-gate validation we need the same
    frontend/execution fields as active V90 scanner rows: sl/tp ladder, zone,
    volatility and cost line. This does not alter pnl/win metrics.
    """
    cache: Dict[str, List[Dict[str, Any]]] = {}
    out: List[Dict[str, Any]] = []
    for r in rows:
        sym = str(r.get('symbol'))
        if sym not in cache:
            cache[sym] = load_json(kline_path(sym)) if kline_path(sym).exists() else []
        if cache[sym]:
            nr = v88_contract_from_candidate(r, cache[sym])
            nr['engine'] = 'V91_PRODUCTION_BACKTEST_CONTRACT'
            nr['backtest_source_engine'] = r.get('engine')
            # Preserve realized historical replay fields from V85/V90 audit.
            for k in ('pnl_pct','exit_reason','exit_date','hold_bars','known_target_valid','future_target_violation'):
                if k in r:
                    nr[k] = r[k]
        else:
            nr = dict(r)
        out.append(nr)
    return out


def main() -> None:
    v90_rows = load(V90_ROWS, [])
    v87_rows = load(V87_ROWS, [])
    active = load(V90_ACTIVE, [])

    production_raw_rows = [r for r in v90_rows if production_filter(r)]
    production_rows = enrich_production_rows(production_raw_rows)
    v87_ranked = evaluate_v87_candidates(v87_rows)
    elite_rows = [r for r in v87_rows if elite_filter(r)]

    production_raw_m = metrics(production_raw_rows)
    production_m = dict(production_raw_m)
    contract_m = metrics(production_rows)
    production_m.update({
        'name': PRODUCTION_FILTER,
        'sample500_ok': production_m['n'] >= TARGET_MIN_SAMPLE,
        'wr90_ok': production_m['wr'] >= TARGET_WR,
        'avg_realized_R2_ok': production_m['avg_realized_R'] >= TARGET_MIN_AVG_R,
        'contract_avg_rr': contract_m['avg_rr'],
        'contract_field_metrics_note': 'contract_avg_rr comes from V88/V90 frontend execution contract; avg_realized_R comes from 3Y replay source rows.',
        'production_pass': bool(production_m['n'] >= TARGET_MIN_SAMPLE and production_m['wr'] >= TARGET_WR and production_m['avg_realized_R'] >= TARGET_MIN_AVG_R),
    })

    elite_m = metrics(elite_rows)
    elite_m.update({
        'name': f'{ELITE_COMBO}+{ELITE_FILTER}',
        'wr90_ok': elite_m['wr'] >= TARGET_WR,
        'avg_rr2_ok': elite_m['avg_rr'] >= TARGET_MIN_AVG_R,
        'payoff15_ok': elite_m['payoff_ratio'] >= TARGET_MIN_PAYOFF_ELITE,
        'elite_pass': bool(elite_m['wr'] >= TARGET_WR and elite_m['avg_rr'] >= TARGET_MIN_AVG_R and elite_m['payoff_ratio'] >= TARGET_MIN_PAYOFF_ELITE),
    })

    required_v90 = ['engine','pick_date','join_date','zone_type','zone_low','zone_high','cost_line','volatility_pct','entry_price','sl','tp1','tp2','tp3','rr','v90_target_semantics']
    active_required = required_v90 + ['zone','volatility']
    required_v87 = ['weekly_state','daily_state','m60_state','mtf_score','entry_mode','entry_price','sl','tp1','tp2','tp3','rr','exit_legs','mfe_r','mae_r']

    report = {
        'engine': 'V91_SMC_FULL_FLOW_SOLUTION_AUDIT',
        'targets': {
            'production_min_sample': TARGET_MIN_SAMPLE,
            'production_min_wr': TARGET_WR,
            'production_min_avg_realized_R': TARGET_MIN_AVG_R,
            'elite_min_wr': TARGET_WR,
            'elite_min_avg_rr': TARGET_MIN_AVG_R,
            'elite_min_payoff_ratio': TARGET_MIN_PAYOFF_ELITE,
        },
        'source_rows': {
            'v90_3y_rows': len(v90_rows),
            'v87_mtf_matrix_rows': len(v87_rows),
            'v90_active_rows': len(active),
        },
        'production_candidate': production_m,
        'production_by_year': bucket(production_rows, lambda r: date_key(r.get('entry_date'))[:4]),
        'production_by_market_state': bucket(production_rows, lambda r: r.get('market_state')),
        'production_by_recovery_substate': bucket([r for r in production_rows if r.get('market_state') == 'RECOVERY'], lambda r: r.get('v90_recovery_substate')),
        'production_loss_buckets': bucket([r for r in production_rows if not win(r)], lambda r: f"{r.get('market_state')}|{r.get('exit_reason')}"),
        'elite_mtf_rr_candidate': elite_m,
        'elite_by_year': bucket(elite_rows, lambda r: date_key(r.get('entry_date'))[:4]),
        'elite_by_mtf_score': bucket(elite_rows, lambda r: r.get('mtf_score')),
        'top_mtf_rr_solutions': v87_ranked[:30],
        'audits': {
            'production_field_audit': field_audit(production_rows, required_v90),
            'active_field_audit': field_audit(active, active_required),
            'elite_field_audit': field_audit(elite_rows, required_v87),
            't1_violations_production': sum(1 for r in production_rows if date_key(r.get('entry_date')) == date_key(r.get('exit_date'))),
            'future_target_violations_production': sum(1 for r in production_rows if r.get('future_target_violation')),
        },
        'smc_stack_verdict': {
            'large_tf_trend': 'V87 confirms weekly_state filter improves WR/RR but sample falls below 500; use as elite tier, not universal gate.',
            'medium_tf_signal': 'V90 production-sized candidate uses V85/V86 BOS/POI/takeover signal and weak RECOVERY rejection.',
            'small_tf_entry': '60min entry improves strictness only for small elite samples because 60min history coverage is incomplete; zone_limit is the deployable small-entry proxy.',
        },
    }
    report['final_verdict'] = (
        'PASS_PRODUCTION_WR90_AVG_R2_AND_PASS_ELITE_MTF_RR'
        if production_m['production_pass'] and elite_m['elite_pass']
        else 'PARTIAL_PASS_REQUIRES_MORE_MTF_HISTORY_OR_GATE_REPAIR'
    )

    (OUT / 'v91_production_rows.json').write_text(json.dumps(production_rows, ensure_ascii=False))
    (OUT / 'v91_elite_mtf_rr_rows.json').write_text(json.dumps(elite_rows, ensure_ascii=False))
    (OUT / 'v91_full_flow_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
