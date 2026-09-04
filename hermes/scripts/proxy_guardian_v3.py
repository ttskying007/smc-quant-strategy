#!/usr/bin/env python3
"""
Proxy Guardian V3 — 全自动代理监控看门狗
=========================================
功能:
  1. 进程+端口+HTTP连通性 三重检测
  2. 自动重启失效代理
  3. 订阅更新失败时尝试旧节点
  4. 定时健康检查报告 (写入JSON供WebUI读取)
  5. 降级策略: kill → restart → 替换配置 → 备用节点
  6. 状态写入多个位置保证WebUI读到
  7. systemd兼容模式 (前台运行)

用法:
  python3 proxy_guardian_v3.py                # 前台运行
  nohup python3 proxy_guardian_v3.py &        # 后台运行
  python3 proxy_guardian_v3.py --single-check # 单次检查
  python3 proxy_guardian_v3.py --status       # 快速查看状态

安装为systemd服务:
  [Unit]
  Description=Proxy Guardian V3
  [Service]
  ExecStart=/usr/bin/python3 /root/.hermes/scripts/proxy_guardian_v3.py
  Restart=always
  [Install]
  WantedBy=multi-user.target
"""

import subprocess, time, sys, os, json, urllib.request, signal, shutil, random
from datetime import datetime
from pathlib import Path

# ============== Config ==============
LOG_DIR = Path.home() / '.hermes' / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / 'proxy_guardian_v3.log'
PID_FILE = Path.home() / '.hermes' / '.proxy_guardian_v3.pid'

# 状态文件 — 写入多个位置供不同WebUI读取
STATUS_FILES = [
    Path.home() / '.hermes' / 'logs' / 'proxy_status.json',
    Path.home() / '.hermes' / 'smc_opt_v7' / 'proxy_status.json',
    Path.home() / '.hermes' / 'smc_opt_v7plus' / 'proxy_status.json',
    Path.home() / '.hermes' / '.proxy_health.json',
    Path('/tmp/proxy_guardian_v4.json'),
]

CONFIG = Path.home() / '.clash' / 'config.yaml'
BACKUP_CONFIGS = [
    Path.home() / '.clash_config_new.yaml',
    Path.home() / '.clash' / 'config_backup.yaml',
]
MIHOMO_BIN = '/usr/local/bin/mihomo'
MIHOMO_DIR = Path.home() / '.clash'
HTTP_PROXY = 'http://127.0.0.1:7890'
API_URL = 'http://127.0.0.1:9090'

FAIL_THRESHOLD = 2         # 失败2次就重启
CHECK_INTERVAL = 20        # 每20秒检查一次
RESTART_COOLDOWN = 30      # 重启后冷却30秒
MAX_LOG_SIZE = 2 * 1024 * 1024  # 2MB

CONNECTIVITY_URLS = [
    'http://www.gstatic.com/generate_204',
    'http://connectivitycheck.platform.harness.com',
    'https://www.google.com',
    'https://www.github.com',
]

# ============== Logging ==============
def log(msg):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
        if os.path.getsize(LOG_FILE) > MAX_LOG_SIZE:
            rotate()
    except:
        pass

def rotate():
    if LOG_FILE.exists():
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        rotated = LOG_FILE.with_suffix(f'.{ts}.log')
        LOG_FILE.rename(rotated)
        log(f'Log rotated: {rotated.name}')

# ============== Status ==============
def save_status(status):
    status['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    status['check_interval'] = CHECK_INTERVAL
    for f in STATUS_FILES:
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            with open(f, 'w') as fp:
                json.dump(status, fp, ensure_ascii=False, indent=2)
        except:
            pass

# ============== Checks ==============
def check_process():
    r = subprocess.run(['pgrep', '-f', 'mihomo'], capture_output=True, text=True, timeout=5)
    pids = [p.strip() for p in r.stdout.strip().split('\n') if p.strip()]
    return pids

def check_api():
    try:
        req = urllib.request.Request(f'{API_URL}/version')
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.status == 200
    except:
        return False

def check_http_proxy():
    try:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({'http': HTTP_PROXY, 'https': HTTP_PROXY})
        )
        for url in CONNECTIVITY_URLS[:3]:
            try:
                req = urllib.request.Request(url, method='HEAD')
                resp = opener.open(req, timeout=8)
                if resp.status in (204, 200):
                    return True
            except:
                continue
        req = urllib.request.Request(CONNECTIVITY_URLS[0], method='HEAD')
        resp = opener.open(req, timeout=10)
        return resp.status in (204, 200)
    except:
        return False

