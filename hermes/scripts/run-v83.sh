#!/bin/bash
"""
SMC V8.3 自动循环启动器
=======================
功能 (与V8.2对比):
  1. 加载上一轮的最佳参数作为种子
  2. 动态收紧参数空间 (每轮缩小15%)
  3. 每轮250次迭代
  4. 里程碑: WR>75%+RR>1.5+N>15 或 WR>70%+RR>2.0+N>12
  5. 自动重启代理守护和状态API
  6. 前后端同步: 写JSON到V82、V7目录
  7. 日志循环检测: 如果连续3轮无改进, 重置参数空间

用法:
  nohup bash run-v83.sh > /root/.hermes/smc_opt_v83/loop.log 2>&1 &
"""

LOG_DIR="$HOME/.hermes/smc_opt_v83"
SCRIPT_DIR="$HOME/.hermes/scripts"
LOOP_LOG="$LOG_DIR/loop.log"
BEST_FILE="$LOG_DIR/best_params.json"
MILESTONE_FILE="$LOG_DIR/milestones.json"
CYCLE_NUM=0

mkdir -p "$LOG_DIR"

echo "╔═══════════════════════════════════════════════════════╗"
echo "║   SMC V8.3 自动循环启动器                              ║"
echo "║   目标: WR>75% + RR>1.5 + N>15 + PF>3                 ║"
echo "║   每轮250次迭代，6阶段搜索                               ║"
echo "║   岛屿模型(3群岛) + 精英保留 + 局部爬山                   ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""

# 初始化里程碑
echo '{"milestones":[]}' > "$MILESTONE_FILE"

# 代理看门狗函数
restart_proxy() {
  echo "  ⚠ 代理异常，尝试重启..."
  pkill -9 -f mihomo 2>/dev/null
  sleep 2
  /usr/local/bin/mihomo -d "$HOME/.clash" -f "$HOME/.clash_config_new.yaml" >/dev/null 2>&1 &
  echo "  等待代理启动..."
  sleep 5
  return $?
}

check_proxy() {
  pgrep -f mihomo >/dev/null 2>&1 || return 1
  curl -s -o /dev/null -w '%{http_code}' --proxy 127.0.0.1:7890 --max-time 3 \
    http://www.gstatic.com/generate_204 2>/dev/null | grep -q '204' || return 1
  return 0
}

# 重启状态API
restart_status_api() {
  pkill -f smc_web_status_api 2>/dev/null
  sleep 1
  if [ -f "$SCRIPT_DIR/smc_web_status_api_v82.py" ]; then
    cd "$SCRIPT_DIR" && python3 smc_web_status_api_v82.py --port 8879 &
    echo "  状态API已启动 (8879)"
  fi
}

# 启动Proxy Guardian
start_guardian() {
  if pgrep -f proxy_guardian_v6 >/dev/null 2>&1; then
    echo "  ✓ Proxy Guardian V6 运行中"
    return 0
  fi
  if [ -f "$SCRIPT_DIR/proxy_guardian_v6.py" ]; then
    cd "$SCRIPT_DIR" && python3 proxy_guardian_v6.py &
    echo "  Proxy Guardian V6 已启动"
    sleep 2
  fi
}

# 清理旧缓存
clean_cache() {
  find "$HOME/.hermes/kline_cache" -name "*.json" -mtime +3 -delete 2>/dev/null
}

