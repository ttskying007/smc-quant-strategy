#!/bin/bash
# SMC Continuous Development Cycle
# Runs continuously until manually stopped

WORK_DIR="/root/.hermes/skills/trading"
LOG_FILE="/root/.hermes/logs/core_dev.log"
REPORT_DIR="/root/.hermes/reports"
CYCLE_DELAY=300  # 5 minutes between cycles

mkdir -p "$REPORT_DIR"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] ==============================================" >> "$LOG_FILE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] SMC Continuous Development Cycle STARTED" >> "$LOG_FILE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Logging to: $LOG_FILE" >> "$LOG_FILE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Reports to: $REPORT_DIR" >> "$LOG_FILE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] ==============================================" >> "$LOG_FILE"

CYCLE=0
while true; do
    CYCLE=$((CYCLE + 1))
    echo "" >> "$LOG_FILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ======= CYCLE $CYCLE START =======" >> "$LOG_FILE"
    
    # Run SMC Core Engine
    cd "$WORK_DIR"
    python3 smc_core_engine.py >> "$LOG_FILE" 2>&1
    
    # Copy results to reports directory
    cp "$WORK_DIR"/reports/* "$REPORT_DIR/" 2>/dev/null
    cp "$WORK_DIR"/library/* /root/.hermes/skills/trading/backtest/ 2>/dev/null
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ======= CYCLE $CYCLE COMPLETE =======" >> "$LOG_FILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Next cycle in ${CYCLE_DELAY}s" >> "$LOG_FILE"
    
    # Wait before next cycle
    sleep $CYCLE_DELAY
done
