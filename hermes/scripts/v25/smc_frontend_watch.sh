#!/usr/bin/env bash
set -euo pipefail
PORT=8890
LOG="/root/.hermes/logs/smc_frontend_watch.log"

# systemd exclusively owns the dashboard process. This cron job is an audit only:
# it must never kill or launch a competing process on port 8890.
service_state=$(systemctl is-active smc-frontend-8890.service 2>/dev/null || true)
if curl -fsS --max-time 3 "http://127.0.0.1:$PORT/api/summary" >/dev/null 2>&1; then
    printf '%s HEALTHY service=%s\n' "$(date '+%F %T')" "${service_state:-unknown}" >> "$LOG"
else
    printf '%s UNHEALTHY service=%s (systemd restart policy owns recovery)\n' "$(date '+%F %T')" "${service_state:-unknown}" >> "$LOG"
fi
