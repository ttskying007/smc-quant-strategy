#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from v81_contextual_smc_generator import f
from v81_full_market_scan import bucket, metrics
from v85_apply_production_gate import field_audit, load_json

SRC = Path('/root/.hermes/smc_opt_v85_production_gate/v85_trades.json')
OUT = Path('/root/.hermes/smc_opt_v86_production_gate')
OUT.mkdir(parents=True, exist_ok=True)


def passes_v86_production_gate(row: Dict[str, Any]) -> bool:
    return (
        1.0 < f(row.get('v85_zone_width_pct'), 999.0) <= 1.6
        and 1.0 < f(row.get('risk_pct'), 999.0) <= 1.5
        and f(row.get('hold_bars'), 999.0) <= 2
        and row.get('v83_takeover_type') == 'HOLD_ABOVE_POI'
        and str(row.get('entry_date')) != str(row.get('exit_date'))
    )


def production_criteria(rows: List[Dict[str, Any]]) -> Dict[str, bool]:
    yb = bucket(rows, lambda r: str(r.get('entry_date',''))[:4])
    fa = field_audit(rows)
    return {
        'total_n_ge_500': len(rows) >= 500,
        'each_year_2023_2026_n_ge_50': all(yb.get(y, {}).get('n', 0) >= 50 for y in ['2023','2024','2025','2026']),
        'each_year_2023_2026_wr_ge_65': all(yb.get(y, {}).get('wr', 0) >= 65 for y in ['2023','2024','2025','2026']),
        't1_zero': sum(1 for r in rows if str(r.get('entry_date')) == str(r.get('exit_date'))) == 0,
        'field_zero_missing': all(v == 0 for v in fa.values()),
    }


def main() -> None:
    rows = load_json(SRC)
    selected = []
    rejected = []
    for r in rows:
        nr = dict(r)
        if passes_v86_production_gate(nr):
            nr['v86_production_gate'] = True
            nr['v86_gate_rule'] = 'V85 core + zone_width<=1.6 + T+1'
            nr['engine'] = 'V86'
            nr['pick_scope'] = 'ACTIVE_CANDIDATE'
            nr['is_active_pick'] = True
            nr['setup_status'] = 'ACTIVE_CANDIDATE'
            nr['state'] = 'ACTIVE_CANDIDATE'
            selected.append(nr)
        else:
            nr['v86_production_gate'] = False
            rejected.append(nr)
    report = {
        'engine': 'V86_PRODUCTION_GATE',
        'source': str(SRC),
        'gate_rule': '1<zone_width_pct<=1.6; 1<risk_pct<=1.5; hold_bars<=2; takeover=HOLD_ABOVE_POI; T+1 enforced',
        'source_metrics': metrics(rows),
        'selected_metrics': metrics(selected),
        'rejected_metrics': metrics(rejected),
        'year': bucket(selected, lambda r: str(r.get('entry_date',''))[:4]),
        'path': bucket(selected, lambda r: r.get('v85_path')),
        'market_state': bucket(selected, lambda r: r.get('market_state')),
        'market_substate': bucket(selected, lambda r: r.get('v85_market_substate')),
        'exit_reason': bucket(selected, lambda r: r.get('exit_reason')),
        'exit_reason_counts': dict(Counter(r.get('exit_reason') for r in selected)),
        'rejected_by_market_state': bucket(rejected, lambda r: r.get('market_state')),
        'rejected_by_exit_reason': bucket(rejected, lambda r: r.get('exit_reason')),
        't1_violations': sum(1 for r in selected if str(r.get('entry_date')) == str(r.get('exit_date'))),
        'field_audit': field_audit(selected),
        'production_criteria': production_criteria(selected),
    }
    (OUT / 'v86_production_candidates.json').write_text(json.dumps(selected, ensure_ascii=False))
    (OUT / 'v86_trades.json').write_text(json.dumps(selected, ensure_ascii=False))
    (OUT / 'v86_picks.json').write_text(json.dumps(selected, ensure_ascii=False))
    (OUT / 'v86_production_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
