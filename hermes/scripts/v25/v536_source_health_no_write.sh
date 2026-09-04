#!/usr/bin/env bash
# V536 no-write provider health monitor. It MUST NOT materialize signals,
# candidates, pending orders, positions, or production registry mutations.
set -euo pipefail
ROOT=/root/.hermes
PY="$ROOT/venvs/smc-source-monitor/bin/python"
SCRIPT="$ROOT/scripts/v25/v536_multitf_source_monitor.py"
LOG="$ROOT/smc_monitor/v536_source_health.log"
mkdir -p "$(dirname "$LOG")"
exec "$PY" "$SCRIPT" >> "$LOG" 2>&1
