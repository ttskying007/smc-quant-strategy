#!/usr/bin/env python3
"""
Proxy Guardian V6 — 全自动代理监控守护进程
============================================
功能 (与V3/V5对比):
  1. 三重检测: 进程/端口/HTTP连通性
  2. 自动重启: pkill + 重新拉起mihomo
  3. 持续重试: 最多3次重启尝试, 每次间隔5秒
  4. 状态写入JSON: 供WebUI前端读取
  5. 日志轮转: 每10MB自动切割
  6. 守护心跳: 每60秒检测一次
  7. 失败通知: 如果连续3次重启失败, 写入紧急状态
  8. 兼容V7/V8/V83所有版本

进程名: proxy_guardian_v6.py
日志: ~/.hermes/logs/proxy_guardian_v6.log
状态: ~/.hermes/smc_opt_v7/proxy_status.json
       ~/.hermes/smc_opt_v82/proxy_status.json
       ~/.hermes/smc_opt_v83/proxy_status.json

用法:
  python3 proxy_guardian_v6.py         # 前台运行
  nohup python3 proxy_guardian_v6.py & # 后台运行
"""

import os, sys, time, json, subprocess, urllib.request, logging, logging.handlers, signal
from pathlib import Path
from datetime import datetime

# ════════ 配置 ════════
HOME = Path.home()
LOG_DIR = HOME / '.hermes' / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / 'proxy_guardian_v6.log'

MILO_BIN = '/usr/local/bin/mihomo'
CONFIG_FILE = HOME / '.clash_production.yaml'
WORK_DIR = HOME / '.clash_new'

# 状态文件 (同步到所有SMC版本目录)
STATUS_FILES = [
    HOME / '.hermes' / 'smc_opt_v7' / 'proxy_status.json',
    HOME / '.hermes' / 'smc_opt_v7plus' / 'proxy_status.json',
    HOME / '.hermes' / 'smc_opt_v82' / 'proxy_status.json',
    HOME / '.hermes' / 'smc_opt_v83' / 'proxy_status.json',
]

# ════════ 日志 ════════
logger = logging.getLogger('proxy_guardian_v6')
logger.setLevel(logging.DEBUG)

# 文件handler
fh = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=5)
fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
logger.addHandler(fh)

# 控制台handler
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S'))
logger.addHandler(ch)

# ════════ 检测 ════════

def check_process() -> tuple[bool, str]:
    """检查1: mihomo进程是否存在"""
    try:
        # Use os.popen as fallback for maximum compatibility
        p = os.popen('pgrep -f mihomo 2>/dev/null')
        output = p.read().strip()
        rc = p.close()
        if output:
            pids = [x for x in output.split('\n') if x.strip()]
            return True, f"PID={','.join(pids[:3])}{'...' if len(pids)>3 else ''}"
        return False, "no mihomo process"
    except Exception as e:
        return False, f"process check error: {e}"

def check_api() -> tuple[bool, str]:
    """检查2: mihomo API端口9090"""
    try:
        req = urllib.request.Request('http://127.0.0.1:9090', method='GET')
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                return True, f"API 200"
            return False, f"API status={resp.status}"
    except urllib.request.URLError as e:
        return False, f"API error: {e.reason}"
    except Exception as e:
        return False, f"API error: {e}"

def check_http_connectivity() -> tuple[bool, float]:
    """检查3: 通过代理访问外网"""
    proxy = urllib.request.ProxyHandler({'http': '127.0.0.1:7890', 'https': '127.0.0.1:7890'})
    opener = urllib.request.build_opener(proxy)
    try:
        t0 = time.time()
        req = urllib.request.Request('http://www.gstatic.com/generate_204', method='GET')
        with opener.open(req, timeout=8) as resp:
            latency = (time.time() - t0) * 1000
            if resp.status == 204:
                return True, round(latency, 1)
            return False, 0
    except Exception:
        return False, 0

# ════════ 操作 ════════

def kill_proxy():
    """杀掉所有mihomo进程"""
    subprocess.run(['pkill', '-9', '-f', 'mihomo'], timeout=5,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)

