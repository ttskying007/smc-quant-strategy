#!/bin/bash
"""
SMC V8.2 自动循环启动器
=======================
功能：
  1. 加载上一轮的最佳参数作为种子
  2. 动态调整参数空间范围（缩窄到最佳参数附近）
  3. 每轮200次迭代
  4. 每轮完成后自动重启下一轮（无限制循环）
  5. 保存每次循环的结果到循环日志
  6. 如果发现WR>85%+RR>2.0+N>20→记录为里程碑

用法：
  nohup bash run-v82.sh > /root/.hermes/smc_opt_v82/loop.log 2>&1 &
"""

LOG_DIR="$HOME/.hermes/smc_opt_v82"
SCRIPT_DIR="$HOME/.hermes/scripts"
LOOP_LOG="$LOG_DIR/loop.log"
BEST_FILE="$LOG_DIR/best_params.json"
MILESTONE_FILE="$LOG_DIR/milestones.json"
CYCLE_NUM=0

mkdir -p "$LOG_DIR"

echo "╔═══════════════════════════════════════════════╗"
echo "║   SMC V8.2 自动循环启动器                      ║"
echo "║   目标: WR>80% + RR>2.0 + N>20                 ║"
echo "║   每轮200次迭代，自动重启动                       ║"
echo "╚═══════════════════════════════════════════════╝"
echo ""

# 初始化里程碑文件
echo '{"milestones":[]}' > "$MILESTONE_FILE"

