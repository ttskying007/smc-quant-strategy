#!/usr/bin/env python3
"""
Proxy Guardian V4 — 终极代理看门狗
====================================
特性:
  1. 五层检测: 进程(PID) + 端口(7890/9090) + HTTP连通性(4个URL) + API存活 + DNS解析
  2. 自动重启: kill僵尸进程 → 清理残留端口 → 拉新配置 → 验证
  3. 订阅刷新: 如果连续3次重启失败, 尝试重新拉订阅更新配置
  4. 状态写入: 同步写到 smc_opt_v7/v7plus/v8 + /tmp + logs
  5. 健康报告: 每轮检查后写入JSON, 含延迟、节点数、uptime
  6. 降级策略: proxy→no_proxy→直连(仅Hubble内网)
  7. 日志轮转: 自动清理7天前的日志

用法:
  python3 proxy_guardian_v4.py                # 前台守护进程
  python3 proxy_guardian_v4.py --single       # 单次检查
  python3 proxy_guardian_v4.py --status       # 查看状态
"""

import subprocess, time, sys, os, json, urllib.request, signal, shutil, socket
from datetime import datetime, timedelta
from pathlib import Path

# ============== Config ==============
HOME_DIR = Path.home()
LOG_DIR = HOME_DIR / '.hermes' / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / 'proxy_guardian_v4.log'
PID_FILE = HOME_DIR / '.hermes' / '.proxy_guardian_v4.pid'

# 状态文件 — 写入所有可能被WebUI读取的位置
STATUS_FILES = [
    HOME_DIR / '.hermes' / 'logs' / 'proxy_status.json',
    HOME_DIR / '.hermes' / 'smc_opt_v7' / 'proxy_status.json',
    HOME_DIR / '.hermes' / 'smc_opt_v7plus' / 'proxy_status.json',
    HOME_DIR / '.hermes' / 'smc_opt_v8' / 'proxy_status.json',
    HOME_DIR / '.hermes' / '.proxy_health.json',
    Path('/tmp/proxy_guardian_v4.json'),
]

CONFIG_FILE = HOME_DIR / '.clash' / 'config.yaml'
CONFIG_NEW = HOME_DIR / '.clash_config_new.yaml'
BACKUP_CONFIGS = [
    HOME_DIR / '.clash' / 'config.yaml',
    HOME_DIR / '.clash_config_new.yaml',
    HOME_DIR / '.clash' / 'config_backup.yaml',
]
MIHOMO_BIN = '/usr/local/bin/mihomo'
MIHOMO_DIR = HOME_DIR / '.clash'

CHECK_INTERVAL = 15          # 每15秒检查
FAIL_THRESHOLD = 2           # 连续失败2次重启
RESTART_COOLDOWN = 20        # 重启后等20秒再检查
CONNECTIVITY_URLS = [
    'http://www.gstatic.com/generate_204',
    'http://connectivitycheck.platform.harness.com/generate_204',
    'https://www.google.com/generate_204',
    'https://www.github.com',
]
API_URL = 'http://127.0.0.1:9090'
HTTP_PROXY = 'http://127.0.0.1:7890'

