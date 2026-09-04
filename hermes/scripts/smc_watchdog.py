#!/usr/bin/env python3
"""
SMC Watchdog — 全自动看门狗系统
===================================
集成管理:
  1. Proxy Guardian v2 (代理监控)
  2. SMC V4 Optimizer (优化器)
  3. Web Status API (状态API)
  4. 自动重启/恢复机制

用法:
  python3 smc_watchdog.py                   # 启动所有服务
  python3 smc_watchdog.py --status          # 查看状态
  python3 smc_watchdog.py --stop            # 停止所有服务
  python3 smc_watchdog.py --restart-opt     # 重启优化器
"""

import subprocess, time, sys, os, json, signal
from datetime import datetime
from pathlib import Path

LOG_DIR = Path.home() / '.hermes' / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / 'smc_watchdog.log'
PID_DIR = Path.home() / '.hermes'
PID_FILE = PID_DIR / '.smc_watchdog.pid'

SCRIPTS_DIR = os.path.expanduser('~/.hermes/scripts')

# 管理的子进程
SERVICES = {
    'proxy_guardian': {
        'script': 'proxy_guardian_v2.py',
        'pid_file': PID_DIR / '.proxy_guardian_v2.pid',
        'check_cmd': ['pgrep', '-f', 'proxy_guardian_v2.py'],
        'restart_delay': 5,
    },
    'status_api': {
        'script': 'smc_web_status_api.py',
        'pid_file': None,  # 通过端口检查
        'check_port': 8878,
        'restart_delay': 3,
    },
}

OPTIMIZER = {
    'script': 'smc_optimizer_v4.py',
    'pid_file': None,
    'check_cmd': ['pgrep', '-f', 'smc_optimizer_v4.py'],
}


