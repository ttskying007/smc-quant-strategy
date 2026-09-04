#!/usr/bin/env bash
# Safe disk-retention policy for the historical SMC report flood.
# Does not touch V517/V536 data, kline caches, production state, sessions,
# state snapshots, active logs, or smc_audit evidence.
set -euo pipefail

REPORTS=/root/.hermes/reports
find "$REPORTS" -type f -name '*.log' -mtime +30 -delete
find "$REPORTS" -maxdepth 1 -mindepth 1 -type d \( -name 'cycle_20*' \) -mtime +30 -exec rm -rf -- {} +
find "$REPORTS" -mindepth 1 -type d -empty -delete
journalctl --vacuum-size=500M >/dev/null 2>&1 || true
rm -rf /root/.cache/pip/http-v2 /root/.cache/uv/archive-v0 /root/.cache/uv/simple-v21 /root/.cache/pnpm/v11 /root/.npm/_cacache

df -h / | awk 'NR==2 {printf "{\"disk_used\":\"%s\",\"disk_free\":\"%s\",\"disk_use_pct\":\"%s\"}\n", $3,$4,$5}'