# 主循环
while true; do
  CYCLE_NUM=$((CYCLE_NUM + 1))
  CYCLE_DIR="$LOG_DIR/cycle_$(printf '%03d' $CYCLE_NUM)"
  mkdir -p "$CYCLE_DIR"

  echo ""
  echo "═══════════════════════════════════════════════════════"
  echo "  循环 #${CYCLE_NUM}  开始: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "═══════════════════════════════════════════════════════"

  # --- 代理检查 + 重启 ---
  if check_proxy; then
    echo "  ✓ 代理正常"
  else
    restart_proxy
    sleep 3
    if check_proxy; then
      echo "  ✓ 代理已恢复"
    else
      echo "  ✗ 代理无法恢复，等待30秒后再试..."
      sleep 30
      continue
    fi
  fi

  # --- WebUI状态API ---
  if curl -s http://127.0.0.1:8879/api/health >/dev/null 2>&1; then
    echo "  ✓ WebUI API (8879) 运行中"
  else
    echo "  ⚠ WebUI API 不可用，重启..."
    restart_status_api
    sleep 2
    if curl -s http://127.0.0.1:8879/api/health >/dev/null 2>&1; then
      echo "  ✓ WebUI API 已恢复"
    fi
  fi

  # --- Proxy Guardian ---
  start_guardian

  # --- 从上一轮最佳加载种子 ---
  SEED_ARGS=""
  TIGHTEN_ARGS=""
  if [ -f "$BEST_FILE" ]; then
    LAST_SCORE=$(python3 -c "import json; d=json.load(open('$BEST_FILE')); print(d.get('score',0))" 2>/dev/null)
    LAST_WR=$(python3 -c "import json; d=json.load(open('$BEST_FILE')); print(d.get('full_eval',{}).get('wr',0))" 2>/dev/null)
    LAST_RR=$(python3 -c "import json; d=json.load(open('$BEST_FILE')); print(d.get('full_eval',{}).get('rr_avg',0))" 2>/dev/null)
    LAST_N=$(python3 -c "import json; d=json.load(open('$BEST_FILE')); print(d.get('full_eval',{}).get('n',0))" 2>/dev/null)
    echo "  📊 上一轮: Score=$LAST_SCORE WR=$LAST_WR% N=$LAST_N RR=$LAST_RR"

    SEED_ARGS="--seed $BEST_FILE"
  else
    echo "  📊 第一轮，使用默认参数"
  fi

  # --- 动态收紧 (每轮缩小) ---
  if [ $CYCLE_NUM -gt 1 ] && [ -f "$BEST_FILE" ]; then
    TIGHTEN_PCT=$(python3 -c "
pct = 0.5 - (($CYCLE_NUM - 1) * 0.03)
print(max(0.1, min(0.5, pct)))
" 2>/dev/null)
    TIGHTEN_ARGS="--tighten $TIGHTEN_PCT"
    echo "  🔧 动态收紧: $TIGHTEN_PCT (cycle $CYCLE_NUM)"
  fi

  # --- 启动 V8.3 优化器 ---
  echo ""
  echo "  启动 250轮 优化 (30只股票)..."
  START_TIME=$(date +%s)

  cd "$SCRIPT_DIR" && python3 smc_optimizer_v83.py 250 30 $SEED_ARGS $TIGHTEN_ARGS 2>&1

  EXIT_CODE=$?
  END_TIME=$(date +%s)
  DURATION=$((END_TIME - START_TIME))

  echo ""
  echo "  本轮耗时: $DURATION 秒 ($(echo "scale=1; $DURATION/60" | bc) 分钟)"
  echo "  退出码: $EXIT_CODE"

  # --- 复制结果 ---
  cp "$LOG_DIR/best_params.json" "$CYCLE_DIR/" 2>/dev/null
  cp "$LOG_DIR/history.json" "$CYCLE_DIR/" 2>/dev/null
  cp "$LOG_DIR/live_status.json" "$CYCLE_DIR/" 2>/dev/null

  # --- 记录里程碑 ---
  if [ -f "$BEST_FILE" ]; then
    BEST_RESULT=$(python3 -c "
import json
d = json.load(open('$BEST_FILE'))
fe = d.get('full_eval', {})
print(f'Score={d.get(\"score\",0):.1f} WR={fe.get(\"wr\",0):.1f}% N={fe.get(\"n\",0)} PF={fe.get(\"pf\",0):.2f} RR={fe.get(\"rr_avg\",0):.2f} Ret={fe.get(\"ret\",0):.2f}%')
" 2>/dev/null)
    echo "  🏆 本轮最佳: $BEST_RESULT"

    # 里程碑写入
    python3 -c "
import json
d = json.load(open('$BEST_FILE'))
fe = d.get('full_eval', {})
m = json.load(open('$MILESTONE_FILE'))
wr = fe.get('wr', 0)
rr = fe.get('rr_avg', 0)
n = fe.get('n', 0)
score = d.get('score', 0)

is_milestone = False
if wr >= 75 and rr >= 1.5 and n >= 15:
    is_milestone = True
elif wr >= 70 and rr >= 2.0 and n >= 12:
    is_milestone = True
elif wr >= 80 and rr >= 1.2 and n >= 20:
    is_milestone = True

if is_milestone:
    import time
    m['milestones'].append({
        'cycle': $CYCLE_NUM, 'score': score,
        'wr': wr, 'n': n, 'rr': rr,
        'time': str(int(time.time()))
    })
    json.dump(m, open('$MILESTONE_FILE', 'w'))
    print('  📌 里程碑已记录!')
else:
    print('  - 未达标')
" 2>/dev/null

    # --- 前后端同步: 复制状态到V7/V82目录 ---
    cp "$LOG_DIR/live_status.json" "$LOG_DIR/../smc_opt_v7/v7_live_status.json" 2>/dev/null
    if [ -d "$LOG_DIR/../smc_opt_v82" ]; then
      cp "$LOG_DIR/live_status.json" "$LOG_DIR/../smc_opt_v82/live_status.json" 2>/dev/null
      cp "$BEST_FILE" "$LOG_DIR/../smc_opt_v82/best_params_v83.json" 2>/dev/null
    fi
    echo "  🔄 前端状态已同步"
  fi

  # --- 清理 ---
  clean_cache

  # --- 完成 ---
  echo ""
  echo "  ✓ 循环 #${CYCLE_NUM} 完成"
  echo "  下一轮将在10秒后自动开始..."
  echo ""
  sleep 10
done