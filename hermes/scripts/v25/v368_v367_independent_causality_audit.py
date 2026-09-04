#!/usr/bin/env python3
"""Independent row-level causality audit for the V367 delayed-entry rebuild."""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path('/root/.hermes')
AUD, KDIR = ROOT / 'smc_audit', ROOT / 'kline_cache'
SRC = AUD / 'v367_causal_v132_reentry_walkforward_latest.json'
OUT = AUD / f'v368_v367_independent_causality_audit_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v368_v367_independent_causality_audit_latest.json'


def date_of(bar: dict) -> str:
    return ''.join(c for c in str(bar.get('t') or bar.get('date') or '') if c.isdigit())[:8]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = json.loads(SRC.read_text())
    df = pd.read_csv(report['artifacts']['replayed_csv'], low_memory=False)
    cache: dict[str, list[dict]] = {}
    counts = {'rows': int(len(df)), 'missing_kline': 0, 'index_mismatch': 0, 'date_mismatch': 0, 'open_price_mismatch': 0, 'exit_not_after_entry': 0, 'same_day_exit': 0, 'bad_confirmation_n': 0}
    samples = []
    for row in df.to_dict('records'):
        sym = str(row['symbol'])
        if sym not in cache:
            try:
                cache[sym] = json.loads((KDIR / f'{sym.replace(".", "_")}_daily_750.json').read_text())
            except Exception:
                cache[sym] = []
        bars = cache[sym]
        if not bars:
            counts['missing_kline'] += 1
            continue
        n = int(float(row['v367_confirmation_n']))
        reclaim = int(float(row['reclaim_idx']))
        entry_i = int(float(row['entry_idx']))
        exit_i = int(float(row['v132_delayed_exit_idx']))
        expected = reclaim + n + 1
        errors = []
        if n not in (2, 3): counts['bad_confirmation_n'] += 1; errors.append('bad_n')
        if entry_i != expected: counts['index_mismatch'] += 1; errors.append('entry_idx')
        if entry_i >= len(bars) or date_of(bars[entry_i]) != str(row['entry_date']): counts['date_mismatch'] += 1; errors.append('entry_date')
        elif not math.isclose(float(bars[entry_i]['o']), float(row['entry_price']), rel_tol=0, abs_tol=1e-6): counts['open_price_mismatch'] += 1; errors.append('entry_open')
        if exit_i <= entry_i: counts['exit_not_after_entry'] += 1; errors.append('exit_idx')
        if str(row['exit_date']) <= str(row['entry_date']): counts['same_day_exit'] += 1; errors.append('exit_date')
        if errors and len(samples) < 20: samples.append({'symbol': sym, 'errors': errors, 'reclaim_idx': reclaim, 'n': n, 'entry_idx': entry_i, 'exit_idx': exit_i})
    result = {'version': 'V368_V367_INDEPENDENT_CAUSALITY_AUDIT_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'), 'no_write': True,
              'audit_contract': 'independently recompute entry_idx=reclaim_idx+confirmation_n+1, verify K-line entry date/open and strict T+1 exit',
              'counts': counts, 'samples': samples,
              'decision': 'CAUSALITY_PASS__V367_ENTRY_AND_T1_CONTRACT_HOLD' if not any(counts[k] for k in counts if k != 'rows') else 'CAUSALITY_FAIL__DO_NOT_USE_V367_METRICS',
              'source': report['artifacts']['replayed_csv']}
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v368_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
