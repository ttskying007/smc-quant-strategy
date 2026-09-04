#!/bin/bash
"""
SMC V8.4 自动循环启动器
=======================
新一代架构 (与V8.3对比):
  1. 每轮300次迭代 (V8.3: 250)
  2. 40只股票覆盖 (V8.3: 30)
  3. 动态收紧35% (V8.3: 15%)
  4. 多阶段自动参数空间压缩
  5. Proxy Guardian V7集成
  6. 里程碑: WR>75%+RR>1.5+N>20 或 WR>80%+RR>1.2+N>25
  7. 自适应收敛: 连续3轮WR不提升 → 重置搜索空间
  
目标: WR>80%, RR>=1.5, PF>5, N>25, 覆盖>40%
"""

LOG_DIR="$HOME/.hermes/smc_opt_v83"
SCRIPT_DIR="$HOME/.hermes/scripts"
LOOP_LOG="$LOG_DIR/loop.log"
BEST_FILE="$LOG_DIR/best_params.json"
MILESTONE_FILE="$LOG_DIR/milestones.json"
CYCLE_NUM=0

mkdir -p "$LOG_DIR"

echo "╔═══════════════════════════════════════════════════════╗"
echo "║   SMC V8.4 自动循环启动器                              ║"
echo "║   目标: WR>80% + RR>1.5 + N>25 + PF>5                 ║"
echo "║   每轮300次迭代，40只股票                               ║"
echo "║   六阶段搜索(随机→SA→精英→岛屿→爬山→收敛)              ║"
echo "║   Proxy Guardian V7 集成                               ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""

# 里程碑
echo '{"milestones":[]}' > "$MILESTONE_FILE"

# 信号文件 (让Guardian通知)
SIGNAL_FILE="$LOG_DIR/guardian_signal"

# 检查Proxy Guardian
check_guardian() {
  if pgrep -f "proxy_guardian_v7.py" >/dev/null 2>&1; then
    echo "  ✓ Proxy Guardian V7 运行中"
    return 0
  fi
  echo "  ⚠ Proxy Guardian V7 未运行，尝试启动..."
  if [ -f "$SCRIPT_DIR/proxy_guardian_v7.py" ]; then
    cd "$SCRIPT_DIR" && python3 proxy_guardian_v7.py >/dev/null 2>&1 &
    echo "  ✓ Proxy Guardian V7 已启动"
    sleep 2
  fi
}

# 检查WebUI
check_webui() {
  if curl -s http://127.0.0.1:8879/api/health >/dev/null 2>&1; then
    return 0
  fi
  echo "  ⚠ WebUI API 不可用，重启..."
  pkill -f "smc_web_status_api_v83" 2>/dev/null
  sleep 1
  cd "$SCRIPT_DIR" && python3 smc_web_status_api_v83.py --port 8879 >/dev/null 2>&1 &
  sleep 3
  if curl -s http://127.0.0.1:8879/api/health >/dev/null 2>&1; then
    echo "  ✓ WebUI API 已恢复"
  fi
}

# Proxy检测 (简化版)
check_proxy_simple() {
  pgrep -f mihomo >/dev/null 2>&1 || return 1
  curl -s -o /dev/null -w '%{http_code}' --proxy 127.0.0.1:7890 --max-time 3 \
    http://www.gstatic.com/generate_204 2>/dev/null | grep -q '204' || return 1
  return 0
}

# 清理缓存
clean_cache() {
  find "$HOME/.hermes/kline_cache" -name "*.json" -mtime +7 -delete 2>/dev/null
}

# 主循环
NO_IMPROVEMENT=0
PREV_WR=0

