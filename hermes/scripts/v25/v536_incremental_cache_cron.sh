#!/usr/bin/env bash
# One bounded, restart-safe V536 raw-cache increment. Safe for cron.
# Per-symbol isolation: one hang cannot block the rest of the run.
set -u -o pipefail

ROOT=/root/.hermes
V25="$ROOT/scripts/v25"
MON="$ROOT/smc_monitor"
LOG="$MON/v536_incremental_cache_cron.log"
LOCK="$MON/v536_incremental_cache_cron.lock"
mkdir -p "$MON"

# Outer lock prevents cron overlap.  Inner accelerator processes up to 10
# symbols one-by-one with a 75s hard timeout each inside a 300s window.
/usr/bin/flock -n "$LOCK" /usr/bin/timeout 340 \
  /usr/bin/python3 "$V25/v536_four_hour_randomized_accelerator.py" \
  --window-sec 300 \
  --max-batches 10 \
  --batch-min 1 \
  --batch-max 1 \
  --per-batch-timeout-sec 75 \
  >> "$LOG" 2>&1
rc=$?
state=$(/usr/bin/python3 - <<'PY'
import json
from pathlib import Path
p = Path('/root/.hermes/smc_monitor/v536_four_hour_acceleration_latest.json')
try:
    r = json.loads(p.read_text())
    print(r.get('state', 'REPORT_UNAVAILABLE'))
except Exception:
    print('REPORT_UNAVAILABLE')
PY
)
printf '%s rc=%s state=%s\n' "$(date -Is)" "$rc" "$state" >> "$LOG"
if [ "$rc" -eq 0 ] && [ "$state" = "NO_PROGRESS_RETRY_REQUIRED" ]; then
  printf '%s no_progress: inspect hang_counts/quarantine and builder status\n' "$(date -Is)" >> "$LOG"
  exit 75
fi
exit "$rc"
