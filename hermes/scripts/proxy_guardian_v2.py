#!/usr/bin/env python3
"""
Proxy Guardian v2.0 — 增强版代理监控看门狗
=============================================
自动检测 mihomo(Clash Meta) 代理状态，失效时自动重启

v2.0 增强:
  1. 三重检查: 进程/端口/HTTP连通性
  2. 实际连通性检查: curl google.com/github.com/youtube.com
  3. mihomo二进制0字节恢复 (从/tmp/mihomo)
  4. 重启失败后的降级策略
  5. 日志轮转
  6. PID文件防重复

用法:
  python3 proxy_guardian_v2.py                # 前台运行
  nohup python3 proxy_guardian_v2.py &        # 后台运行
  python3 proxy_guardian_v2.py --single-check  # 单次检查 (用于cron)
  python3 proxy_guardian_v2.py --repair        # 仅修复 (重启代理)
"""

import subprocess, time, sys, os, json, urllib.request, signal, shutil
from datetime import datetime
from pathlib import Path

LOG_DIR = Path.home() / '.hermes' / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / 'proxy_guardian_v2.log'
PID_FILE = Path.home() / '.hermes' / '.proxy_guardian_v2.pid'
HEALTH_FILE = Path.home() / '.hermes' / '.proxy_health.json'  # 供WebUI读取
STATUS_FILE = Path.home() / '.hermes' / 'logs' / 'proxy_status.json'

CONFIG = Path.home() / '.clash' / 'config.yaml'
MIHOMO_BIN = '/usr/local/bin/mihomo'
MIHOMO_DIR = Path.home() / '.clash'
HTTP_PROXY = 'http://127.0.0.1:7890'
API_URL = 'http://127.0.0.1:9090'

FAIL_THRESHOLD = 3
CHECK_INTERVAL = 30  # 秒
MAX_LOG_SIZE = 1024 * 1024  # 1MB

# 连通性测试URL
CONNECTIVITY_URLS = [
    'http://www.gstatic.com/generate_204',  # Google 快速检测
    'http://connectivitycheck.platform.harness.com',  # 备用
    'https://www.google.com',  # HTTPS测试
    'https://www.github.com',  # 关键服务
]


def log(msg):
    """日志"""
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + '\n')
    # 日志轮转
    if os.path.getsize(LOG_FILE) > MAX_LOG_SIZE:
        rotate()


def rotate():
    """日志轮转"""
    if LOG_FILE.exists():
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        rotated = LOG_FILE.with_suffix(f'.{ts}.log')
        LOG_FILE.rename(rotated)
        log(f'Log rotated: {rotated.name}')


def save_status(status):
    """保存状态供外部读取"""
    status['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    status['check_interval'] = CHECK_INTERVAL
    try:
        with open(STATUS_FILE, 'w') as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
    except:
        pass


def check_process():
    """检查mihomo进程"""
    r = subprocess.run(['pgrep', '-f', 'mihomo'], capture_output=True, text=True, timeout=5)
    pids = [p.strip() for p in r.stdout.strip().split('\n') if p.strip()]
    return pids


def check_http_proxy():
    """检查代理HTTP端口"""
    try:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({'http': HTTP_PROXY, 'https': HTTP_PROXY})
        )
        for url in CONNECTIVITY_URLS[:2]:  # 前2个HTTP URL
            try:
                req = urllib.request.Request(url, method='HEAD')
                resp = opener.open(req, timeout=8)
                if resp.status in (204, 200):
                    return True
            except:
                continue
        # 最后尝试一次
        req = urllib.request.Request(CONNECTIVITY_URLS[0], method='HEAD')
        resp = opener.open(req, timeout=10)
        return resp.status in (204, 200)
    except Exception as e:
        log(f'  HTTP proxy check failed: {str(e)[:60]}')
        return False


def check_internet_connectivity():
    """
    实际连通性检测
    返回: {'google': bool, 'github': bool, 'youtube': bool, 'overall': bool}
    """
    result = {'google': False, 'github': False, 'youtube': False, 'overall': False}
    
    proxy_support = urllib.request.ProxyHandler({'http': HTTP_PROXY, 'https': HTTP_PROXY})
    opener = urllib.request.build_opener(proxy_support)
    
    tests = [
        ('google', 'https://www.google.com/generate_204'),
        ('github', 'https://github.com'),
        ('youtube', 'https://www.youtube.com'),
    ]
    
    for name, url in tests:
        try:
            req = urllib.request.Request(url, method='HEAD')
            resp = opener.open(req, timeout=8)
            result[name] = resp.status in (200, 204, 301, 302)
        except Exception as e:
            result[name] = False
    
    result['overall'] = all(result.values())
    return result


def check_api():
    """检查Clash API"""
    try:
        req = urllib.request.Request(f'{API_URL}/version')
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.status == 200
    except:
        return False


def get_traffic():
    """获取流量信息 (仅用于健康报告)"""
    try:
        req = urllib.request.Request(f'{API_URL}/traffic')
        resp = urllib.request.urlopen(req, timeout=3)
        data = json.loads(resp.read())
        return data.get('upTotal', 0) / 1024 / 1024, data.get('downTotal', 0) / 1024 / 1024
    except:
        return 0, 0