def check_internet():
    result = {'google': False, 'github': False, 'youtube': False, 'overall': False}
    proxy_support = urllib.request.ProxyHandler({'http': HTTP_PROXY, 'https': HTTP_PROXY})
    opener = urllib.request.build_opener(proxy_support)
    tests = [
        ('google', 'https://www.google.com'),
        ('github', 'https://github.com'),
        ('youtube', 'https://www.youtube.com'),
    ]
    for name, url in tests:
        try:
            req = urllib.request.Request(url, method='HEAD')
            resp = opener.open(req, timeout=8)
            result[name] = resp.status in (200, 204, 301, 302)
        except:
            pass
    result['overall'] = all(result.values())
    return result

# ============== Actions ==============
def kill_existing():
    subprocess.run(['pkill', '-f', 'mihomo'], timeout=10, capture_output=True)
    time.sleep(2)
    pids = check_process()
    if pids:
        subprocess.run(['kill', '-9'] + pids, timeout=5, capture_output=True)
        time.sleep(1)

def find_working_config():
    """找到可用的配置文件"""
    for cfg in [CONFIG] + BACKUP_CONFIGS:
        if cfg.exists() and cfg.stat().st_size > 100:
            log(f'  Found config: {cfg} ({cfg.stat().st_size} bytes)')
            return cfg
    # 尝试下载
    log('  No config found, trying subscription download...')
    try:
        sub_path = Path.home() / '.hermes' / 'scripts' / 'clash_sub_hunter.py'
        if sub_path.exists():
            r = subprocess.run([sys.executable, str(sub_path), '--download-only'],
                              capture_output=True, timeout=60, text=True)
            log(f'  Sub hunter: {r.stdout[-200:]}')
            if CONFIG.exists() and CONFIG.stat().st_size > 100:
                return CONFIG
    except:
        pass
    return None

def ensure_mihomo_binary():
    """确保mihomo二进制可用"""
    if os.path.exists(MIHOMO_BIN) and os.path.getsize(MIHOMO_BIN) > 1000000:
        return True
    # 从备份恢复
    for src in ['/tmp/mihomo', '/tmp/mihomo-compat']:
        if os.path.exists(src) and os.path.getsize(src) > 1000000:
            shutil.copy2(src, MIHOMO_BIN)
            os.chmod(MIHOMO_BIN, 0o755)
            log(f'  Binary restored from {src}')
            return True
    log('  Binary NOT available!')
    return False

def try_alternate_port_start():
    """尝试用不同的端口启动 (如果7890被占用)"""
    alt_ports = [7891, 7892, 7898, 7899, 7893]
    # 先检查7890是否真的被占用
    r = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}',
                        '--max-time', '3', '127.0.0.1:7890'],
                       capture_output=True, text=True, timeout=5)
    if r.stdout.strip() == '204':
        return True  # 7890正常
    
    for port in alt_ports:
        log(f'  Trying port {port}...')
        alt_cfg = f'/home/lei/.clash_config_new.yaml'
        cmd = [MIHOMO_BIN, '-d', str(MIHOMO_DIR), '-f', alt_cfg]
        env = os.environ.copy()
        env['http_proxy'] = f'http://127.0.0.1:{port}'
        env['https_proxy'] = f'http://127.0.0.1:{port}'
        try:
            proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   start_new_session=True)
            time.sleep(5)
            r2 = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}',
                                '--max-time', '3', f'127.0.0.1:{port}'],
                               capture_output=True, text=True, timeout=5)
            if r2.stdout.strip() in ('204', '200'):
                log(f'  Alt port {port} works! PID={proc.pid}')
                return True
        except:
            pass
    return False

