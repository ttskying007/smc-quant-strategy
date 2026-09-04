#!/usr/bin/env bash
set -euo pipefail

# Reproducible closure loop for the current V138→V152 research chain.
# Read-only: does not touch production scanner/API/frontend/watchlist.

ROOT="/root/.hermes"
LOG_DIR="$ROOT/smc_audit/v152_hybrid_lifecycle_gate_backtest_20260622"
mkdir -p "$LOG_DIR"

python3 "$ROOT/scripts/v25/v151_observation_window_sl.py" > "$LOG_DIR/rerun_v151.log" 2>&1
python3 "$ROOT/scripts/v25/v152_hybrid_lifecycle_gate.py" > "$LOG_DIR/rerun_v152.log" 2>&1

python3 - <<'PY'
import json
from pathlib import Path
root = Path('/root/.hermes')
summary_paths = {
    'v151': root/'smc_audit/v151_observation_window_sl_backtest_20260621/summary.json',
    'v152': root/'smc_audit/v152_hybrid_lifecycle_gate_backtest_20260622/summary.json',
}
for name, p in summary_paths.items():
    d = json.loads(p.read_text())
    print(f'[{name}] decision={d.get("decision")}')
    if name == 'v151':
        print('  baseline=', d.get('baseline'))
        print('  best=', d.get('best_variant'), d.get('best_metrics'))
        print('  release=', d.get('release_gate'))
    if name == 'v152':
        print('  baseline=', d.get('baseline_v138'))
        print('  v150=', d.get('v150_best_skip_pbg_be_sl50'))
        print('  best=', d.get('best_variant'), d.get('best_metrics'))
        print('  release=', d.get('release_gate'))
        if not d.get('release_gate', {}).get('pass'):
            raise SystemExit('V152 release gate failed')
print('closure_loop=PASS')
PY
