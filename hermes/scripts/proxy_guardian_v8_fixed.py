#!/usr/bin/env python3
"""
Proxy Guardian V8 Fixed — 全自动Mihomo代理监控守护进程 (修复版)
===========================================================

修复的核心问题:
1. 不再硬编码CONFIG路径, 而是自动检测当前运行的配置
2. 优先尝试API节点切换, 避免不必要地重启进程
3. 优雅处理重启, 避免暴力kill导致API接口中断
4. 正确的配置路径传递
"""
import os, sys, json, time, socket, subprocess, urllib.request, logging, signal
from logging.handlers import RotatingFileHandler
from pathlib import Path

HOME = Path.home()
SCRIPTS_DIR = HOME / '.hermes' / 'scripts'
LOGS_DIR = HOME / '.hermes' / 'logs'
CLASH_DIR = str(HOME / '.clash')

OUT_DIRS = [
    HOME / '.hermes' / 'smc_web_v2',
    HOME / '.hermes' / 'smc_opt_v83',
    HOME / '.hermes' / 'smc_opt_v7',
    LOGS_DIR,
]

CHECK_INTERVAL = 30
MAX_FAIL_BEFORE_RESTART = 2
MAX_RESTART_RETRIES = 3
MIHOMO_API = 'http://127.0.0.1:9090'
PROXY_URL = 'http://127.0.0.1:7890'

LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ---- Logging ----
logger = logging.getLogger('proxy_guardian_v8_fixed')
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(str(LOGS_DIR / 'proxy_guardian_v8_fixed.log'),
                              maxBytes=10*1024*1024, backupCount=5)
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s',
                              datefmt='%Y-%m-%d %H:%M:%S')
handler.setFormatter(formatter)
logger.addHandler(handler)
console = logging.StreamHandler()
console.setFormatter(formatter)
logger.addHandler(console)