def restart_proxy():
    log('===== RESTARTING PROXY (V3) =====')
    
    # 1. 杀死现有进程
    kill_existing()
    
    # 2. 确保二进制
    if not ensure_mihomo_binary():
        log('  FAIL: No mihomo binary')
        return False
    
    # 3. 找配置
    config = find_working_config()
    if not config:
        log('  FAIL: No config found')
        return False
    
    # 4. 启动
    cmd = [MIHOMO_BIN, '-d', str(MIHOMO_DIR), '-f', str(config)]
    log(f'  Starting: {" ".join(cmd)}')
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           start_new_session=True)
    time.sleep(8)
    
    # 5. 验证
    pids = check_process()
    api_ok = check_api()
    http_ok = check_http_proxy()
    
    if pids and (api_ok or http_ok):
        log(f'  RESTARTED OK (PID={pids[0]})')
        return True
    
    # 6. 二次尝试 — 等更久
    log('  Waiting longer for proxy...')
    time.sleep(15)
    pids = check_process()
    api_ok = check_api()
    http_ok = check_http_proxy()
    
    if pids and (api_ok or http_ok):
        log(f'  RESTARTED OK after waiting (PID={pids[0]})')
        return True
    
    # 7. 尝试备用端口
    log('  Trying alternate ports...')
    if try_alternate_port_start():
        return True
    
    log('  RESTART FAILED!')
    return False

# ============== Commands ==============
def single_check():
    pids = check_process()
    api_ok = check_api()
    http_ok = check_http_proxy()
    connectivity = check_internet() if http_ok else {'overall': False}
    
    status = {
        'running': bool(pids),
        'pid_count': len(pids),
        'api_ok': api_ok,
        'http_ok': http_ok,
        'connectivity': connectivity,
        'all_ok': bool(pids) and api_ok and http_ok and connectivity.get('overall', False),
    }
    print(json.dumps(status, indent=2))
    save_status(status)
    return status

def show_status():
    pids = check_process()
    api_ok = check_api()
    http_ok = check_http_proxy()
    connectivity = check_internet()
    
    print(f"{'='*50}")
    print(f"  Proxy Guardian V3 — Health Status")
    print(f"{'='*50}")
    print(f"  Time:        {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Process:     {'✅ RUNNING' if pids else '❌ DOWN'} (PID: {', '.join(pids[:3]) if pids else 'N/A'})")
    print(f"  API (9090):  {'✅ OK' if api_ok else '❌ DOWN'}")
    print(f"  HTTP (7890): {'✅ OK' if http_ok else '❌ DOWN'}")
    print(f"  Internet:")
    for k, v in connectivity.items():
        if k != 'overall':
            print(f"    {k:>10}: {'✅' if v else '❌'}")
    print(f"  Overall:     {'✅ ALL OK' if connectivity.get('overall', False) else '❌ ISSUES'}")
    print()
    
    # Show log tail
    if LOG_FILE.exists():
        tail = subprocess.run(['tail', '-5', str(LOG_FILE)], capture_output=True, text=True, timeout=3)
        print(f"  Last 5 log lines:")
        for line in tail.stdout.strip().split('\n')[-5:]:
            print(f"    {line}")
    print(f"{'='*50}")
    return pids and api_ok and http_ok and connectivity.get('overall', False)

# ============== Main Loop ==============
def cleanup():
    log('Proxy Guardian V3 shutting down')
    if PID_FILE.exists():
        PID_FILE.unlink()
    save_status({'running': False, 'reason': 'shutdown'})
    sys.exit(0)

