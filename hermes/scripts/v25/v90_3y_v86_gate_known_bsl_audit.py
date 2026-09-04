#!/usr/bin/env python3
"""V90 full-history audit: V86 gate + V90 non-future target semantics.

Reads V85 3-year full-market simulated candidates, applies the same V90/V86
production gate used by the daily scanner, annotates pre-entry known BSL target
and RECOVERY substate, then reports whether any structurally valid subset meets
90% WR / payoff requirements without using 60min or future liquidity targets.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from v81_full_market_scan import KLINE_DIR, load_json, metrics
from v90_daily_full_market_scanner import known_bsl_target, passes_v86_gate, recovery_substate, field_audit

SRC = Path('/root/.hermes/smc_opt_v85_mixed_accumulation_generator/v85_candidates.json')
V88 = Path('/root/.hermes/smc_opt_v88_production_contract/v88_trades.json')
OUT = Path('/root/.hermes/smc_opt_v90_daily_full_market_scanner')
OUT.mkdir(parents=True, exist_ok=True)

MIN_PRODUCTION_N = 500
TARGET_WR = 90.0


def num(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == '':
            return default
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def date_key(x: Any) -> str:
    s = ''.join(ch for ch in str(x or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def symbol_path(symbol: str) -> Path:
    return KLINE_DIR / f"{symbol.replace('.', '_')}_daily_750.json"


def load_ks(symbol: str, cache: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    if symbol not in cache:
        p = symbol_path(symbol)
        cache[symbol] = load_json(p) if p.exists() else []
    return cache[symbol]


def payoff(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rs = list(rows)
    if not rs:
        return {'n': 0, 'wr': 0, 'avg_pnl': 0, 'payoff_ratio': 0, 'avg_realized_R': 0, 'sl_rate': 0, 'cum': 0}
    pnls = [num(r.get('pnl_pct')) for r in rs]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    risks = [max(num(r.get('risk_pct')), 0.0001) for r in rs]
    realized_r = [p / risk for p, risk in zip(pnls, risks)]
    return {
        'n': len(rs),
        'wr': round(sum(p > 0 for p in pnls) / len(pnls) * 100, 2),
        'avg_pnl': round(sum(pnls) / len(pnls), 4),
        'payoff_ratio': round((sum(wins) / len(wins)) / abs(sum(losses) / len(losses)), 4) if wins and losses else 0,
        'avg_realized_R': round(sum(realized_r) / len(realized_r), 4),
        'sl_rate': round(sum(str(r.get('exit_reason')) in {'EXIT_POI_CLOSE_BREAK','EXIT_TREND_STRUCTURE_DAMAGE'} for r in rs) / len(rs) * 100, 2),
        'tp_rate': round(sum(str(r.get('exit_reason')) == 'TAKE_PROFIT_LIQUIDITY_TARGET' for r in rs) / len(rs) * 100, 2),
        'cum': round(sum(pnls), 2),
    }


def bucket(rows: Iterable[Dict[str, Any]], key) -> Dict[str, Any]:
    g: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        g[str(key(r))].append(r)
    return {k: payoff(v) for k, v in sorted(g.items())}


def annotate_gate_rows(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    ks_cache: Dict[str, List[Dict[str, Any]]] = {}
    gated: List[Dict[str, Any]] = []
    reject = Counter()
    for r0 in rows:
        r = dict(r0)
        if not passes_v86_gate(r):
            reject['V86_GATE_FAIL'] += 1
            continue
        sym = str(r.get('symbol'))
        ks = load_ks(sym, ks_cache)
        entry_idx = int(num(r.get('entry_idx'), -1))
        if not ks or entry_idx < 0 or entry_idx >= len(ks):
            reject['KLINE_OR_ENTRY_MISSING'] += 1
            continue
        bsl = known_bsl_target(ks, entry_idx, num(r.get('entry_price')))
        r.update(bsl)
        r['v90_recovery_substate'] = recovery_substate(r, ks)
        r['v90_target_semantics'] = 'PRE_ENTRY_KNOWN_BSL_OR_FIXED_RR_NO_FUTURE_LIQUIDITY_TARGET'
        r['known_target_valid'] = bool(num(r.get('known_bsl_target')) > 0 and int(num(r.get('known_bsl_idx'), -1)) < entry_idx)
        r['future_target_violation'] = bool(num(r.get('known_bsl_target')) > 0 and int(num(r.get('known_bsl_idx'), 10**9)) >= entry_idx)
        r['engine'] = 'V90_3Y_AUDIT_V86_GATE_KNOWN_BSL'
        r['cost_line'] = r.get('smart_money_cost') or r.get('entry_price')
        r['volatility_pct'] = r.get('volatility_pct') or r.get('risk_pct')
        gated.append(r)
    return gated, dict(reject)


def combos(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    candidates: List[Tuple[str, List[Dict[str, Any]]]] = []
    candidates.append(('ALL_V86_GATE', rows))
    candidates.append(('EXCLUDE_RECOVERY', [r for r in rows if r.get('market_state') != 'RECOVERY']))
    candidates.append(('BULL_CONTINUATION_ONLY', [r for r in rows if r.get('market_state') == 'BULL_CONTINUATION']))
    candidates.append(('MIXED_ONLY', [r for r in rows if r.get('market_state') == 'MIXED']))
    candidates.append(('KNOWN_BSL_ONLY', [r for r in rows if r.get('known_target_valid')]))
    candidates.append(('KNOWN_BSL_EXCLUDE_RECOVERY', [r for r in rows if r.get('known_target_valid') and r.get('market_state') != 'RECOVERY']))
    candidates.append(('EXCLUDE_RECOVERY_WEAK', [r for r in rows if r.get('v90_recovery_substate') != 'RECOVERY_WEAK_LOWER_LOW_OR_FAILED_HIGH']))
    candidates.append(('EXCLUDE_RECOVERY_ALL_WEAK_STATES', [r for r in rows if r.get('market_state') != 'RECOVERY' or r.get('v90_recovery_substate') in {'RECOVERY_CONFIRMED_FAST_RECLAIM','RECOVERY_STABLE_HIGHER_LOW'}]))
    out = []
    for name, subset in candidates:
        m = payoff(subset)
        m['name'] = name
        m['production_n_ok'] = m['n'] >= MIN_PRODUCTION_N
        m['wr90_ok'] = m['wr'] >= TARGET_WR
        m['production_pass'] = bool(m['production_n_ok'] and m['wr90_ok'])
        out.append(m)
    return sorted(out, key=lambda x: (x['production_pass'], x['wr'], x['n']), reverse=True)


def main() -> None:
    src_rows = json.loads(SRC.read_text())
    gated, reject = annotate_gate_rows(src_rows)
    v88_rows = json.loads(V88.read_text()) if V88.exists() else []
    report = {
        'engine': 'V90_3Y_AUDIT_V86_GATE_KNOWN_BSL',
        'source': str(SRC),
        'source_rows': len(src_rows),
        'gated_rows': len(gated),
        'reject_counts': reject,
        'target': {'min_n': MIN_PRODUCTION_N, 'wr_percent': TARGET_WR},
        'v88_baseline': payoff(v88_rows),
        'v90_v86_gate_baseline': payoff(gated),
        'production_combos': combos(gated),
        'by_year': bucket(gated, lambda r: date_key(r.get('entry_date'))[:4]),
        'by_market_state': bucket(gated, lambda r: r.get('market_state')),
        'by_recovery_substate': bucket([r for r in gated if r.get('market_state') == 'RECOVERY'], lambda r: r.get('v90_recovery_substate')),
        'by_known_target': bucket(gated, lambda r: 'KNOWN_BSL' if r.get('known_target_valid') else 'FIXED_RR_FALLBACK'),
        'exit_reason_counts': dict(Counter(str(r.get('exit_reason')) for r in gated)),
        'field_audit': field_audit(gated),
        'guards': {
            't1_violations': sum(1 for r in gated if date_key(r.get('entry_date')) == date_key(r.get('exit_date'))),
            'future_target_violations': sum(1 for r in gated if r.get('future_target_violation')),
            'known_bsl_rate': round(sum(1 for r in gated if r.get('known_target_valid')) / len(gated) * 100, 2) if gated else 0,
        },
        'conclusion': '',
    }
    passing = [c for c in report['production_combos'] if c['production_pass']]
    if passing:
        report['conclusion'] = 'FOUND_PRODUCTION_CANDIDATE_MEETING_90WR_AND_SAMPLE_GATE'
    else:
        report['conclusion'] = 'NO_90WR_PRODUCTION_CANDIDATE_UNDER_V86_GATE_AND_NON_FUTURE_TARGET;_RECOVERY_REMAINS_NON_PRODUCTION_WITH_DAILY_ONLY_DATA'
    (OUT / 'v90_3y_v86_gate_known_bsl_rows.json').write_text(json.dumps(gated, ensure_ascii=False))
    (OUT / 'v90_3y_v86_gate_known_bsl_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