def start_proxy() -> bool:
    """启动mihomo代理"""
    if not CONFIG_FILE.exists():
        logger.error(f"Config not found: {CONFIG_FILE}")
        return False
    if not MILO_BIN:
        logger.error(f"Binary not found: {MILO_BIN}")
        return False

    try:
        proc = subprocess.Popen(
            [MILO_BIN, '-d', str(WORK_DIR), '-f', str(CONFIG_FILE)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(3)
        if proc.poll() is None:
            logger.info(f"Proxy started (PID={proc.pid})")
            return True
        else:
            logger.error(f"Proxy exited immediately (rc={proc.returncode})")
            return False
    except Exception as e:
        logger.error(f"Start failed: {e}")
        return False

def restart_proxy() -> bool:
    """完整的重启流程"""
    logger.warning("Restarting proxy...")
    kill_proxy()
    time.sleep(2)
    return start_proxy()

# ════════ 状态写入 ════════

def write_status(ok: bool, proc_msg: str, api_msg: str, latency: float, restart_count: int, consecutive_failures: int, api_ok: bool = False, http_ok: bool = False):
    """写入状态JSON到所有SMC版本目录"""
    status = {
        'all_ok': ok,
        'proxy_ok': ok,
        'running': ok,
        'process': proc_msg,
        'pid': proc_msg,
        'api': api_msg,
        'port_7890': api_ok,
        'port_9090': api_ok,
        'port_ok': api_ok,
        'internet_ok': http_ok,
        'connectivity': {
            'ok': http_ok,
            'latency_ms': latency,
        },
        'latency_ms': latency,
        'restart_count': restart_count,
        'total_restarts': restart_count,
        'consecutive_failures': consecutive_failures,
        'fail_count': consecutive_failures,
        'uptime_seconds': 0,
        'uptime': 0,
        'alive_nodes': 0,
        'total_nodes': 0,
        'last_check': time.strftime('%Y-%m-%d %H:%M:%S'),
        'checked_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'timestamp': int(time.time()),
    }

    for f in STATUS_FILES:
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            with open(f, 'w') as fp:
                json.dump(status, fp, ensure_ascii=False)
        except Exception:
            pass

# ════════ 主循环 ════════

def main():
    logger.info("=" * 60)
    logger.info("Proxy Guardian V6 — 启动")
    logger.info(f"  Config: {CONFIG_FILE}")
    logger.info(f"  Binary: {MILO_BIN}")
    logger.info(f"  Status: {len(STATUS_FILES)} targets")
    logger.info("=" * 60)

    restart_count = 0
    consecutive_failures = 0
    check_interval = 60  # 60秒检测一次
    max_consecutive_failures = 3

    # 首次检测
    time.sleep(5)

    while True:
        try:
            # --- 三重检测 ---
            proc_ok, proc_msg = check_process()
            api_ok, api_msg = check_api()
            http_ok, latency = check_http_connectivity()

            proxy_ok = proc_ok and api_ok and http_ok

            if proxy_ok:
                logger.info(f"✓ {proc_msg} | {api_msg} | latency={latency}ms")
                consecutive_failures = 0
                write_status(True, proc_msg, api_msg, latency, restart_count, consecutive_failures, api_ok, http_ok)
            else:
                # 收集所有失败原因
                failures = []
                if not proc_ok: failures.append(f"proc({proc_msg})")
                if not api_ok: failures.append(f"api({api_msg})")
                if not http_ok: failures.append(f"http(timeout)")
                logger.warning(f"✗ {' / '.join(failures)}")

                consecutive_failures += 1

                # 写入紧急状态
                write_status(False, proc_msg, api_msg, latency, restart_count, consecutive_failures, api_ok, http_ok)

                if consecutive_failures >= max_consecutive_failures:
                    logger.critical(f"连续{consecutive_failures}次检测失败! 写入紧急状态...")
                    for f in STATUS_FILES:
                        try:
                            with open(f.with_name('proxy_emergency.json'), 'w') as fp:
                                json.dump({
                                    'emergency': True,
                                    'consecutive_failures': consecutive_failures,
                                    'last_ok': time.strftime('%Y-%m-%d %H:%M:%S'),
                                    'restart_count': restart_count,
                                }, fp)
                        except:
                            pass
                    # 强制更短间隔
                    check_interval = 30

                # --- 尝试重启 (最多3次) ---
                for attempt in range(3):
                    logger.warning(f"重启尝试 {attempt+1}/3...")
                    time.sleep(2)
                    restart_proxy()
                    time.sleep(3)

                    # 重新检查
                    proc_ok2, proc_msg2 = check_process()
                    api_ok2, api_msg2 = check_api()
                    http_ok2, latency2 = check_http_connectivity()

                    if proc_ok2 and api_ok2 and http_ok2:
                        restart_count += 1
                        consecutive_failures = 0
                        check_interval = 60
                        logger.info(f"✓ 重启成功 (第{restart_count}次)")
                        write_status(True, proc_msg2, api_msg2, latency2, restart_count, consecutive_failures, api_ok2, http_ok2)
                        break
                else:
                    logger.error("✗ 3次重启均失败")

        except Exception as e:
            logger.error(f"检测异常: {e}", exc_info=True)
            write_status(False, f"error: {e}", "", 0, restart_count, consecutive_failures)

        # 等待下一次检测
        time.sleep(check_interval)

    # 正常退出
    for f in STATUS_FILES:
        try:
            with open(f, 'w') as fp:
                json.dump({'proxy_ok': False, 'status': 'shutdown', 'timestamp': int(time.time())}, fp)
        except:
            pass

    logger.info("Proxy Guardian V6 — 停止")

if __name__ == '__main__':
    main()