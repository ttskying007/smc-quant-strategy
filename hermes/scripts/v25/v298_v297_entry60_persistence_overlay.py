#!/usr/bin/env python3
"""V298 no-write: entry-session 60m persistence overlay on V297 same-source ACC->MAN->DIS.

V297 generated same-source intraday lifecycle candidates but daily next-open execution
remained weak.  This script reuses the V294 executable entry-session persistence
machinery on V297 rows, mapping the intraday accumulation zone to zone_low/high.
No production, frontend, or watchlist writes.
"""
from __future__ import annotations

import csv
import importlib.util
import json
from datetime import datetime
from pathlib import Path

BASE = Path('/root/.hermes')
AUDIT = BASE / 'smc_audit'
V294_SCRIPT = BASE / 'scripts/v25/v294_entry60_persistence_audit.py'
V297 = json.loads((AUDIT / 'v297_intraday_acc_man_dis_latest.json').read_text())
ROWS = Path(V297['artifacts']['rows'])
INDMAP = AUDIT / 'v225_baostock_industry_participation_probe_20260627_031854/baostock_stock_industry.json'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v298_v297_entry60_persistence_no_write_{TS}'
LATEST = AUDIT / 'v298_v297_entry60_persistence_latest.json'


def load_v294():
    spec = importlib.util.spec_from_file_location('v294_core_for_v298', V294_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    core = load_v294()
    sym_ind = {r['symbol']: r.get('industry', '') for r in json.loads(INDMAP.read_text()) if r.get('symbol')}
    with ROWS.open() as fh:
        source = list(csv.DictReader(fh))
    for r in source:
        r['zone_low'] = r.get('acc_lo') or r.get('sl')
        r['zone_high'] = r.get('acc_hi') or r.get('entry')
    stock_count = len({r['symbol'] for r in source})
    raw = core.blank()
    for r in source:
        core.add(raw, r)
    stock_ctx, mctx, ictx, files60 = core.build_k_context(sym_ind)
    variants, best_rows = core.simulate(source, sym_ind, stock_ctx, mctx, ictx)
    best_path = OUT / 'v298_best_rows.csv'
    if best_rows:
        fields = []
        for r in best_rows:
            for k in r:
                if k not in fields:
                    fields.append(k)
        with best_path.open('w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader(); w.writerows(best_rows)
    summary = {
        'version': 'V298_V297_ENTRY60_PERSISTENCE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'hypothesis': 'Same-source ACC->MAN->DIS only works if the next entry session confirms durable 60m market/industry/stock persistence.',
        'source': str(ROWS), 'source_n': len(source), 'sixty_min_files': files60,
        'raw_v297_source': core.metrics(raw, stock_count, len(source)),
        'best_variant': variants[0] if variants else None,
        'top_variants': variants[:20],
        't1_violations_best': sum(1 for r in best_rows if r.get('t1_violation')),
        'artifacts': {'best_rows': str(best_path), 'summary': str(OUT / 'v298_summary.json')},
    }
    (OUT / 'v298_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({'latest': str(LATEST), 'raw': summary['raw_v297_source'], 'best': summary['best_variant'], 'top10': variants[:10], 't1': summary['t1_violations_best']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