def log(msg):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def check_process(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    return [p for p in r.stdout.strip().split('\n') if p.strip()]


def check_port(port):
    r = subprocess.run(['ss', '-tlnp'], capture_output=True, text=True, timeout=5)
    return str(port) in r.stdout


def start_service(name, config):
    """启动一个服务"""
    script_path = os.path.join(SCRIPTS_DIR, config['script'])
    if not os.path.exists(script_path):
        log(f'  ❌ Script not found: {script_path}')
        return False
    
    log(f'  🚀 Starting {name}...')
    proc = subprocess.Popen(
        ['python3', script_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        cwd=SCRIPTS_DIR,
    )
    
    # 等待启动
    time.sleep(config.get('restart_delay', 3))
    
    # 验证
    if 'check_cmd' in config:
        pids = check_process(config['check_cmd'])
        if pids:
            log(f'  ✅ {name} started (PID: {pids[0]})')
            return True
    elif 'check_port' in config:
        if check_port(config['check_port']):
            log(f'  ✅ {name} started (port: {config["check_port"]})')
            return True
    
    log(f'  ⚠ {name} may have started (check logs)')
    return True


def stop_service(name, config):
    """停止一个服务"""
    if 'check_cmd' in config:
        pids = check_process(config['check_cmd'])
        for pid in pids:
            try:
                subprocess.run(['kill', pid], timeout=5)
                log(f'  Stopped {name} (PID: {pid})')
            except:
                pass
    elif 'check_port' in config:
        # 通过ss找PID
        r = subprocess.run(['ss', '-tlnp'], capture_output=True, text=True, timeout=5)
        for line in r.stdout.split('\n'):
            if str(config['check_port']) in line and 'pid=' in line:
                import re
                m = re.search(r'pid=(\d+)', line)
                if m:
                    try:
                        subprocess.run(['kill', m.group(1)], timeout=5)
                        log(f'  Stopped {name} (PID: {m.group(1)})')
                    except:
                        pass


def start_optimizer(iterations=200, stocks=12):
    """启动V4优化器"""
    if check_process(OPTIMIZER['check_cmd']):
        log('Optimizer already running, skipping')
        return
    
    log(f'  🚀 Starting V4 Optimizer ({iterations} iterations, {stocks} stocks/iter)...')
    
    script_path = os.path.join(SCRIPTS_DIR, OPTIMIZER['script'])
    with open(LOG_DIR / 'v4_optimizer.log', 'a') as logfile:
        logfile.write(f"\n{'='*60}\n")
        logfile.write(f"Started at: {datetime.now()}\n")
        logfile.write(f"{'='*60}\n")
        
        proc = subprocess.Popen(
            ['python3', script_path, '--iterations', str(iterations), '--stocks', str(stocks)],
            stdout=logfile,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            cwd=SCRIPTS_DIR,
        )
    
    log(f'  ✅ Optimizer started (PID: {proc.pid})')
    return proc


def stop_optimizer():
    """停止优化器"""
    pids = check_process(OPTIMIZER['check_cmd'])
    for pid in pids:
        # 先发SIGTERM，等5秒再发SIGKILL
        try:
            subprocess.run(['kill', pid], timeout=5)
            log(f'Sent SIGTERM to optimizer PID: {pid}')
        except:
            pass
    
    time.sleep(3)
    pids = check_process(OPTIMIZER['check_cmd'])
    for pid in pids:
        try:
            subprocess.run(['kill', '-9', pid], timeout=5)
            log(f'Sent SIGKILL to optimizer PID: {pid}')
        except:
            pass


def get_status():
    """获取所有服务状态"""
    status = {}
    
    for name, config in SERVICES.items():
        running = False
        if 'check_cmd' in config:
            running = bool(check_process(config['check_cmd']))
        elif 'check_port' in config:
            running = check_port(config['check_port'])
        status[name] = {'running': running}
    
    # 优化器
    opt_running = bool(check_process(OPTIMIZER['check_cmd']))
    status['optimizer'] = {'running': opt_running}
    
    # 代理
    proxy_file = PID_DIR / 'logs' / 'proxy_status.json'
    if proxy_file.exists():
        try:
            proxy_status = json.load(open(proxy_file))
            status['proxy_ok'] = proxy_status.get('all_ok', False)
        except:
            status['proxy_ok'] = False
    
    return status


def print_status():
    """打印状态"""
    status = get_status()
    
    print(f"\n{'='*60}")
    print(f"  SMC Watchdog Status")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    
    for name, s in status.items():
        if isinstance(s, dict):
            status_icon = '✅' if s.get('running') else '❌'
            print(f"  {status_icon} {name}: {'Running' if s.get('running') else 'Stopped'}")
        elif isinstance(s, bool):
            icon = '✅' if s else '❌'
            print(f"  {icon} {name}: {'OK' if s else 'Down'}")
    
    # 检查优化进度
    opt_dir = Path.home() / '.hermes' / 'smc_opt_v4'
    if opt_dir.exists():
        iter_files = list(opt_dir.glob('iter_*.json'))
        best_file = opt_dir / 'best_params.json'
        print(f"\n  📊 V4 Optimizer Progress:")
        print(f"     Iterations completed: {len(iter_files)}")
        if best_file.exists() and os.path.getsize(best_file) > 0:
            try:
                data = json.load(open(best_file))
                print(f"     Best Score: {data.get('best_score', 'N/A')}")
                print(f"     Best WR_s: {data.get('best_wr_s', 'N/A')}%")
                print(f"     Best PF_s: {data.get('best_pf_s', 'N/A')}")
            except:
                print(f"     (best_params.json unreadable)")
    
    print(f"\n  Logs:")
    print(f"     Watchdog: {LOG_FILE}")
    print(f"     Proxy:    {LOG_DIR}/proxy_guardian_v2.log")
    print(f"     Optimizer: {LOG_DIR}/v4_optimizer.log")
    print(f"     Status API: port 8878")
    print(f"{'='*60}\n")


def main_loop():
    """主看门狗循环"""
    signal.signal(signal.SIGINT, lambda s, f: cleanup())
    signal.signal(signal.SIGTERM, lambda s, f: cleanup())
    
    # PID
    PID_FILE.write_text(str(os.getpid()))
    
    log('=' * 50)
    log('🚀 SMC Watchdog started')
    log(f'PID: {os.getpid()}')
    log('=' * 50)
    
    # 启动所有服务
    log('\n📋 Starting services...')
    for name, config in SERVICES.items():
        if 'check_cmd' in config:
            if not check_process(config['check_cmd']):
                start_service(name, config)
        elif 'check_port' in config:
            if not check_port(config['check_port']):
                start_service(name, config)
    
    log('\n✅ All services started')
    log(f'Status API: http://localhost:8878/api/status')
    
    # 主监控循环 (每60秒检查一次)
    check_interval = 60
    while True:
        try:
            time.sleep(check_interval)
            
            # 检查所有服务
            for name, config in SERVICES.items():
                running = False
                if 'check_cmd' in config:
                    running = bool(check_process(config['check_cmd']))
                elif 'check_port' in config:
                    running = check_port(config['check_port'])
                
                if not running:
                    log(f'⚠ {name} is DOWN, restarting...')
                    start_service(name, config)
            
            # 检查优化器
            opt_running = bool(check_process(OPTIMIZER['check_cmd']))
            if not opt_running:
                log('⚠ Optimizer is DOWN (may have completed or crashed)')
                # 检查是否有新结果
                opt_dir = OPT_DIR = Path.home() / '.hermes' / 'smc_opt_v4'
                iter_files = list(opt_dir.glob('iter_*.json'))
                log(f'  Last completed: {len(iter_files)} iterations')
        
        except KeyboardInterrupt:
            cleanup()
        except Exception as e:
            log(f'Error: {e}')
            import traceback
            traceback.print_exc()


def cleanup():
    log('\n\nShutting down SMC Watchdog...')
    if PID_FILE.exists():
        PID_FILE.unlink()
    log('Goodbye!')
    sys.exit(0)


if __name__ == '__main__':
    if '--status' in sys.argv:
        print_status()
    elif '--stop' in sys.argv:
        log('Stopping all services...')
        for name, config in SERVICES.items():
            stop_service(name, config)
        stop_optimizer()
        log('All services stopped')
    elif '--restart-opt' in sys.argv:
        stop_optimizer()
        time.sleep(2)
        start_optimizer(200, 12)
    elif '--start-opt' in sys.argv:
        start_optimizer(200, 12)
    else:
        main_loop()