def main():
    signal.signal(signal.SIGINT, lambda s, f: cleanup())
    signal.signal(signal.SIGTERM, lambda s, f: cleanup())
    
    # 防重复
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            r = subprocess.run(['kill', '-0', str(old_pid)], capture_output=True, timeout=3)
            if r.returncode == 0:
                print(f'Proxy Guardian V3 already running (PID: {old_pid})')
                print(f'Log: {LOG_FILE}')
                sys.exit(0)
        except:
            pass
    
    PID_FILE.write_text(str(os.getpid()))
    
    log('=' * 50)
    log('Proxy Guardian V3 STARTED')
    log(f'PID: {os.getpid()}')
    log(f'Config: {CONFIG}')
    log(f'Check interval: {CHECK_INTERVAL}s, Fail threshold: {FAIL_THRESHOLD}')
    log('=' * 50)
    
    fail_count = 0
    total_restarts = 0
    last_health_save = 0
    consecutive_failures = 0
    
    while True:
        try:
            proc_pids = check_process()
            api_ok = check_api()
            http_ok = check_http_proxy()
            
            all_ok = bool(proc_pids) and api_ok and http_ok
            
            if all_ok:
                fail_count = 0
                consecutive_failures = 0
                # 每10次保存健康报告
                if time.time() - last_health_save > 200:
                    connectivity = check_internet()
                    save_status({
                        'running': True,
                        'pid_count': len(proc_pids),
                        'api_ok': True,
                        'http_ok': True,
                        'connectivity': connectivity,
                        'all_ok': True,
                        'total_restarts': total_restarts,
                        'fail_count': 0,
                        'state': 'healthy',
                        'total_checks': 0,
                    })
                    last_health_save = time.time()
            else:
                fail_count += 1
                status_parts = []
                status_parts.append(f'Proc:{"OK(" + ",".join(proc_pids[:2]) + ")" if proc_pids else "DOWN"}')
                status_parts.append(f'API:{"OK" if api_ok else "DOWN"}')
                status_parts.append(f'HTTP:{"OK" if http_ok else "DOWN"}')
                log(f'WARN #{fail_count}: {", ".join(status_parts)}')
                
                if fail_count >= FAIL_THRESHOLD:
                    log(f'=== PROXY DOWN (failed {fail_count}x in a row) ===')
                    consecutive_failures += 1
                    
                    save_status({
                        'running': False,
                        'api_ok': api_ok,
                        'http_ok': http_ok,
                        'all_ok': False,
                        'total_restarts': total_restarts,
                        'fail_count': fail_count,
                        'state': 'restarting',
                        'reboot_attempt': consecutive_failures,
                    })
                    
                    if restart_proxy():
                        total_restarts += 1
                        fail_count = 0
                        log(f'Restart #{total_restarts} SUCCESS')
                        save_status({
                            'running': True,
                            'api_ok': True,
                            'http_ok': True,
                            'all_ok': True,
                            'total_restarts': total_restarts,
                            'fail_count': 0,
                            'state': 'recovered',
                        })
                        time.sleep(RESTART_COOLDOWN)
                    else:
                        log('RESTART FAILED, waiting 60s...')
                        # 发送系统通知 (如果有)
                        time.sleep(60)
                        # 如果重启失败次数太多，更激进
                        if consecutive_failures >= 5:
                            log('CRITICAL: Killed 5x in a row, trying full kill+reinstall')
                            subprocess.run(['pkill', '-9', '-f', 'mihomo'], timeout=5, capture_output=True)
                            time.sleep(5)
                            # 尝试重新下载mihomo
                            subprocess.run(['apt-get', 'install', '--reinstall', '-y', 'mihomo'],
                                          capture_output=True, timeout=60)
                            time.sleep(5)
                            consecutive_failures = 0
                        continue
            
            time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            cleanup()
        except Exception as e:
            log(f'ERROR: {e}')
            import traceback
            traceback.print_exc()
            time.sleep(CHECK_INTERVAL)

if __name__ == '__main__':
    if '--single-check' in sys.argv:
        single_check()
    elif '--status' in sys.argv:
        show_status()
    elif '--repair' in sys.argv:
        status = single_check()
        if not status['all_ok']:
            print('Repairing...')
            if restart_proxy():
                print('Repair OK')
            else:
                print('Repair FAILED')
    else:
        main()