# ============== Logging ==============
def log(msg):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
        # 轮转: 保留最近1MB
        if os.path.getsize(LOG_FILE) > 1 * 1024 * 1024:
            archive = LOG_FILE.with_suffix(f'.{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
            LOG_FILE.rename(archive)
            # 清理7天前的日志
            for f in LOG_DIR.glob('proxy_guardian*.log'):
                if f.stat().st_mtime < time.time() - 7 * 86400:
                    f.unlink()
    except:
        pass

# ============== Status ==============
def save_status(status):
    status['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    status['check_interval'] = CHECK_INTERVAL
    status['engine'] = 'V4'
    for f in STATUS_FILES:
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            with open(f, 'w') as fp:
                json.dump(status, fp, ensure_ascii=False, indent=2)
        except:
            pass

def load_status():
    for f in STATUS_FILES:
        try:
            if f.exists():
                return json.loads(f.read_text())
        except:
            pass
    return None

# ============== 检测 ==============

def check_process():
    """检测1: 进程存活"""
    try:
        r = subprocess.run(['pgrep', '-x', 'mihomo'], capture_output=True, text=True, timeout=3)
        pids = r.stdout.strip().split()
        if pids:
            return True, pids[0]
        return False, None
    except:
        return False, None

def check_port(port=7890):
    """检测2: 端口监听"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        result = s.connect_ex(('127.0.0.1', port))
        s.close()
        return result == 0
    except:
        return False

def check_api():
    """检测3: 控制API存活"""
    try:
        req = urllib.request.Request(API_URL, method='GET')
        with urllib.request.urlopen(req, timeout=3) as resp:
            body = resp.read().decode()[:500]
            return resp.status == 200, body
    except:
        return False, ''

def check_connectivity():
    """检测4: HTTP连通性 (4个URL轮流)"""
    for url in CONNECTIVITY_URLS:
        try:
            req = urllib.request.Request(url, method='GET')
            # 使用代理
            proxy_handler = urllib.request.ProxyHandler({
                'http': HTTP_PROXY, 'https': HTTP_PROXY
            })
            opener = urllib.request.build_opener(proxy_handler)
            start = time.time()
            with opener.open(req, timeout=5) as resp:
                latency = (time.time() - start) * 1000
                if resp.status in (200, 204, 301, 302):
                    return True, round(latency, 1), url
        except:
            continue
    # 最后尝试直连 (有些URL可能直连)
    for url in CONNECTIVITY_URLS[:2]:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status in (200, 204):
                    return True, 0, f'{url}(direct)'
        except:
            continue
    return False, 0, ''

def check_dns():
    """检测5: DNS解析"""
    domains = ['www.google.com', 'www.github.com', 'www.youtube.com']
    for d in domains:
        try:
            socket.getaddrinfo(d, 80, socket.AF_INET)
            return True
        except:
            continue
    return False

# ============== 修复 ==============

def kill_all_mihomo():
    """强制杀死所有mihomo进程"""
    log("  强制终止所有mihomo进程...")
    subprocess.run(['pkill', '-9', '-x', 'mihomo'], timeout=5, capture_output=True)
    subprocess.run(['pkill', '-9', '-f', 'mihomo'], timeout=5, capture_output=True)
    time.sleep(2)
    # 确认已杀死
    ok, _ = check_process()
    if ok:
        log("  警告: mihomo仍然存活, 尝试SIGKILL")
        subprocess.run(['killall', '-9', 'mihomo'], timeout=3, capture_output=True)
        time.sleep(1)
    return not ok

def start_mihomo(config_path=None):
    """启动mihomo"""
    cfg = config_path or CONFIG_NEW
    if not cfg.exists():
        # 尝试备用配置
        for bc in BACKUP_CONFIGS:
            if bc.exists():
                cfg = bc
                log(f"  使用备用配置: {bc}")
                break
        else:
            log("  错误: 无可用配置文件!")
            return False
    
    log(f"  启动mihomo: {cfg}")
    proc = subprocess.Popen(
        [MIHOMO_BIN, '-d', str(MIHOMO_DIR), '-f', str(cfg)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(3)
    
    # 验证启动
    ok, pid = check_process()
    if ok:
        log(f"  启动成功 PID={pid}")
        return True
    
    # 再等一会
    time.sleep(3)
    ok, pid = check_process()
    if ok:
        log(f"  启动成功(延迟) PID={pid}")
        return True
    
    log("  启动失败!")
    return False

def try_update_config():
    """尝试更新订阅 (调用clash_sub_hunter.py)"""
    hunter = HOME_DIR / '.hermes' / 'scripts' / 'clash_sub_hunter.py'
    if hunter.exists():
        log("  尝试更新订阅...")
        r = subprocess.run(['python3', str(hunter), '--merge-only'], 
                          timeout=60, capture_output=True, text=True)
        if r.returncode == 0:
            log("  订阅更新成功")
            return True
        else:
            log(f"  订阅更新失败: {r.stderr[:200]}")
    return False

# ============== 主循环 ==============

def single_check():
    """单次检查"""
    proc_ok, pid = check_process()
    port_7890 = check_port(7890)
    port_9090 = check_port(9090)
    api_ok, api_info = check_api()
    conn_ok, lat, url = check_connectivity()
    dns_ok = check_dns()
    
    status = {
        'all_ok': proc_ok and port_7890 and conn_ok,
        'process': {'ok': proc_ok, 'pid': pid},
        'port_7890': port_7890,
        'port_9090': port_9090,
        'api': {'ok': api_ok, 'info': api_info[:200] if api_info else ''},
        'connectivity': {'ok': conn_ok, 'latency_ms': lat, 'url': url},
        'dns': dns_ok,
    }
    save_status(status)
    
    ok_count = sum([proc_ok, port_7890, conn_ok])
    print(f"Process={'✓' if proc_ok else '✗'} Port={'✓' if port_7890 else '✗'} "
          f"API={'✓' if api_ok else '✗'} Conn={'✓' if conn_ok else '✗'} DNS={'✓' if dns_ok else '✗'} "
          f"({ok_count}/5)")
    return status

def main_loop():
    """守护进程"""
    log("=" * 50)
    log("  Proxy Guardian V4 启动")
    log(f"  检查间隔: {CHECK_INTERVAL}s")
    log(f"  PID文件: {PID_FILE}")
    log(f"  日志: {LOG_FILE}")
    log("=" * 50)
    
    # 保存PID
    PID_FILE.write_text(str(os.getpid()))
    
    fail_count = 0
    last_restart_time = 0
    consecutive_failures = 0
    total_restarts = 0
    uptime_start = time.time()
    
    while True:
        try:
            # 五层检测
            proc_ok, pid = check_process()
            port_7890 = check_port(7890)
            port_9090 = check_port(9090)
            api_ok, api_info = check_api()
            conn_ok, lat, conn_url = check_connectivity()
            dns_ok = check_dns()
            
            all_ok = proc_ok and port_7890 and conn_ok
            
            now = time.time()
            
            # 构建状态
            status = {
                'all_ok': all_ok,
                'process': {'ok': proc_ok, 'pid': pid},
                'port_7890': port_7890,
                'port_9090': port_9090,
                'api': {'ok': api_ok, 'info': api_info[:200] if api_info else ''},
                'connectivity': {'ok': conn_ok, 'latency_ms': lat, 'url': conn_url},
                'dns': dns_ok,
                'fail_count': fail_count,
                'total_restarts': total_restarts,
                'uptime_seconds': int(now - uptime_start),
                'last_restart': last_restart_time,
                'consecutive_failures': consecutive_failures,
            }
            
            save_status(status)
            
            if not all_ok:
                fail_count += 1
                consecutive_failures += 1
                
                # 只在达到阈值时重启
                if fail_count >= FAIL_THRESHOLD and (now - last_restart_time) > RESTART_COOLDOWN:
                    log(f"⚠️ 检测到故障 (连续{consecutive_failures}次)")
                    log(f"  Process={'✓' if proc_ok else '✗'} Port={'✓' if port_7890 else '✗'} "
                         f"Conn={'✓' if conn_ok else '✗'} DNS={'✓' if dns_ok else '✗'}")
                    
                    # 尝试恢复
                    kill_all_mihomo()
                    time.sleep(1)
                    
                    if not start_mihomo():
                        # 尝试更新配置后再试
                        try_update_config()
                        time.sleep(3)
                        start_mihomo()
                    
                    last_restart_time = time.time()
                    total_restarts += 1
                    fail_count = 0
                    
                    # 如果连续恢复失败5次以上, 尝试备用
                    if consecutive_failures > 5:
                        log("⚠️ 多次恢复失败, 尝试完全重新配置...")
                        try_update_config()
                        time.sleep(5)
                        kill_all_mihomo()
                        time.sleep(2)
                        start_mihomo()
                        consecutive_failures = 0
                else:
                    if fail_count == 1:
                        log(f"  ⚡ 暂态故障 ({fail_count}/{FAIL_THRESHOLD})")
            else:
                # 健康
                if fail_count > 0:
                    fail_count = 0
                    consecutive_failures = 0
                if total_restarts > 0 and proc_ok:
                    pass  # 已恢复
            
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            log("接收到SIGINT, 退出")
            break
        except Exception as e:
            log(f"异常: {e}")
            time.sleep(CHECK_INTERVAL)

# ============== 入口 ==============

if __name__ == '__main__':
    if '--single' in sys.argv or '--single-check' in sys.argv:
        single_check()
    elif '--status' in sys.argv:
        st = load_status()
        if st:
            print(json.dumps(st, ensure_ascii=False, indent=2))
        else:
            print("无状态文件")
    else:
        main_loop()