class ProxyGuardianV8Fixed:
    def __init__(self):
        self.fail_count = 0
        self.total_restarts = 0
        self.last_restart_time = None
        self.running = True
        self.current_config = self._get_current_config()
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame):
        logger.info(f"收到信号 {signum}, 正在退出...")
        self.running = False

    def _get_current_config(self):
        """自动检测当前运行的mihomo配置路径"""
        try:
            r = subprocess.run(['pgrep', '-f', 'mihomo'],
                             capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                pid = r.stdout.strip().split('\n')[0]
                with open(f'/proc/{pid}/cmdline', 'rb') as f:
                    cmdline = f.read().decode('utf-8', errors='replace').replace('\x00', ' ')
                import re
                m = re.search(r'-f\s+(\S+)', cmdline)
                if m:
                    config = m.group(1)
                    dm = re.search(r'-d\s+(\S+)', cmdline)
                    workdir = dm.group(1) if dm else str(HOME / '.clash')
                    if not config.startswith('/'):
                        config = os.path.join(workdir, config)
                    if os.path.exists(config):
                        return config
        except Exception as e:
            logger.warning(f"检测配置路径异常: {e}")
        return None

    # ---- 检测层 ----

    def check_process(self):
        """检测mihomo进程"""
        try:
            r = subprocess.run(['pgrep', '-f', 'mihomo'],
                             capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                pids = r.stdout.strip().split('\n')
                return True, pids[0]
            return False, None
        except Exception as e:
            logger.warning(f"进程检测异常: {e}")
            return False, None

    def check_port(self):
        """检测7890端口"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            result = s.connect_ex(('127.0.0.1', 7890))
            s.close()
            return result == 0
        except:
            return False

    def check_http(self, url='https://www.gstatic.com/generate_204', timeout=5):
        """通过代理检测HTTP连通性, 返回 (ok, latency_ms)"""
        try:
            proxy_handler = urllib.request.ProxyHandler({'http': PROXY_URL, 'https': PROXY_URL})
            opener = urllib.request.build_opener(proxy_handler)
            start = time.time()
            with opener.open(url, timeout=timeout) as resp:
                elapsed = (time.time() - start) * 1000
                return resp.status == 204 or resp.status == 200, elapsed
        except Exception:
            return False, 0

    def check_connectivity(self):
        """三层连通性检测: gstatic -> google -> baidu"""
        ok, lat = self.check_http('https://www.gstatic.com/generate_204', 5)
        if ok:
            return {'ok': True, 'latency_ms': int(lat), 'method': 'gstatic'}

        ok2, lat2 = self.check_http('https://www.google.com', 5)
        if ok2:
            return {'ok': True, 'latency_ms': int(lat2), 'method': 'google'}

        ok3, lat3 = self.check_http('https://www.baidu.com', 5)
        return {
            'ok': False,
            'latency_ms': 0,
            'method': 'failed',
            'google_blocked': True,
            'baidu_blocked': not ok3,
            'gfw_suspected': True if ok3 else False,
            'diagnosis': 'GFW_BLOCKED' if ok3 else 'NETWORK_DOWN'
        }

    def query_mihomo(self, endpoint):
        """调用mihomo API"""
        try:
            req = urllib.request.Request(f"{MIHOMO_API}/{endpoint.lstrip('/')}")
            with urllib.request.urlopen(req, timeout=3) as resp:
                return json.loads(resp.read().decode())
        except:
            return None

    def get_proxy_groups(self):
        """获取代理组和当前选中节点, 返回 (name, now, all_nodes)"""
        proxies = self.query_mihomo('/proxies')
        if proxies and 'proxies' in proxies:
            for name, p in proxies.get('proxies', {}).items():
                if isinstance(p, dict) and 'now' in p and 'all' in p:
                    if p['all']:
                        return name, p.get('now'), p.get('all', [])
            return None, None, []
        return None, None, []

    def get_node_delays(self):
        """获取所有代理节点的延迟信息"""
        proxies = self.query_mihomo('/proxies') or {}
        node_delays = {}
        for name, p in proxies.get('proxies', {}).items():
            if isinstance(p, dict) and p.get('type') in ('Shadowsocks', 'VMess', 'Trojan', 'Hysteria2', 'VLESS', 'WireGuard'):
                history = p.get('history', [])
                delay = history[-1].get('delay', 0) if history else 0
                alive = p.get('alive', False)
                node_delays[name] = {'delay': delay, 'alive': alive}
        return node_delays

    def switch_node(self, group_name):
        """通过API切换到延迟最低的可用节点 — 不会中断API接口!"""
        if not group_name:
            return False

        _, _, all_nodes = self.get_proxy_groups()
        if not all_nodes:
            logger.warning("无可用节点")
            return False

        proxies = self.query_mihomo('/proxies') or {}
        node_delays = {}
        for n in all_nodes:
            info = proxies.get('proxies', {}).get(n, {})
            delay = info.get('history', [{}])[-1].get('delay', 99999) if info.get('history') else 99999
            alive = info.get('alive', False)
            if alive:
                node_delays[n] = delay

        if not node_delays:
            logger.warning("无存活节点可切换")
            return False

        chosen = min(node_delays, key=node_delays.get)
        current_delay = node_delays[chosen]

        if current_delay > 3000:
            logger.warning(f"最低延迟仍过高: {current_delay}ms")

        try:
            data = json.dumps({'name': chosen}).encode()
            req = urllib.request.Request(
                f"{MIHOMO_API}/proxies/{group_name}",
                data=data,
                headers={'Content-Type': 'application/json'},
                method='PUT'
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 204:
                    logger.info(f"✅ 切换到节点: {chosen} (延迟: {current_delay}ms)")
                    time.sleep(2)
                    return True
        except Exception as e:
            logger.warning(f"节点切换失败 ({chosen}): {e}")
        return False

    def restart_mihomo(self):
        """优雅重启mihomo — 使用正确的配置路径"""
        config = self.current_config
        if not config or not os.path.exists(config):
            config = str(HOME / '.clash' / 'config_bb.yaml')
            logger.warning(f"使用默认配置: {config}")

        logger.warning(f"🔄 正在重启 mihomo (配置: {config})...")

        try:
            subprocess.run(['pkill', '-15', '-f', 'mihomo'], capture_output=True, timeout=5)
            time.sleep(2)
            subprocess.run(['pkill', '-9', '-f', 'mihomo'], capture_output=True, timeout=3)
            time.sleep(1)
        except:
            pass

        for attempt in range(MAX_RESTART_RETRIES):
            logger.info(f"启动尝试 {attempt + 1}/{MAX_RESTART_RETRIES}...")
            try:
                cmd = ['mihomo', '-d', CLASH_DIR, '-f', config]
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(3)

                for retry in range(5):
                    time.sleep(1)
                    proc_ok, pid = self.check_process()
                    port_ok = self.check_port()
                    logger.info(f"  验证 {retry+1}: proc={proc_ok} port={port_ok}")
                    if proc_ok and port_ok:
                        logger.info(f"✅ 启动成功! PID={pid}")
                        self.current_config = config
                        self.total_restarts += 1
                        self.last_restart_time = time.time()
                        return True
            except Exception as e:
                logger.error(f"启动异常: {e}")

        logger.critical("❌ 启动完全失败!")
        return False

    def get_node_count(self):
        """获取节点存活/总数"""
        proxies = self.query_mihomo('/proxies')
        if not proxies or 'proxies' not in proxies:
            return 0, 0
        alive = 0
        total = 0
        for name, p in proxies.get('proxies', {}).items():
            if isinstance(p, dict) and p.get('type') in ('Shadowsocks', 'VMess', 'Trojan', 'Hysteria2', 'VLESS', 'WireGuard'):
                total += 1
                if p.get('alive', False) or (p.get('history') and p['history'][-1].get('delay', 0) > 0):
                    alive += 1
        return alive, total

    def write_status(self, state):
        """写入状态JSON"""
        status = {
            'running': state.get('process_ok', False),
            'pid': state.get('pid', ''),
            'process_ok': state.get('process_ok', False),
            'port_ok': state.get('port_ok', False),
            'internet_ok': state.get('internet_ok', False),
            'connectivity': state.get('connectivity', {}),
            'node_name': state.get('node_name', ''),
            'alive_nodes': state.get('alive_nodes', 0),
            'total_nodes': state.get('total_nodes', 0),
            'total_restarts': self.total_restarts,
            'last_restart_time': self.last_restart_time,
            'fail_count': self.fail_count,
            'current_config': self.current_config or state.get('current_config', ''),
            'last_check': time.strftime('%Y-%m-%d %H:%M:%S'),
            'timestamp': int(time.time()),
            'emergency': self.fail_count >= MAX_FAIL_BEFORE_RESTART * 2,
            'source': 'proxy_guardian_v8_fixed',
            'all_ok': all([state.get('process_ok', False), state.get('port_ok', False), state.get('internet_ok', False)]),
            'ok': all([state.get('process_ok', False), state.get('port_ok', False), state.get('internet_ok', False)]),
        }

        for d in OUT_DIRS:
            d.mkdir(parents=True, exist_ok=True)
            try:
                (d / 'proxy_status.json').write_text(json.dumps(status, indent=2))
            except Exception as e:
                logger.warning(f"写入 {d}/proxy_status.json 失败: {e}")

        if self.fail_count >= MAX_FAIL_BEFORE_RESTART * 2:
            emergency_file = HOME / '.hermes' / 'smc_web_v2' / 'proxy_emergency.json'
            emergency_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                emergency_file.write_text(json.dumps({
                    'time': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'fail_count': self.fail_count,
                    'total_restarts': self.total_restarts,
                    'message': '代理严重故障: 连续多次检测失败',
                }, indent=2))
            except:
                pass

        return status

    def run_once(self):
        """执行一轮完整检测"""
        state = {'process_ok': False, 'port_ok': False,
                 'internet_ok': False, 'pid': '', 'node_name': '',
                 'alive_nodes': 0, 'total_nodes': 0, 'connectivity': {},
                 'current_config': self.current_config or ''}

        self.current_config = self._get_current_config()
        state['current_config'] = self.current_config or ''

        proc_ok, pid = self.check_process()
        state['process_ok'] = proc_ok
        state['pid'] = pid or ''

        state['port_ok'] = self.check_port()

        conn = self.check_connectivity()
        state['internet_ok'] = conn['ok']
        state['connectivity'] = conn

        gname, gnow, gnodes = None, None, []
        try:
            gname, gnow, gnodes = self.get_proxy_groups()
        except ValueError:
            pass
        state['node_name'] = gnow or ''
        alive, total = self.get_node_count()
        state['alive_nodes'] = alive
        state['total_nodes'] = total

        all_ok = proc_ok and state['port_ok'] and conn['ok']
        if not all_ok:
            self.fail_count += 1
            logger.warning(f"⚠ 检测失败 (累计{self.fail_count}): "
                          f"proc={proc_ok} port={state['port_ok']} net={conn['ok']}")
            if not conn['ok'] and 'diagnosis' in conn:
                logger.warning(f"  诊断: {conn['diagnosis']}")
        else:
            self.fail_count = 0

        status = self.write_status(state)
        return status, all_ok

    def run(self):
        """主循环"""
        logger.info("=" * 50)
        logger.info("Proxy Guardian V8 Fixed 启动")
        logger.info(f"检测间隔: {CHECK_INTERVAL}s")
        logger.info(f"API接口: {MIHOMO_API}")
        logger.info(f"当前配置: {self.current_config or '待检测'}")
        logger.info(f"状态目录: {[str(d) for d in OUT_DIRS]}")
        logger.info("=" * 50)

        while self.running:
            try:
                status, all_ok = self.run_once()

                if all_ok:
                    logger.info(f"✅ 一切正常 | 节点: {status['alive_nodes']}/{status['total_nodes']} | "
                               f"当前: {status['node_name']}")
                else:
                    if self.fail_count >= MAX_FAIL_BEFORE_RESTART:
                        logger.warning(f"⚠ 连续{self.fail_count}次失败, 尝试恢复...")

                        group_name, _, _ = self.get_proxy_groups()
                        if group_name:
                            logger.info(f"🔄 尝试切换节点 (组: {group_name}) - 不会中断API接口!")
                            if self.switch_node(group_name):
                                logger.info("节点切换成功, 等待验证...")
                                time.sleep(3)
                                _, re_ok = self.run_once()
                                if re_ok:
                                    logger.info("✅ 节点切换后恢复正常")
                                    self.fail_count = 0
                                    continue

                        logger.warning("🔄 节点切换无效, 尝试优雅重启...")
                        if self.restart_mihomo():
                            logger.info("重启成功, 重新检测...")
                            time.sleep(3)
                            self.run_once()
                            self.fail_count = 0
                        else:
                            logger.critical("❌ 自动恢复完全失败!")

            except Exception as e:
                logger.error(f"检测异常: {e}", exc_info=True)

            for _ in range(CHECK_INTERVAL):
                if not self.running:
                    break
                time.sleep(1)

        logger.info("Proxy Guardian V8 Fixed 已停止")
        return self.write_status({
            'process_ok': False, 'port_ok': False,
            'internet_ok': False, 'pid': '', 'node_name': '',
            'alive_nodes': 0, 'total_nodes': 0, 'connectivity': {},
            'current_config': self.current_config or ''
        })

def show_status():
    """打印当前状态"""
    for d in OUT_DIRS:
        f = d / 'proxy_status.json'
        if f.exists():
            print(f.read_text())
            return
    print(json.dumps({'error': '无状态文件'}))

def single_check():
    guardian = ProxyGuardianV8Fixed()
    status, ok = guardian.run_once()
    print(json.dumps(status, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    if '--status' in sys.argv:
        show_status()
    elif '--single' in sys.argv:
        single_check()
    else:
        guardian = ProxyGuardianV8Fixed()
        guardian.run()
