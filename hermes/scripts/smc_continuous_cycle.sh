#!/bin/bash
LOGFILE="/root/.hermes/logs/core_dev.log"
REPORTDIR="/root/.hermes/reports"
WORKDIR="/root/.hermes/skills/trading"
mkdir -p "$REPORTDIR" "$(dirname "$LOGFILE")"
log_msg() { echo "[$(date +%Y-%m-%d\ %H:%M:%S)] $1" | tee -a "$LOGFILE"; }
log_msg "=========================================="
log_msg "SMC Continuous Development Cycle STARTED"
log_msg "=========================================="
cycle_count=0
while true; do
  cycle_count=$((cycle_count+1))
  cycle_ts=$(date +%Y%m%d_%H%M%S)
  log_msg "--- Cycle $cycle_count ($cycle_ts) ---"
  # STEP 1: Generate strategies/indicators
  log_msg "STEP 1: Generate strategies/indicators (smc_core_engine.py)"
  cd "$WORKDIR" && python3 smc_core_engine.py >> "$LOGFILE" 2>&1
  RET1=$?
  log_msg "  smc_core_engine.py exit code: $RET1"
  # STEP 2: Backtest
  if [ -f "$WORKDIR/smc-backtest/scripts/smc_backtest.py" ]; then
    log_msg "STEP 2: Run backtest"
    cd "$WORKDIR/smc-backtest/scripts" && python3 smc_backtest.py >> "$LOGFILE" 2>&1
    RET2=$?
    log_msg "  backtest exit code: $RET2"
  else
    log_msg "STEP 2: Backtest script not found, skipping"
  fi
  # STEP 3: Signal generation
  if [ -f "$WORKDIR/smc-signal-scanner/scripts/smc_scanner.py" ]; then
    log_msg "STEP 3: Generate signals"
    cd "$WORKDIR/smc-signal-scanner/scripts" && python3 smc_scanner.py >> "$LOGFILE" 2>&1
    RET3=$?
    log_msg "  scanner exit code: $RET3"
  else
    log_msg "STEP 3: Scanner script not found, skipping"
  fi
  # STEP 4: Save results snapshot
  log_msg "STEP 4: Save results snapshot"
  cp "$LOGFILE" "$REPORTDIR/core_dev_${cycle_ts}.log" 2>/dev/null || true
  # Find latest signal/strategy files and copy to reports
  ls -t "$WORKDIR"/library/strategy_library.json 2>/dev/null && cp "$WORKDIR"/library/strategy_library.json "$REPORTDIR/strategy_library_${cycle_ts}.json" 2>/dev/null || true
  ls -t "$REPORTDIR"/signals_*.json 2>/dev/null | head -1 | xargs -I{} cp {} "$REPORTDIR/latest_signals_${cycle_ts}.json" 2>/dev/null || true
  log_msg "--- Cycle $cycle_count complete. Sleeping 60s ---"
  sleep 60
done