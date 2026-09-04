#!/usr/bin/env bash
# =============================================================================
# SMC代理监控守护脚本
# 功能: 三重检测(进程+端口+HTTP连通性) + 自动恢复
# 运行: 每60秒检查一次, 如果发现问题自动重启代理
# 用法: 放入crontab (每分钟执行) 或 systemd
# =============================================================================

set -euo pipefail

# 配置
PROXY_BIN="/usr/local/bin/mihomo"
CONFIG_FILE="/home/lei/.clash_config_new.yaml"
PROXY_DIR="$HOME/.clash"
PROXY_PORT=7890
API_PORT=9090
LOG_FILE="$HOME/.clash/proxy_monitor.log"
PID_FILE="$HOME/.clash/mihomo.pid"
MAX_RESTART=5          # 30分钟内最多重启次数
RESTART_WINDOW=1800    # 重启窗口 (30秒)

# 检测网址 (翻墙验证)
TEST_URLS=(
    "https://www.google.com"
    "https://www.youtube.com"
    "https://github.com"
    "https://api.openai.com"
)

log() {
    local level="${2:-INFO}"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$level] $1" >> "$LOG_FILE"
    echo "[$level] $1"
}

check_process() {
    # 用pgrep找第一个mihomo进程
    local pid
    pid=$(pgrep -o -x mihomo 2>/dev/null || echo "")
    if [ -n "$pid" ]; then
        log "进程运行中 (PID=$pid)"
        echo "$pid" > "$PID_FILE"
        return 0
    fi
    
    log "进程未运行" "WARN"
    return 1
}

check_port() {
    local port="$1"
    local name="$2"
    if ss -tlnp "sport = :$port" 2>/dev/null | grep -q LISTEN; then
        log "端口 $port ($name) 正常"
        return 0
    fi
    log "端口 $port ($name) 未监听" "WARN"
    return 1
}

check_connectivity() {
    local url
    for url in "${TEST_URLS[@]}"; do
        if curl -sS -o /dev/null --max-time 8 -x "http://127.0.0.1:$PROXY_PORT" "$url" 2>/dev/null; then
            log "代理连通 OK ($url)"
            return 0
        fi
        log "代理连通 失败 ($url)" "WARN"
    done
    return 1
}

start_proxy() {
    log "正在启动代理..." "ACTION"
    
    # 清理残留
    rm -f "$PID_FILE"
    pkill -x mihomo 2>/dev/null || true
    sleep 1
    
    # 启动
    nohup "$PROXY_BIN" -d "$PROXY_DIR" -f "$CONFIG_FILE" >> "$LOG_FILE" 2>&1 &
    local pid=$!
    echo "$pid" > "$PID_FILE"
    
    log "代理启动 (PID=$pid)" "ACTION"
    
    # 等待启动完成
    for i in $(seq 1 10); do
        sleep 2
        if ss -tlnp "sport = :$PROXY_PORT" 2>/dev/null | grep -q LISTEN; then
            log "代理启动确认: 端口 $PROXY_PORT 已监听"
            
            # 设置系统代理
            export http_proxy="http://127.0.0.1:$PROXY_PORT"
            export https_proxy="http://127.0.0.1:$PROXY_PORT"
            export all_proxy="socks5://127.0.0.1:$PROXY_PORT"
            export HTTP_PROXY="http://127.0.0.1:$PROXY_PORT"
            export HTTPS_PROXY="http://127.0.0.1:$PROXY_PORT"
            export ALL_PROXY="socks5://127.0.0.1:$PROXY_PORT"
            
            # 写入bashrc
            if ! grep -q "export http_proxy=http://127.0.0.1:$PROXY_PORT" /root/.bashrc 2>/dev/null; then
                echo "" >> /root/.bashrc
                echo "# 代理设置 (自动)" >> /root/.bashrc
                echo "export http_proxy=http://127.0.0.1:$PROXY_PORT" >> /root/.bashrc
                echo "export https_proxy=http://127.0.0.1:$PROXY_PORT" >> /root/.bashrc
                echo "export all_proxy=socks5://127.0.0.1:$PROXY_PORT" >> /root/.bashrc
                echo "export HTTP_PROXY=http://127.0.0.1:$PROXY_PORT" >> /root/.bashrc
                echo "export HTTPS_PROXY=http://127.0.0.1:$PROXY_PORT" >> /root/.bashrc
                echo "export ALL_PROXY=socks5://127.0.0.1:$PROXY_PORT" >> /root/.bashrc
            fi
            
            return 0
        fi
    done
    
    log "代理启动超时" "ERROR"
    return 1
}

# 计数重启
count_restarts() {
    local now
    now=$(date +%s)
    local count=0
    if [ -f "$LOG_FILE" ]; then
        count=$(grep -c "正在启动代理" "$LOG_FILE" 2>/dev/null || echo 0)
    fi
    echo "$count"
}

# =============================================================================
# 主检查逻辑
# =============================================================================

main() {
    log "=== 代理监控检查 ==="
    
    local restart_count
    restart_count=$(count_restarts)
    
    if [ "$restart_count" -ge "$MAX_RESTART" ]; then
        log "重启次数超限 ($restart_count >= $MAX_RESTART), 跳过自动重启" "ERROR"
        log "手动检查: 1) 配置是否正确 2) 订阅是否过期 3) 网络是否正常"
        exit 1
    fi
    
    local all_ok=true
    local failures=()
    
    # 检查1: 进程
    if ! check_process; then
        all_ok=false
        failures+=("进程")
    fi
    
    # 检查2: 端口
    if ! check_port "$PROXY_PORT" "HTTP/SOCKS"; then
        all_ok=false
        failures+=("端口$PROXY_PORT")
    fi
    if ! check_port "$API_PORT" "API"; then
        all_ok=false
        failures+=("端口$API_PORT")
    fi
    
    if [ "$all_ok" = false ]; then
        log "问题: ${failures[*]}, 尝试重启..." "WARN"
        start_proxy
        exit $?
    fi
    
    # 检查3: 连通性 (每3次检查才测一次, 节省资源)
    local check_id
    check_id=$(date +%s)
    if [ $((check_id % 180)) -lt 60 ]; then  # 大约每3分钟一次
        if ! check_connectivity; then
            log "连通性失败, 尝试重启..." "WARN"
            start_proxy
            exit $?
        fi
    fi
    
    log "✓ 代理状态正常"
    return 0
}

main "$@"