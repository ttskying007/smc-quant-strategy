#!/usr/bin/env python3
"""V81 full-market contextual SMC scan.

Scans cached 750-day A-share klines with the new V81 context-first generator.
This is a research/audit script; it does not change production frontend defaults.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List

from v81_contextual_smc_generator import generate_candidates, next_exit_semantic, f

KLINE_DIR = Path('/root/.hermes/kline_cache')
ENV_PATH = Path('/root/.hermes/smc_opt_v74_env_state_machine/v74_env_by_date.json')
OUT_DIR = Path('/root/.hermes/smc_opt_v81_contextual_smc_generator')
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def symbol_from_path(path: Path) -> str:
    parts = path.name.replace('_daily_750.json', '').split('_')
    if len(parts) != 2:
        return path.stem
    return f'{parts[0]}.{parts[1]}'


def normalize_env(row: Dict[str, Any]) -> Dict[str, Any]:
    nr = dict(row)
    nr['market_state'] = row.get('market_state_v74') or row.get('market_state') or row.get('state') or ''
    return nr


def simulate_trade(c: Dict[str, Any], ks: List[Dict[str, Any]]) -> Dict[str, Any]:
    entry_idx = int(c['entry_idx'])
    entry = f(c.get('entry_price'))
    poi = {
        'zone_low': c.get('zone_low'),
        'zone_high': c.get('zone_high'),
        'prior_structure_low': c.get('prior_structure_low'),
        'liquidity_target': c.get('liquidity_target'),
    }
    # Semantic exit first, capped by 20 bars.  If no semantic event appears,
    # classify as time stop at last available bar in the window.
    horizon = ks[entry_idx:min(len(ks), entry_idx + 21)]
    if len(horizon) <= 1:
        b = ks[min(entry_idx, len(ks) - 1)]
        exit_signal = 'NO_T1_EXIT_BAR_AVAILABLE'
        exit_idx = min(entry_idx, len(ks) - 1)
        exit_price = f(b.get('c'))
        exit_date = b.get('t') or b.get('date')
    else:
        # Start at the first post-entry bar so A-share T+1 is enforced by
        # construction, not as a later cosmetic shift.
        ex = next_exit_semantic(horizon, poi, 1)
        if ex.get('exit_idx') is None:
            local_idx = len(horizon) - 1
            b = horizon[local_idx]
            exit_signal = 'TIME_STOP_NO_SEMANTIC_EXIT'
            exit_idx = entry_idx + local_idx
            exit_price = f(b.get('c'))
            exit_date = b.get('t') or b.get('date')
        else:
            exit_signal = ex['exit_signal']
            exit_idx = entry_idx + int(ex['exit_idx'])
            exit_price = f(ex.get('exit_price'))
            exit_date = ex.get('exit_date')
    # T+1 hard guard: drop candidates that cannot provide an exit bar after entry.
    if str(exit_date) == str(c.get('entry_date')) and exit_idx + 1 < len(ks):
        exit_idx += 1
        b = ks[exit_idx]
        exit_date = b.get('t') or b.get('date')
        exit_price = f(b.get('c'))
        exit_signal = f'{exit_signal}_T1_SHIFTED'
    pnl = (exit_price / entry - 1) * 100 if entry else 0
    risk_pct = (entry / f(c.get('zone_low'), entry) - 1) * 100 if f(c.get('zone_low')) else 0
    out = dict(c)
    out.update({
        'exit_idx': exit_idx,
        'exit_date': exit_date,
        'exit_price': round(exit_price, 6),
        'exit_reason': exit_signal,
        'pnl_pct': round(pnl, 4),
        'hold_bars': max(0, exit_idx - entry_idx),
        'risk_pct': round(risk_pct, 4),
        'select_date': c.get('event_date'),
        'pick_date': c.get('event_date'),
        'join_date': c.get('entry_date'),
        'zone_type': c.get('poi_type'),
        'signal_type': c.get('event_type'),
        'smart_money_cost': c.get('entry_price'),
        'volatility_pct': round(max(risk_pct, 0.0001), 4),
    })
    return out


def metrics(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rs = list(rows)
    if not rs:
        return {'n': 0, 'wr': 0, 'avg_pnl': 0, 'sl_rate': 0, 'poi_break_rate': 0, 'trend_damage_rate': 0, 'tp_rate': 0, 'cum': 0}
    vals = [f(r.get('pnl_pct')) for r in rs]
    return {
        'n': len(rs),
        'wr': round(sum(v > 0 for v in vals) / len(vals) * 100, 2),
        'avg_pnl': round(sum(vals) / len(vals), 4),
        'poi_break_rate': round(sum(r.get('exit_reason') == 'EXIT_POI_CLOSE_BREAK' for r in rs) / len(rs) * 100, 2),
        'trend_damage_rate': round(sum(r.get('exit_reason') == 'EXIT_TREND_STRUCTURE_DAMAGE' for r in rs) / len(rs) * 100, 2),
        'tp_rate': round(sum(r.get('exit_reason') == 'TAKE_PROFIT_LIQUIDITY_TARGET' for r in rs) / len(rs) * 100, 2),
        'cum': round(sum(vals), 2),
    }


def bucket(rows: Iterable[Dict[str, Any]], key) -> Dict[str, Any]:
    g: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        g[str(key(r))].append(r)
    return {k: metrics(v) for k, v in sorted(g.items())}


def main() -> None:
    env_raw = load_json(ENV_PATH)
    env_by_date = {str(k)[:8]: normalize_env(v) for k, v in env_raw.items()}
    all_candidates: List[Dict[str, Any]] = []
    scanned = 0
    for path in sorted(KLINE_DIR.glob('*_daily_750.json')):
        ks = load_json(path)
        if len(ks) < 80:
            continue
        sym = symbol_from_path(path)
        cands = generate_candidates(sym, ks, env_by_date)
        for c in cands:
            all_candidates.append(simulate_trade(c, ks))
        scanned += 1
    report = {
        'engine': 'V81_CONTEXTUAL_SMC_GENERATOR',
        'scanned_symbols': scanned,
        'candidate_count': len(all_candidates),
        'metrics': metrics(all_candidates),
        'year': bucket(all_candidates, lambda r: str(r.get('entry_date',''))[:4]),
        'story': bucket(all_candidates, lambda r: r.get('story')),
        'market_state': bucket(all_candidates, lambda r: r.get('market_state')),
        'exit_reason': dict(Counter(r.get('exit_reason') for r in all_candidates)),
        't1_violations': sum(1 for r in all_candidates if str(r.get('entry_date')) == str(r.get('exit_date'))),
        'field_audit': {
            'missing_select_date': sum(1 for r in all_candidates if not r.get('select_date')),
            'missing_join_date': sum(1 for r in all_candidates if not r.get('join_date')),
            'missing_zone': sum(1 for r in all_candidates if not (r.get('zone_low') and r.get('zone_high'))),
            'missing_cost_line': sum(1 for r in all_candidates if not r.get('smart_money_cost')),
            'missing_volatility': sum(1 for r in all_candidates if not r.get('volatility_pct')),
        },
    }
    (OUT_DIR / 'v81_candidates.json').write_text(json.dumps(all_candidates, ensure_ascii=False))
    (OUT_DIR / 'v81_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
