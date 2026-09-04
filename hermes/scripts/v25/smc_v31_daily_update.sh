#!/usr/bin/env bash
set -euo pipefail
LOG_DIR="/root/.hermes/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/smc_v31_daily_$(date +%Y%m%d).log"
{
  echo "==== $(date '+%F %T') SMC V31 daily update start ===="
  cd /root/.hermes/scripts/v25
  python3 download_750.py
  python3 v31_full_scan.py --start 20260101 --end "$(date +%Y%m%d)"
  python3 v31_audit.py || true
  echo "==== $(date '+%F %T') SMC V31 daily update done ===="
} >> "$LOG" 2>&1
