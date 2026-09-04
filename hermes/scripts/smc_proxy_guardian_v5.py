#!/usr/bin/env python3
"""
SMC Proxy Guardian V5 — 与V7优化器深度整合
============================================
功能:
  1. 代理健康检查（进程+端口+外网）
  2. 自动重启（含订阅更新）
  3. 节点存活统计
  4. 与V7优化器共享状态目录
  5. 写状态文件供WebUI读取

日志: /tmp/smc_proxy_guardian.log
状态: ~/.hermes/smc_opt_v7/proxy_status.json
"""
import os, sys, time, json, subprocess, socket, logging, signal, threading
from pathlib import Path
from datetime import datetime

# === Config ===
MIHOMO_BIN = "/usr/local/bin/mihomo"
CLASH_CONFIG = os.path.expanduser("/home/lei/.clash_config_new.yaml")
CLASH_DIR = "/root/.clash/"
CHECK_INTERVAL = 60        # 60秒检查一次
RECOVERY_WAIT = 15          # 等待恢复
MAX_FAILURES = 3
LOG_FILE = "/tmp/smc_proxy_guardian.log"
PID_FILE = Path("/tmp/smc_proxy_guardian_v5.pid")

STATUS_DIRS = [
    Path.home() / '.hermes' / 'smc_opt_v7',
    Path.home() / '.hermes' / 'smc_opt_v8',
    Path.home() / '.hermes' / 'smc_opt_v82',
    Path.home() / '.hermes' / 'logs',
]
for d in STATUS_DIRS:
    d.mkdir(parents=True, exist_ok=True)
STATUS_FILES = [d / 'proxy_status.json' for d in STATUS_DIRS]

# === Logging ===
logging.basicConfig(
    level=logging.INFO, format='%(asctime)s [PG5] %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)])
log = logging.getLogger('pg5')

# === Status ===
status = {
    'running': False, 'pid': 0, 'port_ok': False, 'internet_ok': False,
    'all_ok': False, 'total_restarts': 0, 'alive_nodes': 0, 'total_nodes': 0,
    'last_check': None, 'uptime': None, 'errors': [],
}
status_lock = threading.Lock()

def write_status(**updates):
    global status
    with status_lock:
        status.update(updates)
        status['last_check'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for f in STATUS_FILES:
            try:
                f.write_text(json.dumps(status, ensure_ascii=False, indent=2))
            except: pass

def run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, '', 'timeout'
    except Exception as e:
        return -1, '', str(e)

def check_process():
    rc, out, _ = run(['pgrep', '-f', 'mihomo'])
    if rc == 0 and out:
        pid = out.split('\n')[0].strip()
        return True, pid
    return False, None

def check_port():
    rc, out, _ = run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}',
                       '--proxy', '127.0.0.1:7890', '--max-time', '3',
                       'http://www.gstatic.com/generate_204'])
    return out == '204'

def check_internet():
    targets = [('google.com', True), ('github.com', True), ('youtube.com', True)]
    results = {}
    for url, use_proxy in targets:
        if use_proxy:
            r = run(['curl', '-s', '-x', '127.0.0.1:7890', '-o', '/dev/null', '-w', '%{http_code}',
                     '--max-time', '5', url])
        else:
            r = run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}',
                     '--max-time', '5', url])
        ok = r[0] == 0 and r[1] in ('200', '301', '302')
        results[url] = ok
    return results

def check_nodes():
    """检查节点存活状态"""
    rc, out, _ = run(['curl', '-s', '--max-time', '3', 'http://127.0.0.1:9090/proxies'])
    if rc != 0 or not out:
        return None
    try:
        d = json.loads(out)
        proxies = d.get('proxies', {})
        nodes = [(n,p) for n,p in proxies.items()
                 if p.get('type') in ('Shadowsocks','VMess','Trojan','Hysteria2','Vless')]
        alive = sum(1 for n,p in nodes if p.get('alive', False))
        return {'total': len(nodes), 'alive': alive}
    except:
        return None