while true; do
  CYCLE_NUM=$((CYCLE_NUM + 1))
  CYCLE_DIR="$LOG_DIR/cycle_$(printf '%03d' $CYCLE_NUM)"
  mkdir -p "$CYCLE_DIR"
  
  echo ""
  echo "══════════════════════════════════════════════"
  echo "  循环 #${CYCLE_NUM}  开始: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "══════════════════════════════════════════════"
  
  # 检查代理状态
  PROXY_OK=$(pgrep -f mihomo >/dev/null 2>&1 && curl -s -o /dev/null -w '%{http_code}' --proxy 127.0.0.1:7890 --max-time 3 http://www.gstatic.com/generate_204 2>/dev/null || echo "000")
  if [ "$PROXY_OK" != "204" ]; then
    echo "  ⚠ 代理异常，尝试重启..."
    pkill -9 -f mihomo 2>/dev/null
    sleep 2
    /usr/local/bin/mihomo -d "$HOME/.clash" -f "$HOME/.clash_config_new.yaml" >/dev/null 2>&1 &
    echo "  等待代理启动..."
    sleep 5
  else
    echo "  ✓ 代理正常"
  fi
  
  # 检查WebUI API是否运行
  if curl -s http://127.0.0.1:8879/api/health >/dev/null 2>&1; then
    echo "  ✓ WebUI API (8879) 运行中"
  else
    echo "  ⚠ WebUI API (8879) 不可用，尝试启动..."
    cd "$SCRIPT_DIR" && python3 smc_web_status_api_v82.py --port 8879 &
    sleep 2
  fi
  
  # 检查Proxy Guardian
  if pgrep -f smc_proxy_guardian_v5 >/dev/null 2>&1; then
    echo "  ✓ Proxy Guardian 运行中"
  else
    echo "  ⚠ Proxy Guardian 不可用，启动..."
    cd "$SCRIPT_DIR" && python3 smc_proxy_guardian_v5.py &
    sleep 3
  fi
  
  # 检查是否有上一轮的最佳参数作为种子
  SEED_ARGS=""
  if [ -f "$BEST_FILE" ]; then
    LAST_SCORE=$(python3 -c "import json; d=json.load(open('$BEST_FILE')); print(d.get('score',0))" 2>/dev/null)
    LAST_WR=$(python3 -c "import json; d=json.load(open('$BEST_FILE')); print(d.get('full_eval',{}).get('wr',0))" 2>/dev/null)
    LAST_RR=$(python3 -c "import json; d=json.load(open('$BEST_FILE')); print(d.get('full_eval',{}).get('rr_avg',0))" 2>/dev/null)
    LAST_N=$(python3 -c "import json; d=json.load(open('$BEST_FILE')); print(d.get('full_eval',{}).get('n',0))" 2>/dev/null)
    echo "  📊 上一轮: Score=$LAST_SCORE WR=$LAST_WR% N=$LAST_N RR=$LAST_RR"
    
    # 检查是否是里程碑
    if python3 -c "import json; d=json.load(open('$MILESTONE_FILE')); d['milestones'].append({'cycle':$CYCLE_NUM,'score':$LAST_SCORE,'wr':$LAST_WR,'n':$LAST_N,'rr':$LAST_RR,'time':'$(date +%s)'}); json.dump(d,open('$MILESTONE_FILE','w'))" 2>/dev/null; then
      echo "  📌 里程碑已记录"
    fi
    
    SEED_ARGS="--seed $BEST_FILE"
  else
    echo "  📊 第一轮，使用默认参数"
  fi
  
  # 动态调整参数空间（每5轮收紧一次）
  DYNAMIC_ARGS=""
  if [ $CYCLE_NUM -gt 1 ] && [ -f "$BEST_FILE" ]; then
    # 在最佳参数附近50%范围内搜索
    DYNAMIC_ARGS="--tighten 0.5"
  fi
  
  # ═══════ 启动 V8.2 优化器 ═══════
  echo ""
  echo "  启动 200轮 优化..."
  START_TIME=$(date +%s)
  
  cd "$SCRIPT_DIR" && python3 smc_optimizer_v82.py 200 15 $SEED_ARGS $DYNAMIC_ARGS 2>&1
  
  EXIT_CODE=$?
  END_TIME=$(date +%s)
  DURATION=$((END_TIME - START_TIME))
  
  echo ""
  echo "  本轮耗时: $DURATION 秒 ($(echo "scale=1; $DURATION/60" | bc) 分钟)"
  echo "  退出码: $EXIT_CODE"
  
  # 复制结果到本循环目录
  cp "$LOG_DIR/best_params.json" "$CYCLE_DIR/" 2>/dev/null
  cp "$LOG_DIR/history.json" "$CYCLE_DIR/" 2>/dev/null
  cp "$LOG_DIR/live_status.json" "$CYCLE_DIR/" 2>/dev/null
  
  # 取最佳结果
  if [ -f "$BEST_FILE" ]; then
    BEST_RESULT=$(python3 -c "
import json
d = json.load(open('$BEST_FILE'))
fe = d.get('full_eval', {})
print(f'Score={d.get(\"score\",0):.1f} WR={fe.get(\"wr\",0):.1f}% N={fe.get(\"n\",0)} PF={fe.get(\"pf\",0):.2f} RR={fe.get(\"rr_avg\",0):.2f} Ret={fe.get(\"ret\",0):.2f}%')
" 2>/dev/null)
    echo "  🏆 本轮最佳: $BEST_RESULT"
    
    # OOS验证（如果有OOS脚本）
    if [ -f "$SCRIPT_DIR/smc_oos_verify.py" ]; then
      OOS_RESULT=$(cd "$SCRIPT_DIR" && python3 smc_oos_verify.py "$BEST_FILE" 2>/dev/null)
      echo "  🌍 OOS验证: $OOS_RESULT"
    fi
  fi
  
  # ═══════ 完成本循环 ═══════
  echo ""
  echo "  ✓ 循环 #${CYCLE_NUM} 完成"
  echo "  下一轮将在5秒后自动开始..."
  echo ""
  
  # 清理K线缓存（防止缓存过大）
  find "$HOME/.hermes/kline_cache" -name "*.json" -mtime +7 -delete 2>/dev/null
  
  sleep 5
done