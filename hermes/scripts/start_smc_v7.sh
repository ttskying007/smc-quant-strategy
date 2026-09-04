#!/usr/bin/env python3
"""
SMC V7 + Proxy Guardian V4 统一启动器
========================================
一键启动：
  1. Proxy Guardian V4 (/tmp/proxy_guardian_v4.py)
  2. SMC WebUI 静态文件服务器 (port 8877)
  3. SMC V7 WebUI API (port 8878)
  4. V7 自动迭代器 (可选项, 背景运行)

日志目录: /root/.hermes/logs/
状态文件: /tmp/proxy_guardian_v4.json (供WebUI读取)
"""
import os, sys, subprocess, time, signal, json
from pathlib import Path
from datetime import datetime

HOME = Path.home()
SCRIPTS = HOME / '.hermes' / 'scripts'
LOGS = HOME / '.hermes' / 'logs'
LOGS.mkdir(parents=True, exist_ok=True)

PROCESSES = []

def log(msg):
    t = datetime.now().strftime('%H:%M:%S')
    print(f"[{t}] {msg}", flush=True)

def start(name, cmd, workdir=None, bg=True):
    """Start a process"""
    log(f"  Starting {name}: {' '.join(str(c) for c in cmd)}")
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=open(LOGS / f'{name}.log', 'a'),
            stderr=subprocess.STDOUT,
            start_new_session=True,
            cwd=workdir or str(SCRIPTS),
        )
        PROCESSES.append({'name': name, 'proc': proc, 'pid': proc.pid})
        log(f"  {name} started (PID: {proc.pid})")
        return proc
    except Exception as e:
        log(f"  {name} FAILED: {e}")
        return None

def is_alive(pid):
    try:
        with open(f'/proc/{pid}/stat') as f:
            return 'Z' not in f.read().split(' ')[2:3]
    except:
        return False

def stop_all():
    """Stop all processes"""
    log("\nStopping all services...")
    for p in reversed(PROCESSES):
        name, proc = p['name'], p['proc']
        if proc.poll() is None:
            log(f"  Stopping {name} (PID: {proc.pid})")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except:
                proc.kill()
                proc.wait(timeout=3)
    log("All services stopped")

def main():
    global PROCESSES

    log("=" * 55)
    log(f"  SMC V7 + Proxy Guardian V4 启动器")
    log("=" * 55)

    # Cleanup old zombies
    log("\n[Phase 0] Cleanup stale processes...")
    subprocess.run(['pkill', '-9', '-f', 'smc_web_server.py'], capture_output=True)
    subprocess.run(['pkill', '-9', '-f', 'smc_webui_api.py'], capture_output=True)
    subprocess.run(['pkill', '-9', '-f', 'proxy_guardian_v4.py'], capture_output=True)
    subprocess.run(['pkill', '-9', '-f', 'auto_iter_v7.py'], capture_output=True)
    time.sleep(2)
    # Kill zombie mihomo
    subprocess.run(['pkill', '-9', '-x', 'mihomo'], capture_output=True)
    time.sleep(1)
    log("  Cleanup complete")

    # Phase 1: Proxy Guardian V4
    log("\n[Phase 1] Proxy Guardian V4...")
    proxy_cmd = [sys.executable, str(SCRIPTS / 'proxy_guardian_v4.py')]
    proxy = start('proxy-g4', proxy_cmd)
    time.sleep(2)

    # Phase 2: SMC WebUI static server (port 8877)
    log("\n[Phase 2] SMC WebUI (port 8877)...")
    web_cmd = [sys.executable, str(HOME / 'hermes-webui' / 'scripts' / 'smc_web_server.py')]
    start('smc-webui-8877', web_cmd, workdir=str(HOME / 'hermes-webui'))

    # Phase 3: V7 API server (port 8878)
    log("\n[Phase 3] V7 WebUI API (port 8878)...")
    api_cmd = [sys.executable, str(SCRIPTS / 'smc_webui_api.py')]
    start('v7-api-8878', api_cmd)

    # Phase 4: V7 Auto-iteration (background, if not already running)
    log("\n[Phase 4] V7 Auto Iteration (background)...")
    iter_cmd = [
        sys.executable, str(SCRIPTS / 'auto_iter_v7.py'),
        '--iters', '100',
        '--stocks', '50',
    ]
    start('auto-iter-v7', iter_cmd)

    # Summary
    time.sleep(2)
    log("\n" + "=" * 55)
    log("  All services started!")
    log("=" * 55)
    log(f"  Proxy Guardian V4:  /tmp/proxy_guardian_v4.log")
    log(f"  SMC WebUI:         http://127.0.0.1:8877")
    log(f"  V7 API:            http://127.0.0.1:8878")
    log(f"  V7 迭代进度:        http://127.0.0.1:8878/api/progress")
    log(f"  V7 状态:           http://127.0.0.1:8878/api/status")
    log(f"  V7 参数:           http://127.0.0.1:8878/api/params")
    log(f"  V7 股票扫描:        http://127.0.0.1:8878/api/stock/600519.SH")
    log(f"\n  日志目录: {LOGS}")
    log(f"  查看迭代: tail -f {LOGS}/auto-iter-v7.log")
    log("\n 按 Ctrl+C 停止所有服务")

    try:
        while True:
            time.sleep(10)
            # Health check every 10s
            for p in PROCESSES[:]:
                if p['proc'].poll() is not None:
                    name, pid = p['name'], p['pid']
                    log(f"  WARNING: {name} (PID {pid}) has exited (code: {p['proc'].returncode})")
                    PROCESSES.remove(p)
                    if name == 'proxy-g4':
                        log("  Proxy died! Restarting...")
                        new = start('proxy-g4', proxy_cmd)
                    elif name == 'v7-api-8878':
                        log("  V7 API died! Restarting...")
                        new = start('v7-api-8878', api_cmd)
    except KeyboardInterrupt:
        stop_all()

if __name__ == '__main__':
    main()