def full_check():
    results = {'process': False, 'port': False, 'internet': {}, 'nodes': None}
    results['process'], pid = check_process()
    results['port'] = check_port()
    results['internet'] = check_internet()
    results['nodes'] = check_nodes()

    all_ok = results['process'] and results['port'] and all(results['internet'].values())
    results['all_ok'] = all_ok

    write_status(
        running=results['process'], pid=pid if results['process'] else None,
        port_ok=results['port'], internet_ok=all_ok,
        all_ok=all_ok, connectivity=results['internet'],
        alive_nodes=(results['nodes'] or {}).get('alive', 0),
        total_nodes=(results['nodes'] or {}).get('total', 0),
    )

    log.info(f"Check: process={results['process']} port={results['port']} "
             f"internet={results['internet']} nodes={results['nodes']}")
    return results

def restart_proxy():
    log.warning("🔄 Restarting proxy...")
    run(['pkill', '-f', 'mihomo'])
    time.sleep(3)

    # 检查二进制
    if os.path.exists(MIHOMO_BIN) and os.path.getsize(MIHOMO_BIN) == 0:
        log.warning("  mihomo binary is 0 bytes, restoring from /tmp...")
        if Path('/tmp/mihomo').exists() and Path('/tmp/mihomo').stat().st_size > 0:
            run(['cp', '/tmp/mihomo', MIHOMO_BIN])
            run(['chmod', '+x', MIHOMO_BIN])
            log.info("  Restored mihomo binary from /tmp")

    # 检查配置文件
    if not os.path.exists(CLASH_CONFIG):
        log.warning("  Config not found, running sub hunter...")
        sub_hunter = Path.home() / '.hermes' / 'scripts' / 'clash_sub_hunter.py'
        if sub_hunter.exists():
            run([sys.executable, str(sub_hunter), '--download-only'], timeout=30)

    # 启动
    cmd = [MIHOMO_BIN, '-d', CLASH_DIR, '-f', CLASH_CONFIG]
    log.info(f"  Starting: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    time.sleep(RECOVERY_WAIT)

    # 验证
    results = full_check()
    if results['all_ok']:
        with status_lock:
            status['total_restarts'] += 1
        log.info("  ✅ Proxy restarted successfully")
        return True
    else:
        log.error("  ❌ Proxy restart failed")
        return False

def cleanup_zombies():
    """清理僵尸mihomo进程"""
    rc, out, _ = run(['ps', 'aux', '|', 'grep', 'mihomo', '|', 'grep', '-v', 'grep', '|', 'wc', '-l'])
    try:
        count = int(out)
        if count > 2:
            log.warning(f"  Found {count} mihomo processes, cleaning up...")
            run(['pkill', '-9', '-f', 'mihomo'])
            time.sleep(2)
    except: pass

def main_loop():
    """主循环"""
    log.info("=" * 50)
    log.info("SMC Proxy Guardian V5 starting...")
    log.info(f"Check interval: {CHECK_INTERVAL}s")
    log.info(f"Status files: {STATUS_FILES}")
    log.info("=" * 50)

    PID_FILE.write_text(str(os.getpid()))
    failure_count = 0
    start_time = time.time()

    while True:
        try:
            results = full_check()

            if results['all_ok']:
                failure_count = 0
                uptime = int(time.time() - start_time)
                write_status(uptime=uptime)
            else:
                failure_count += 1
                log.warning(f"  Failure {failure_count}/{MAX_FAILURES}")

                if failure_count >= MAX_FAILURES:
                    log.error("  ❌ Max failures reached, attempting recovery...")
                    cleanup_zombies()
                    restart_proxy()
                    failure_count = 0

        except Exception as e:
            log.error(f"  Error in check loop: {e}")

        time.sleep(CHECK_INTERVAL)

if __name__ == '__main__':
    main_loop()