#!/usr/bin/env python3
"""V65 signal sequence audit."""
from __future__ import annotations
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
V65_TRADES = ROOT / 'smc_opt_v65' / 'v65_trades.json'
V49_TRADES = ROOT / 'smc_opt_v49_exit_optimized' / 'v49_trades.json'
OUT_JSON = ROOT / 'smc_audit' / 'v65_signal_sequence_audit.json'
OUT_MD = ROOT / 'smc_audit' / 'v65_signal_sequence_audit.md'
ORDER = ['source_event_idx', 'zone_idx', 'retrace_index', 'conf_index', 'entry_index', 'exit_index']


def _i(x: Any, default=-1) -> int:
    try:
        return int(float(x))
    except Exception:
        return default


def _load(p: Path, default):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def main() -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    trade_path = V65_TRADES if V65_TRADES.exists() else V49_TRADES
    trades = _load(trade_path, [])
    rows = []
    counts = Counter()
    for t in trades:
        issues = []
        vals = [(k, _i(t.get(k))) for k in ORDER if not (k == 'retrace_index' and t.get('trade_role') == 'REENTRY')]
        for k, v in vals:
            if v < 0 and k in ('source_event_idx', 'zone_idx', 'conf_index', 'entry_index', 'exit_index'):
                issues.append(f'MISSING_{k.upper()}')
        for (ka, a), (kb, b) in zip(vals, vals[1:]):
            if a >= 0 and b >= 0 and a > b:
                issues.append(f'{ka}_GT_{kb}')
        if _i(t.get('entry_index')) >= 0 and _i(t.get('exit_index')) >= 0 and _i(t.get('exit_index')) < _i(t.get('entry_index')):
            issues.append('EXIT_BEFORE_ENTRY')
        if str(t.get('entry_date','')) > str(t.get('exit_date','')):
            issues.append('EXIT_DATE_BEFORE_ENTRY_DATE')
        counts.update(issues)
        rows.append({'symbol': t.get('symbol'), 'entry_date': t.get('entry_date'), 'idx': dict(vals), 'issues': issues, 'status': 'PASS' if not issues else 'FAIL'})
    bad = [r for r in rows if r['issues']]
    summary = {'generated_at': datetime.now().isoformat(timespec='seconds'), 'trade_file': str(trade_path), 'n_trades': len(trades), 'pass_count': len(rows)-len(bad), 'violation_count': len(bad), 'issue_counts': dict(counts)}
    OUT_JSON.write_text(json.dumps({'summary': summary, 'rows': rows}, ensure_ascii=False, indent=2))
    md = ['# V65 Signal Sequence Audit\n\n```json\n', json.dumps(summary, ensure_ascii=False, indent=2), '\n```\n']
    for r in bad[:80]:
        md.append(f"- {r['symbol']} {r['entry_date']} issues={','.join(r['issues'])}\n")
    OUT_MD.write_text(''.join(md))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
