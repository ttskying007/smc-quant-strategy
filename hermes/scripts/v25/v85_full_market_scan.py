#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List

from v81_full_market_scan import KLINE_DIR, ENV_PATH, bucket, load_json, metrics, normalize_env, simulate_trade, symbol_from_path
from v85_mixed_accumulation_generator import generate_v85_candidates

OUT_DIR = Path('/root/.hermes/smc_opt_v85_mixed_accumulation_generator')
OUT_DIR.mkdir(parents=True, exist_ok=True)


def field_audit(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    return {
        'missing_select_date': sum(1 for r in rows if not r.get('select_date')),
        'missing_pick_date': sum(1 for r in rows if not r.get('pick_date')),
        'missing_join_date': sum(1 for r in rows if not r.get('join_date')),
        'missing_zone': sum(1 for r in rows if not (r.get('zone_low') and r.get('zone_high'))),
        'missing_zone_type': sum(1 for r in rows if not r.get('zone_type')),
        'missing_cost_line': sum(1 for r in rows if not r.get('smart_money_cost')),
        'missing_volatility': sum(1 for r in rows if not r.get('volatility_pct')),
    }


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
        cands = generate_v85_candidates(sym, ks, env_by_date)
        for c in cands:
            row = simulate_trade(c, ks)
            row['v85_path'] = c.get('v85_path')
            row['v85_market_substate'] = c.get('v85_market_substate')
            row['v85_reason'] = c.get('v85_reason')
            row['v85_zone_width_pct'] = c.get('v85_zone_width_pct')
            row['v83_takeover_type'] = c.get('v83_takeover_type')
            row['smart_money_cost'] = c.get('smart_money_cost') or row.get('smart_money_cost')
            row['volatility_pct'] = c.get('volatility_pct') or row.get('volatility_pct')
            all_candidates.append(row)
        scanned += 1

    report = {
        'engine': 'V85_MIXED_ACCUMULATION_GENERATOR',
        'scanned_symbols': scanned,
        'candidate_count': len(all_candidates),
        'metrics': metrics(all_candidates),
        'year': bucket(all_candidates, lambda r: str(r.get('entry_date',''))[:4]),
        'path': bucket(all_candidates, lambda r: r.get('v85_path')),
        'market_substate': bucket(all_candidates, lambda r: r.get('v85_market_substate')),
        'market_state': bucket(all_candidates, lambda r: r.get('market_state')),
        'takeover': bucket(all_candidates, lambda r: r.get('v83_takeover_type')),
        'exit_reason_counts': dict(Counter(r.get('exit_reason') for r in all_candidates)),
        'exit_reason': bucket(all_candidates, lambda r: r.get('exit_reason')),
        't1_violations': sum(1 for r in all_candidates if str(r.get('entry_date')) == str(r.get('exit_date'))),
        'field_audit': field_audit(all_candidates),
    }
    (OUT_DIR / 'v85_candidates.json').write_text(json.dumps(all_candidates, ensure_ascii=False))
    (OUT_DIR / 'v85_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
