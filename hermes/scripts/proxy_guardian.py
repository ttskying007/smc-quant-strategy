#!/usr/bin/env python3
"""
Proxy Guardian — 代理监控看门狗
自动检测 mihomo(Clash Meta) 代理状态，失效时自动重启

工作方式:
  1. 每30秒检查代理是否存活 (HTTP 7890, API 9090)
  2. 检查连通性: curl google.com & github.com
  3. 连续失败3次判定为死亡，自动拉起
  4. 记录日志到 ~/.hermes/logs/proxy_guardian.log

用法:
  python3 proxy_guardian.py               # 前台运行
  nohup python3 proxy_guardian.py &        # 后台运行
"""

import subprocess, time, sys, os, json, urllib.request, signal
from datetime import datetime
from pathlib import Path

LOG_DIR = Path.home() / '.hermes' / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / 'proxy_guardian.log'
PID_FILE = Path.home() / '.hermes' / '.proxy_guardian.pid'
CONFIG = Path.home() / '.clash_config_new.yaml'
MIHOMO_BIN = '/usr/local/bin/mihomo'
MIHOMO_DIR = Path.home() / '.clash'
PROXY = 'http://127.0.0.1:7890'
API = 'http://127.0.0.1:9090'

FAIL_THRESHOLD = 3  # 连续失败次数
CHECK_INTERVAL = 30  # 秒


def log(msg):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line)
    with open(LOG_FILE, 'a') as f:
        f.write(line + '\n')


def check_process():
    """检查mihomo进程是否存在"""
    r = subprocess.run(['pgrep', '-f', 'mihomo'], capture_output=True, text=True, timeout=5)
    pids = [p.strip() for p in r.stdout.strip().split('\n') if p.strip()]
    return pids


def check_http_proxy():
    """检查代理端口是否响应（仅HTTP，HTTPS失败不算致命）"""
    try:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({'http': PROXY})
        )
        req = urllib.request.Request('http://www.gstatic.com/generate_204', method='HEAD')
        resp = opener.open(req, timeout=10)
        return resp.status == 204
    except Exception as e:
        log(f'  HTTP proxy check failed: {str(e)[:60]}')
        return False


def check_api():
    """检查Clash API是否响应"""
    try:
        req = urllib.request.Request(f'{API}/version')
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.status == 200
    except Exception:
        return False


def restart_proxy():
    """重启代理"""
    log('🔄 Restarting proxy...')
    # Kill existing
    subprocess.run(['pkill', '-f', 'mihomo'], timeout=10, capture_output=True)
    time.sleep(2)
    # Ensure killed
    pids = check_process()
    if pids:
        subprocess.run(['kill', '-9'] + [p for p in pids], timeout=5, capture_output=True)
        time.sleep(1)
    # Ensure binary exists (it was emptied somehow, restore from /tmp if needed)
    if not os.path.getsize(MIHOMO_BIN):
        log('  Binary was empty, restoring from /tmp backup')
        import shutil
        for src in ['/tmp/mihomo', '/tmp/mihomo-compat']:
            if os.path.exists(src) and os.path.getsize(src) > 1000000:
                shutil.copy2(src, MIHOMO_BIN)
                os.chmod(MIHOMO_BIN, 0o755)
                log(f'  Restored from {src}')
                break
    # Start
    cmd = [MIHOMO_BIN, '-d', str(MIHOMO_DIR), '-f', str(CONFIG)]
    log(f'  Starting: {" ".join(cmd)}')
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )
    time.sleep(5)
    # Verify
    pids = check_process()
    if pids:
        log(f'✅ Restarted successfully (PID: {pids[0]})')
        return True
    else:
        log('❌ Restart failed')
        return False


def cleanup():
    log('Shutting down Proxy Guardian')
    if PID_FILE.exists():
        PID_FILE.unlink()
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, lambda s, f: cleanup())
    signal.signal(signal.SIGTERM, lambda s, f: cleanup())

    # Write PID
    PID_FILE.write_text(str(os.getpid()))
    log('=' * 50)
    log('Proxy Guardian started')
    log(f'PID: {os.getpid()}')
    log(f'Config: {CONFIG}')
    log(f'Fail threshold: {FAIL_THRESHOLD}')
    log(f'Check interval: {CHECK_INTERVAL}s')
    log('=' * 50)

    fail_count = 0
    total_restarts = 0

    while True:
        try:
            proc_pids = check_process()
            api_ok = check_api()
            http_ok = check_http_proxy()

            status_parts = []
            if proc_pids:
                status_parts.append(f'PID:{",".join(proc_pids)}')
            else:
                status_parts.append('NO_PROCESS')

            status_parts.append(f'API:{"OK" if api_ok else "FAIL"}')
            status_parts.append(f'HTTP:{"OK" if http_ok else "FAIL"}')

            all_ok = bool(proc_pids) and api_ok and http_ok

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
                        # Failed to restart — keep trying but wait longer
                        log('  Will retry restart in 60s')
                        time.sleep(60)
                        continue

            time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            cleanup()
        except Exception as e:
            log(f'Error: {e}')
            time.sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    main()