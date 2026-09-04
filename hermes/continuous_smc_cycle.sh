#!/usr/bin/env bash
# SMC Continuous Development Cycle
# Runs: 1) strategy/indicator generation, 2) backtests, 3) signals, 4) saves reports
# Logs to /root/.hermes/logs/core_dev.log
# Run until manually stopped

set -o pipefail

ENGINE_DIR="/root/.hermes/skills/trading"
ENGINE_SCRIPT="${ENGINE_DIR}/smc_core_engine.py"
LOG_FILE="/root/.hermes/logs/core_dev.log"
REPORT_DIR="/root/.hermes/reports"
PID_FILE="/root/.hermes/logs/core_dev.pid"

echo $$ > "$PID_FILE"

exec >> "$LOG_FILE" 2>&1

echo ""
echo "============================================================"
echo " SMC Continuous Development Cycle - STARTED"
echo " PID: $$"
echo " Date: $(date -u '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"
echo ""

CYCLE_COUNT=0

while true; do

    CYCLE_COUNT=$((CYCLE_COUNT + 1))
    CYCLE_TIME=$(date -u '+%Y-%m-%d %H:%M:%S')
    CYCLE_DIR="${REPORT_DIR}/cycle_$(date -u '+%Y%m%d_%H%M%S')"
    mkdir -p "$CYCLE_DIR"

    echo "============================================================"
    echo " CYCLE #${CYCLE_COUNT} - ${CYCLE_TIME}"
    echo "============================================================"

    echo ""
    echo "--- PHASE 1: Running SMC Core Engine ---"
    cd "$ENGINE_DIR"
    python3 "$ENGINE_SCRIPT" 2>&1
    ENGINE_EXIT=$?
    echo "Engine exit code: ${ENGINE_EXIT}"

    if [ -f "${ENGINE_DIR}/logs/core_engine.log" ]; then
        cp "${ENGINE_DIR}/logs/core_engine.log" "${CYCLE_DIR}/engine_run.log"
    fi

    echo ""
    echo "--- PHASE 2: Collecting generated reports ---"

    if [ -f "${ENGINE_DIR}/library/strategy_library.json" ]; then
        cp "${ENGINE_DIR}/library/strategy_library.json" "${CYCLE_DIR}/strategy_library.json"
        cp "${ENGINE_DIR}/library/strategy_library.json" "${REPORT_DIR}/strategy_library_latest.json"
        echo "Copied strategy library"
    fi

    if [ -d "${ENGINE_DIR}/backtest" ]; then
        mkdir -p "${CYCLE_DIR}/backtests"
        cp "${ENGINE_DIR}/backtest/"*.json "${CYCLE_DIR}/backtests/" 2>/dev/null
        if [ -f "${ENGINE_DIR}/backtest/backtest_summary.json" ]; then
            cp "${ENGINE_DIR}/backtest/backtest_summary.json" "${REPORT_DIR}/backtest_summary_latest.json"
            echo "Copied backtest summary"
        fi
    fi

    if [ -d "${ENGINE_DIR}/reports" ]; then
        mkdir -p "${CYCLE_DIR}/signals"
        cp "${ENGINE_DIR}/reports/"*.json "${CYCLE_DIR}/signals/" 2>/dev/null
        cp "${ENGINE_DIR}/reports/"*.json "${REPORT_DIR}/" 2>/dev/null
        echo "Copied signal reports"
    fi

    echo ""
    echo "--- PHASE 3: Generating cycle summary ---"

    cat > "${CYCLE_DIR}/cycle_summary.json" << JSONEOF
{
    "cycle": ${CYCLE_COUNT},
    "timestamp": "$(date -u -Iseconds)",
    "engine_exit_code": ${ENGINE_EXIT},
    "phases": {
        "engine_run": ${ENGINE_EXIT},
        "report_collection": 0
    }
}
JSONEOF

    ln -sf "$CYCLE_DIR" "${REPORT_DIR}/latest_cycle" 2>/dev/null
    cp "${CYCLE_DIR}/cycle_summary.json" "${REPORT_DIR}/latest_cycle_summary.json"

    echo ""
    echo "--- CYCLE #${CYCLE_COUNT} COMPLETE ---"
    echo "Reports saved to: ${CYCLE_DIR}"

    echo ""
    echo "Waiting 30s before next cycle..."
    sleep 30

done
