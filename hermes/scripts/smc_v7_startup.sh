#!/bin/bash
# SMC V7 Full System Startup Script
# 启动: Status API, Proxy Guardian, V7 Optimizer, Web Server
set -e

SCRIPT_DIR="/root/.hermes/scripts"
LOG_DIR="/root/.hermes/logs"
OPT_DIR="/root/.hermes/smc_opt_v7"

mkdir -p "$LOG_DIR" "$OPT_DIR"

echo "========================================"
echo " SMC V7 Full System Startup"
echo " $(date)"
echo "========================================"

# 1. Kill previous instances
echo "[1/5] Cleaning up previous instances..."
kill $(lsof -ti:8877 2>/dev/null) 2>/dev/null || true
kill $(lsof -ti:8878 2>/dev/null) 2>/dev/null || true
pkill -f "smc_proxy_guardian_v5" 2>/dev/null || true
pkill -f "smc_web_status_api" 2>/dev/null || true
pkill -f "smc_web_server_v3" 2>/dev/null || true
sleep 2

# 2. Start Proxy Guardian V5
echo "[2/5] Starting Proxy Guardian V5..."
nohup python3 "$SCRIPT_DIR/smc_proxy_guardian_v5.py" > /tmp/smc_proxy_guardian.log 2>&1 &
PG_PID=$!
echo "  PID: $PG_PID"
sleep 3

# 3. Start Status API (port 8878)
echo "[3/5] Starting Status API (port 8878)..."
nohup python3 "$SCRIPT_DIR/smc_web_status_api.py" > /tmp/smc_status_api.log 2>&1 &
API_PID=$!
echo "  PID: $API_PID"
sleep 2

# 4. Start Web Server (port 8877)
echo "[4/5] Starting Web Server (port 8877)..."
nohup python3 "$SCRIPT_DIR/smc_web_server_v3.py" --port 8877 --api-port 8878 > /tmp/smc_web_server.log 2>&1 &
WEB_PID=$!
echo "  PID: $WEB_PID"
sleep 2

# 5. Verify all services
echo "[5/5] Verifying services..."
echo "  WebUI:    $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8877/index.html)"
echo "  API:      $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8878/api/health)"
echo "  Proxy:    $(curl -s http://127.0.0.1:8878/api/v7/proxy | python3 -c \"import sys,json; d=json.load(sys.stdin); print('OK' if d.get('running') else 'down')\")"
echo "  V7 status:$(curl -s http://127.0.0.1:8878/api/v7/progress | python3 -c \"import sys,json; d=json.load(sys.stdin); print(f\"gen={d['current_iter']}/{d['total_iters']}\")\")"

echo ""
echo "✅ All services running!"
echo "  WebUI: http://localhost:8877"
echo "  API:   http://localhost:8878/api/status"
echo ""
echo "To run V7 optimizer (separate):"
echo "  cd $SCRIPT_DIR && python3 smc_engine_v7.py --iters 300 --pop-size 24 --stocks 100"
echo "========================================"