def restart_proxy():
    """重启代理 (带降级)"""
    log('🔄 Restarting proxy (v2)...')
    
    # 1. Kill existing
    subprocess.run(['pkill', '-f', 'mihomo'], timeout=10, capture_output=True)
    time.sleep(2)
    
    pids = check_process()
    if pids:
        subprocess.run(['kill', '-9'] + pids, timeout=5, capture_output=True)
        time.sleep(1)
    
    # 2. 检查二进制完整性
    if not os.path.exists(MIHOMO_BIN) or os.path.getsize(MIHOMO_BIN) == 0:
        log('  Binary is empty/missing, restoring from backup')
        # 从/tmp备份恢复
        for src in ['/tmp/mihomo', '/tmp/mihomo-compat']:
            if os.path.exists(src) and os.path.getsize(src) > 1000000:
                shutil.copy2(src, MIHOMO_BIN)
                os.chmod(MIHOMO_BIN, 0o755)
                log(f'  Restored from {src}')
                break
        else:
            log('  ❌ No valid backup found! Trying to download...')
            # 尝试从github下载
            return False
    
    # 3. 启动
    if not CONFIG.exists():
        log(f'  ❌ Config not found: {CONFIG}')
        return False
    
    cmd = [MIHOMO_BIN, '-d', str(MIHOMO_DIR), '-f', str(CONFIG)]
    log(f'  Starting: {" ".join(cmd)}')
    
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )
    time.sleep(5)
    
    # 4. 验证
    pids = check_process()
    api_ok = check_api()
    http_ok = check_http_proxy()
    
    if pids and api_ok:
        log(f'✅ Restarted successfully (PID: {pids[0]})')
        return True
    elif pids:
        log(f'⚠ Process up but API/HTTP not responding, waiting...')
        time.sleep(10)
        api_ok = check_api()
        http_ok = check_http_proxy()
        if api_ok or http_ok:
            log(f'✓ Proxy stabilized after waiting')
            return True
    
    log('❌ Restart failed')
    return False


def single_check():
    """单次检查 (用于cron调用)"""
    pids = check_process()
    api_ok = check_api()
    http_ok = check_http_proxy()
    connectivity = check_internet_connectivity() if http_ok else {'overall': False}
    
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


def cleanup():
    log('Shutting down Proxy Guardian v2')
    if PID_FILE.exists():
        PID_FILE.unlink()
    # 保存最终状态
    save_status({'running': False, 'reason': 'shutdown'})
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, lambda s, f: cleanup())
    signal.signal(signal.SIGTERM, lambda s, f: cleanup())
    
    # 防止重复启动
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            r = subprocess.run(['kill', '-0', str(old_pid)], capture_output=True, timeout=3)
            if r.returncode == 0:
                print(f'Proxy Guardian already running (PID: {old_pid})')
                print(f'Log: {LOG_FILE}')
                sys.exit(0)
        except:
            pass
    
    PID_FILE.write_text(str(os.getpid()))
    
    log('=' * 50)
    log('Proxy Guardian v2 started')
    log(f'PID: {os.getpid()}')
    log(f'Config: {CONFIG}')
    log(f'Fail threshold: {FAIL_THRESHOLD}')
    log(f'Check interval: {CHECK_INTERVAL}s')
    log('=' * 50)
    
    fail_count = 0
    total_restarts = 0
    last_health_save = 0
    
    while True:
        try:
            proc_pids = check_process()
            api_ok = check_api()
            http_ok = check_http_proxy()
            
            # 每5次保存一次健康报告
            health_update = (time.time() - last_health_save) > 150  # 每150秒
            
            status_parts = []
            if proc_pids:
                status_parts.append(f'PID:{",".join(proc_pids[:3])}')
            else:
                status_parts.append('NO_PROCESS')
            status_parts.append(f'API:{"OK" if api_ok else "FAIL"}')
            status_parts.append(f'HTTP:{"OK" if http_ok else "FAIL"}')
            
            all_ok = bool(proc_pids) and api_ok and http_ok
            
            # 更新状态文件
            if health_update or all_ok != fail_count == 0:
                connectivity = {}
                if all_ok:
                    connectivity = check_internet_connectivity()
                save_status({
                    'running': bool(proc_pids),
                    'api_ok': api_ok,
                    'http_ok': http_ok,
                    'connectivity': connectivity,
                    'all_ok': all_ok,
                    'total_restarts': total_restarts,
                    'fail_count': fail_count,
                })
                last_health_save = time.time()
            
            if all_ok:
                if fail_count > 0:
                    log(f'✓ Recovered after {fail_count} failures')
                fail_count = 0
            else:
                fail_count += 1
                log(f'⚠ Check #{fail_count}/{FAIL_THRESHOLD}: {", ".join(status_parts)}')
                
                if fail_count >= FAIL_THRESHOLD:
                    log(f'🚨 Proxy DOWN (failed {fail_count}x)')
                    if restart_proxy():
                        total_restarts += 1
                        fail_count = 0
                        log(f'Restart #{total_restarts} successful')
                    else:
                        log('  ❌ Restart failed, will retry in 60s')
                        time.sleep(60)
                        continue
            
            time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            cleanup()
        except Exception as e:
            log(f'Error: {e}')
            import traceback
            traceback.print_exc()
            time.sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    if '--single-check' in sys.argv:
        single_check()
    elif '--repair' in sys.argv:
        status = single_check()
        if not status['all_ok']:
            print('Repairing proxy...')
            restart_proxy()
            status = single_check()
            print(f'After repair: {"OK" if status["all_ok"] else "STILL DOWN"}')
    else:
        main()