while true; do
  CYCLE_NUM=$((CYCLE_NUM + 1))
  CYCLE_DIR="$LOG_DIR/cycle_$(printf '%03d' $CYCLE_NUM)"
  mkdir -p "$CYCLE_DIR"

  echo ""
  echo "═══════════════════════════════════════════════════════"
  echo "  循环 #${CYCLE_NUM}  开始: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "═══════════════════════════════════════════════════════"

  # --- 基础设施 ---
  check_guardian
  check_webui

  # --- Proxy检查 ---
  if check_proxy_simple; then
    echo "  ✓ 代理正常"
  else
    echo "  ⚠ 代理异常，等待Guardian自愈..."
    sleep 15
    if check_proxy_simple; then
      echo "  ✓ 代理已恢复"
    else
      echo "  ⚠ 代理仍未恢复，继续运行（引擎使用内网Hubble API，不需代理）"
    fi
  fi

  # --- 动态参数 ---
  SEED_ARGS=""
  TIGHTEN_ARGS=""
  STOCKS="40"
  ITERS="300"

  if [ -f "$BEST_FILE" ]; then
    LAST_SCORE=$(python3 -c "import json; d=json.load(open('$BEST_FILE')); print(d.get('score',0))" 2>/dev/null)
    LAST_WR=$(python3 -c "import json; d=json.load(open('$BEST_FILE')); print(d.get('full_eval',{}).get('wr',0))" 2>/dev/null)
    LAST_RR=$(python3 -c "import json; d=json.load(open('$BEST_FILE')); print(d.get('full_eval',{}).get('rr_avg',0))" 2>/dev/null)
    LAST_N=$(python3 -c "import json; d=json.load(open('$BEST_FILE')); print(d.get('full_eval',{}).get('n',0))" 2>/dev/null)
    LAST_PF=$(python3 -c "import json; d=json.load(open('$BEST_FILE')); print(d.get('full_eval',{}).get('pf',0))" 2>/dev/null)
    echo "  📊 上一轮: Score=$LAST_SCORE WR=$LAST_WR% N=$LAST_N RR=$LAST_RR PF=$LAST_PF"
    
    SEED_ARGS="--seed $BEST_FILE"

    # 动态收紧幅度
    if (( $(echo "$LAST_WR < 60" | bc -l) )); then
      # WR低 → 宽松探索
      TIGHTEN_PCT=0.25
    elif (( $(echo "$LAST_WR < 70" | bc -l) )); then
      TIGHTEN_PCT=0.30
    else
      TIGHTEN_PCT=0.35
    fi
    TIGHTEN_ARGS="--tighten $TIGHTEN_PCT"
    echo "  🔧 动态收紧: $TIGHTEN_PCT (WR=$LAST_WR%)"
    
    # 检测WR是否提升
    if (( $(echo "$LAST_WR > $PREV_WR" | bc -l) )); then
      NO_IMPROVEMENT=0
    else
      NO_IMPROVEMENT=$((NO_IMPROVEMENT + 1))
    fi
    PREV_WR=$LAST_WR
    
    # 连续3轮无进展 → 重置参数空间
    if [ $NO_IMPROVEMENT -ge 3 ]; then
      echo "  ⚠ 连续3轮WR未提升，重置参数空间 (宽松搜索)"
      TIGHTEN_PCT=0.1
      TIGHTEN_ARGS="--tighten 0.1"
      NO_IMPROVEMENT=0
    fi
  else
    echo "  📊 第一轮，使用默认参数"
  fi

  # --- 启动优化 ---
  echo ""
  echo "  启动 ${ITERS}次迭代 × ${STOCKS}只股票..."
  START_TIME=$(date +%s)

  cd "$SCRIPT_DIR" && python3 smc_optimizer_v84.py $ITERS $STOCKS $SEED_ARGS $TIGHTEN_ARGS 2>&1

  EXIT_CODE=$?
  END_TIME=$(date +%s)
  DURATION=$((END_TIME - START_TIME))

  echo ""
  echo "  本轮耗时: $DURATION 秒 ($(echo "scale=1; $DURATION/60" | bc) 分钟)"
  echo "  退出码: $EXIT_CODE"

  # --- 保存周期结果 ---
  cp "$LOG_DIR/best_params.json" "$CYCLE_DIR/" 2>/dev/null
  cp "$LOG_DIR/history.json" "$CYCLE_DIR/" 2>/dev/null
  cp "$LOG_DIR/live_status.json" "$CYCLE_DIR/" 2>/dev/null

  # --- 里程碑 ---
  if [ -f "$BEST_FILE" ]; then
    python3 -c "
import json, os
d = json.load(open('$BEST_FILE'))
fe = d.get('full_eval', {})
wr = fe.get('wr', 0)
rr = fe.get('rr_avg', 0)
n = fe.get('n', 0)
pf = fe.get('pf', 0)
score = d.get('score', 0)
print(f'  🏆 Score={score:.1f} WR={wr:.1f}% N={n} PF={pf:.2f} RR={rr:.2f}')

# 里程碑判定
is_milestone = False
if wr >= 75 and rr >= 1.5 and n >= 20:
    is_milestone = True
elif wr >= 80 and rr >= 1.2 and n >= 25:
    is_milestone = True
elif wr >= 70 and rr >= 2.0 and n >= 15:
    is_milestone = True
elif pf >= 5 and wr >= 60 and n >= 20:
    is_milestone = True

if is_milestone:
    m = json.load(open('$MILESTONE_FILE'))
    m['milestones'].append({
        'cycle': $CYCLE_NUM, 'score': score,
        'wr': wr, 'n': n, 'rr': rr, 'pf': pf,
        'time': str(int(time.time()))
    })
    json.dump(m, open('$MILESTONE_FILE', 'w'))
    print('  📌 里程碑已记录!')
" 2>/dev/null
  fi

  # --- 前后端同步 ---
  if [ -f "$LOG_DIR/live_status.json" ]; then
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
  echo "  下一轮将在5秒后自动开始..."
  echo ""
  sleep 5
done