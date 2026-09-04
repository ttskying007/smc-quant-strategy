#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List

from v81_contextual_smc_generator import f
from v81_full_market_scan import bucket, metrics

SRC = Path('/root/.hermes/smc_opt_v85_mixed_accumulation_generator/v85_candidates.json')
OUT = Path('/root/.hermes/smc_opt_v85_production_gate')
OUT.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def zone_width(row: Dict[str, Any]) -> float:
    return f(row.get('v85_zone_width_pct'), 999.0)


def passes_v85_production_gate(row: Dict[str, Any]) -> bool:
    return (
        1.0 < zone_width(row) <= 2.0
        and 1.0 < f(row.get('risk_pct'), 999.0) <= 1.5
        and f(row.get('hold_bars'), 999.0) <= 2
        and row.get('v83_takeover_type') == 'HOLD_ABOVE_POI'
        and str(row.get('entry_date')) != str(row.get('exit_date'))
    )


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
    rows = load_json(SRC)
    selected = []
    for r in rows:
        if passes_v85_production_gate(r):
            nr = dict(r)
            nr['v85_production_gate'] = True
            nr['v85_gate_rule'] = '1<zone_width<=2 AND 1<risk_pct<=1.5 AND hold_bars<=2 AND HOLD_ABOVE_POI AND T+1'
            selected.append(nr)

    report = {
        'engine': 'V85_PRODUCTION_GATE',
        'source': str(SRC),
        'gate_rule': '1<zone_width_pct<=2; 1<risk_pct<=1.5; hold_bars<=2; takeover=HOLD_ABOVE_POI; T+1 enforced',
        'source_metrics': metrics(rows),
        'selected_metrics': metrics(selected),
        'year': bucket(selected, lambda r: str(r.get('entry_date',''))[:4]),
        'path': bucket(selected, lambda r: r.get('v85_path')),
        'market_state': bucket(selected, lambda r: r.get('market_state')),
        'market_substate': bucket(selected, lambda r: r.get('v85_market_substate')),
        'exit_reason': bucket(selected, lambda r: r.get('exit_reason')),
        'exit_reason_counts': dict(Counter(r.get('exit_reason') for r in selected)),
        't1_violations': sum(1 for r in selected if str(r.get('entry_date')) == str(r.get('exit_date'))),
        'field_audit': field_audit(selected),
        'production_criteria': {
            'total_n_ge_500': len(selected) >= 500,
            'each_year_2023_2026_n_ge_50': all(bucket(selected, lambda r: str(r.get('entry_date',''))[:4]).get(y, {}).get('n', 0) >= 50 for y in ['2023','2024','2025','2026']),
            'each_year_2023_2026_wr_ge_65': all(bucket(selected, lambda r: str(r.get('entry_date',''))[:4]).get(y, {}).get('wr', 0) >= 65 for y in ['2023','2024','2025','2026']),
            't1_zero': sum(1 for r in selected if str(r.get('entry_date')) == str(r.get('exit_date'))) == 0,
            'field_zero_missing': all(v == 0 for v in field_audit(selected).values()),
        },
    }
    (OUT / 'v85_production_candidates.json').write_text(json.dumps(selected, ensure_ascii=False))
    (OUT / 'v85_trades.json').write_text(json.dumps(selected, ensure_ascii=False))
    (OUT / 'v85_picks.json').write_text(json.dumps(selected, ensure_ascii=False))
    (OUT / 'v85_production_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
