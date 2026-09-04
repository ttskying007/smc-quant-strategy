#!/bin/bash
# SMC Auto-runner - Runs continuously until manually stopped
# This script runs every cycle and logs everything

BASE_DIR="/root/.hermes"
LOG_DIR="$BASE_DIR/logs"
SCRIPT_DIR="$BASE_DIR/skills/trading"
REPORT_DIR="$BASE_DIR/reports"
BACKTEST_DIR="$BASE_DIR/backtest"

mkdir -p "$LOG_DIR" "$REPORT_DIR" "$BACKTEST_DIR"

# Prevent duplicate execution
LOCKFILE="/tmp/smc_autorun.lock"
if [ -f "$LOCKFILE" ]; then
    PID=$(cat "$LOCKFILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "[$(date)] Another instance is running (PID: $PID). Exiting."
        exit 1
    fi
fi
echo $$ > "$LOCKFILE"

CYCLE=0
MAX_CYCLES=100  # Safety limit

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_DIR/autorun.log"
}

log "=== SMC Auto-runner Started (PID: $$) ==="

while [ $CYCLE -lt $MAX_CYCLES ]; do
    CYCLE=$((CYCLE + 1))
    log "=== Cycle $CYCLE/$MAX_CYCLES ==="
    
    # Phase 1: Core Engine
    log "Phase 1: Core Engine"
    python3 "$SCRIPT_DIR/smc_core_engine.py" >> "$LOG_DIR/core_engine.log" 2>&1
    
    if [ $? -ne 0 ]; then
        log "ERROR: Core engine failed, retrying..."
        sleep 30
        continue
    fi
    
    sleep 3
    
    # Phase 2: Generate Frontend
    log "Phase 2: Generating Dashboard"
    
    python3 << 'PYEOF'
import json, random, os
from datetime import datetime
from pathlib import Path

BASE = Path("/root/.hermes")
LIB = BASE / "skills/trading/library"
REP = BASE / "reports"
BACK = BASE / "backtest"

# Load data
data = {"strategies": [], "signals": [], "backtest": {}}
lf = LIB / "strategy_library.json"
if lf.exists():
    with open(lf, "r") as f:
        lib = json.load(f)
        data["strategies"] = list(lib.get("strategies", {}).values())[-10:]

sf = sorted(REP.glob("signals_*.json"), reverse=True)
if sf and len(sf) > 0:
    with open(sf[0], "r") as f:
        signals = json.load(f)
        data["signals"] = signals[:30]

bsf = BACK / "backtest_summary.json"
if bsf.exists():
    with open(bsf, "r") as f:
        data["backtest"] = json.load(f)

# Generate HTML
ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
st = "".join(f"<tr><td><code>{s['id']}</code></td><td>{s['name']}</td><td>{s.get('type','')}</td><td>{s.get('parameters',{}).get('rr_min','')}</td><td>{s.get('status','')}</td></tr>" for s in data["strategies"])
sig = "".join(f"<tr><td><code>{s['symbol']}</code></td><td>{s['signal_type']}</td><td><b>{s['direction']}</b></td><td>{s['price']}</td><td>{s['sl']}</td><td>{s['tp']}</td><td><b>{s['rr']}x</b></td></tr>" for s in data["signals"])
bt = data.get("backtest",{})

html = f"""<!DOCTYPE html><html><head><meta charset=utf-8><meta http-equiv=refresh content=60><title>SMC Live Dashboard</title></head><body>
<div style="font-family:Arial,sans-serif;margin:20px;background:#f5f5f5;padding:20px;border-radius:10px;">
<h1 style="color:#333;">\U0001f680 SMC Strategy Dashboard</h1><p>Auto-updated: {ts}</p>
<div style="display:flex;flex-wrap:wrap;gap:20px;">
<div style="background:linear-gradient(135deg,#667eea,#764ba2);color:white;padding:20px;border-radius:10px;text-align:center;flex:1;min-width:150px;">
<h2 style="margin:0;font-size:36px;">{len(data['strategies'])}</h2><p style="margin:5px 0;">Strategies</p></div>
<div style="background:linear-gradient(135deg,#20c997,#17a2b8);color:white;padding:20px;border-radius:10px;text-align:center;flex:1;min-width:150px;">
<h2 style="margin:0;font-size:36px;">{bt.get('avg_win_rate',0):.0%}</h2><p style="margin:5px 0;">Win Rate</p></div>
<div style="background:linear-gradient(135deg,#fd7e14,#e83e8c);color:white;padding:20px;border-radius:10px;text-align:center;flex:1;min-width:150px;">
<h2 style="margin:0;font-size:36px;">{bt.get('avg_profit_factor',0):.2f}x</h2><p style="margin:5px 0;">Profit Factor</p></div>
<div style="background:linear-gradient(135deg,#6f42c1,#007bff);color:white;padding:20px;border-radius:10px;text-align:center;flex:1;min-width:150px;">
<h2 style="margin:0;font-size:36px;">{len(data['signals'])}</h2><p style="margin:5px 0;">Signals</p></div></div>
</div>
<div style="font-family:Arial,sans-serif;margin:20px;background:white;padding:20px;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,0.1);">
<h2>\U0001f4ca Recent Strategies</h2><table style="width:100%;border-collapse:collapse;"><tr style="background:#667eea;color:white;"><th style="padding:8px;">ID</th><th style="padding:8px;">Name</th><th style="padding:8px;">Type</th><th style="padding:8px;">RR Min</th><th style="padding:8px;">Status</th></tr>{st or '<tr><td colspan=5 style="text-align:center;padding:20px;">No data</td></tr>'}</table></div>
<div style="font-family:Arial,sans-serif;margin:20px;background:white;padding:20px;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,0.1);">
<h2>\U0001f4c8 Live Signals</h2><table style="width:100%;border-collapse:collapse;"><tr style="background:#667eea;color:white;"><th style="padding:8px;">Symbol</th><th style="padding:8px;">Signal</th><th style="padding:8px;">Dir</th><th style="padding:8px;">Price</th><th style="padding:8px;">SL</th><th style="padding:8px;">TP</th><th style="padding:8px;">RR</th></tr>{sig or '<tr><td colspan=7 style="text-align:center;padding:20px;">No signals</td></tr>'}</table></div>
</body></html>"""

with open(REP / "dashboard.html","w") as f:
    f.write(html)
PYEOF
    
    sleep 3
    
    # Check if we should continue
    if [ $CYCLE -ge $MAX_CYCLES ]; then
        log "Max cycles reached, stopping"
        break
    fi
    
    log "Cycle $CYCLE complete, waiting 30s..."
    sleep 30
done

log "=== SMC Auto-runner Stopped ==="
rm -f "$LOCKFILE"
