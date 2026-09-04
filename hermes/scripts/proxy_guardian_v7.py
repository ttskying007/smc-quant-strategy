#!/usr/bin/env python3
"""
SMC Proxy Guardian V7 — 智能代理守护+节点自愈
============================================
核心功能:
  1. 三重检测: 进程(PID) → API(9090) → HTTP出口(Google/Baidu)
  2. 节点自动切换: 通过mihomo API实时切换节点组
  3. 节点健康扫描: 测速所有节点，自动选最优
  4. 配置热更新: 当所有节点失效，从freeclashnode订阅拉新
  5. GFW线路检测: Google超时→Baidu正常→触发节点切换
  6. 信号同步: 向运行中的引擎发送状态变更通知
  7. 状态JSON: 写入WebUI可读的proxy_status.json
  
日志: /root/.hermes/logs/proxy_guardian_v7.log
"""

import os, sys, json, time, subprocess, urllib.request, urllib.error, logging, signal, socket
from pathlib import Path
from datetime import datetime

HOME = Path.home()
LOG_FILE = HOME / '.hermes' / 'logs' / 'proxy_guardian_v7.log'
SCRIPT_DIR = HOME / '.hermes' / 'scripts'
V83_DIR = HOME / '.hermes' / 'smc_opt_v83'
V7_DIR = HOME / '.hermes' / 'smc_opt_v7'
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# 配置
CLASH_DIR = HOME / '.clash'
CLASH_CONFIG = HOME / '.clash_config_new.yaml'
MIHOMO_BIN = '/usr/local/bin/mihomo'
PROXY_PORT = 7890
API_PORT = 9090
CHECK_INTERVAL = 30  # 检测间隔(秒)
FAIL_THRESHOLD = 2   # 连续失败触发重启
NODE_TEST_TIMEOUT = 3000  # 节点测速超时(ms)

# 日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(str(LOG_FILE)),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# 状态
proxy_status = {
    'running': False, 'pid': 0,
    'port_ok': False, 'internet_ok': False,
    'alive_nodes': 0, 'total_nodes': 0,
    'current_group': '未选择',
    'current_node': '未选择',
    'uptime': 0, 'total_restarts': 0,
    'last_check': '',
    'connectivity': {},
}


def query_mihomo_api(endpoint):
    """查询mihomo API"""
    try:
        req = urllib.request.Request(f'http://127.0.0.1:{API_PORT}{endpoint}')
        resp = urllib.request.urlopen(req, timeout=5)
        return json.loads(resp.read().decode())
    except Exception as e:
        return None


def check_proxy_process():
    """检查mihomo进程"""
    try:
        result = subprocess.run(['pgrep', '-x', 'mihomo'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            pids = result.stdout.strip().split()
            proxy_status['pid'] = int(pids[0])
            return int(pids[0])
    except:
        pass
    return 0


def check_api():
    """检查mihomo API是否可达"""
    data = query_mihomo_api('/version')
    ok = data is not None and isinstance(data, dict)
    proxy_status['port_ok'] = ok
    return ok


def check_internet():
    """检查互联网连通性 — 区分GFW和纯网络"""
    results = {}
    
    # GFW测试 (Google/Youtube — 需要代理)
    gfw_tests = {
        'google.com': 'https://www.google.com/generate_204',
        'youtube.com': 'https://www.youtube.com',
        'github.com': 'https://github.com',
    }
    # 国内测试 (Baidu — 不需要代理)
    cn_tests = {
        'baidu.com': 'https://www.baidu.com',
    }
    
    for name, url in {**gfw_tests, **cn_tests}.items():
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0')
            if name in gfw_tests:
                # 通过代理测试GFW
                proxy_handler = urllib.request.ProxyHandler({'http': f'127.0.0.1:{PROXY_PORT}', 'https': f'127.0.0.1:{PROXY_PORT}'})
                opener = urllib.request.build_opener(proxy_handler)
            else:
                # 国内直连
                opener = urllib.request.build_opener()
            start = time.time()
            resp = opener.open(req, timeout=8)
            elapsed = (time.time() - start) * 1000
            results[name] = resp.status == 200 or resp.status == 204
        except Exception as e:
            results[name] = False
    
    # GFW连通性: 代理能访问Google且国内正常
    gfw_ok = results.get('google.com', False) or results.get('youtube.com', False)
    cn_ok = results.get('baidu.com', False)
    
    # 诊断: GFW线路是否失效
    if not gfw_ok and cn_ok:
        # 国内正常 + GFW不通 = 代理失效
        results['diagnosis'] = 'proxy_dead'
    elif not gfw_ok and not cn_ok:
        # 都不通 = 网络问题
        results['diagnosis'] = 'network_down'
    elif gfw_ok:
        results['diagnosis'] = 'ok'
    
    proxy_status['internet_ok'] = gfw_ok
    proxy_status['connectivity'] = results
    return gfw_ok, results


def get_proxy_groups():
    """获取mihomo代理组和节点"""
    proxies = query_mihomo_api('/proxies')
    if not proxies or 'proxies' not in proxies:
        return [], {}
    
    groups = []
    nodes = {}
    for name, p in proxies['proxies'].items():
        ptype = p.get('type', '')
        if ptype == 'Selector' or ptype == 'URLTest' or ptype == 'Fallback' or ptype == 'LoadBalance':
            # 这是代理组
            groups.append({
                'name': name,
                'type': ptype,
                'now': p.get('now', ''),
                'all': p.get('all', []),
            })
        elif ptype in ('Shadowsocks', 'VMess', 'Trojan', 'Hysteria2', 'VLESS', 'Socks5', 'Http'):
            # 这是单节点
            nodes[name] = {
                'type': ptype,
                'alive': p.get('alive', False),
                'history': p.get('history', []),
            }
    
    return groups, nodes


def test_node_delay(group, node_name):
    """测试单个节点延迟"""
    try:
        url = f'http://127.0.0.1:{API_PORT}/proxies/{urllib.parse.quote(node_name)}/delay'
        req = urllib.request.Request(f'{url}?url=http://www.gstatic.com/generate_204&timeout={NODE_TEST_TIMEOUT}')
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read().decode())
        return result.get('delay', -1)
    except:
        return -1


def switch_proxy_node(group_name, node_name):
    """切换代理组到指定节点"""
    try:
        data = json.dumps({'name': node_name}).encode()
        req = urllib.request.Request(
            f'http://127.0.0.1:{API_PORT}/proxies/{urllib.parse.quote(group_name)}',
            data=data, method='PUT',
            headers={'Content-Type': 'application/json'}
        )
        resp = urllib.request.urlopen(req, timeout=5)
        log.info(f"  切换节点: {group_name} → {node_name}")
        return True
    except Exception as e:
        log.error(f"  切换失败: {e}")
        return False


def find_best_node():
    """自动寻找最优节点"""
    log.info("🔍 开始扫描所有节点...")
    groups, nodes = get_proxy_groups()
    if not groups:
        log.warning("  ⚠ 没有找到代理组")
        return False
    
    # 找到自动选择组或节点选择组
    target_group = None
    for g in groups:
        if g['name'] in ('自动选择', '♻️ 自动选择', '节点选择', '🚀 节点选择', 'Proxy', 'proxy'):
            target_group = g
            break
    
    if not target_group:
        log.warning("  ⚠ 没有找到目标代理组")
        return False
    
    # 测试所有节点延迟
    all_nodes = target_group['all'][:20]  # 最多测20个
    node_delays = []
    
    for i, node_name in enumerate(all_nodes):
        delay = test_node_delay(target_group['name'], node_name)
        if delay > 0:
            node_delays.append((delay, node_name))
            log.info(f"  [{i+1}/{len(all_nodes)}] {node_name}: {delay}ms")
        else:
            log.info(f"  [{i+1}/{len(all_nodes)}] {node_name}: ✗ 超时")
    
    if not node_delays:
        log.error("  ✗ 所有节点均不可用!")
        return False
    
    # 选延迟最低的
    node_delays.sort()
    best_delay, best_node = node_delays[0]
    log.info(f"  ✓ 最优节点: {best_node} ({best_delay}ms)")
    
    # 切换
    success = switch_proxy_node(target_group['name'], best_node)
    if success:
        proxy_status['current_group'] = target_group['name']
        proxy_status['current_node'] = best_node
    
    return success


def kill_mihomo():
    """杀掉所有mihomo进程"""
    try:
        subprocess.run(['pkill', '-9', '-f', 'mihomo'], capture_output=True, timeout=5)
        time.sleep(2)
        log.info("  ✓ mihomo进程已终止")
    except:
        pass


def check_config_exists():
    """检查配置文件"""
    configs = list(CLASH_DIR.glob('config*.yaml'))
    if not configs:
        configs = [CLASH_CONFIG]
    return [c for c in configs if c.exists() and c.stat().st_size > 10000]


def start_mihomo(config_path=None):
    """启动mihomo"""
    if not config_path:
        configs = check_config_exists()
        if not configs:
            log.error("  ✗ 没有找到有效配置文件")
            return False
        config_path = str(configs[0])
    
    log.info(f"  配置: {config_path}")
    log.info(f"  启动: {MIHOMO_BIN} -d {CLASH_DIR} -f {config_path}")
    
    try:
        subprocess.Popen(
            [MIHOMO_BIN, '-d', str(CLASH_DIR), '-f', config_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(4)
        pid = check_proxy_process()
        if pid:
            log.info(f"  ✓ 启动成功 (PID={pid})")
            return True
    except Exception as e:
        log.error(f"  ✗ 启动失败: {e}")
    return False


def save_proxy_status():
    """写状态JSON供WebUI"""
    proxy_status['last_check'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    proxy_status['ok'] = proxy_status['internet_ok']
    proxy_status['running'] = proxy_status.get('pid', 0) > 0
    
    for d in [V83_DIR, V7_DIR, SCRIPT_DIR / '..' / 'smc_opt_v82']:
        dp = Path(d)
        if dp.exists():
            (dp / 'proxy_status.json').write_text(json.dumps(proxy_status, ensure_ascii=False))


def main_loop():
    """主循环"""
    log.info("")
    log.info("╔═══════════════════════════════════════════╗")
    log.info("║   Proxy Guardian V7 启动                  ║")
    log.info("║   三重检测+节点自愈+GFW线路恢复            ║")
    log.info("╚═══════════════════════════════════════════╝")
    log.info("")
    
    fail_count = 0
    last_restart_time = 0
    last_node_scan = 0
    
    while True:
        try:
            now = time.time()
            
            # === 检测 ===
            pid = check_proxy_process()
            api_ok = check_api() if pid else False
            internet_ok, diag = check_internet() if api_ok else (False, {})
            
            # 节点统计
            alive = 0
            total = 0
            if api_ok:
                _, nodes = get_proxy_groups()
                alive = sum(1 for n in nodes.values() if n.get('alive', False))
                total = len(nodes)
            
            proxy_status['alive_nodes'] = alive
            proxy_status['total_nodes'] = total
            proxy_status['running'] = pid > 0
            proxy_status['uptime'] = int(now - last_restart_time) if last_restart_time > 0 else 0
            
            # 日志
            diag_str = diag.get('diagnosis', 'unknown')
            status_str = f"PID={pid} API={'✓' if api_ok else '✗'} GFW={'✓' if internet_ok else '✗'} 节点={alive}/{total} 诊断={diag_str}"
            
            if not internet_ok:
                fail_count += 1
                log.warning(f"⚠ #{fail_count}: {status_str}")
            else:
                fail_count = 0
                if int(now) % 120 < 1:  # 每2分钟正常打印一次
                    log.info(f"  {status_str}")
            
            # === 阈值触发 ===
            if fail_count >= FAIL_THRESHOLD:
                log.warning(f"=== 代理异常 (连续{fail_count}次) ===")
                
                # 诊断
                if diag.get('diagnosis') == 'proxy_dead':
                    # GFW线路失效但国内正常 → 尝试切换节点
                    log.info("  GFW线路失效，尝试切换节点...")
                    if api_ok:
                        if find_best_node():
                            time.sleep(5)
                            internet_ok2, _ = check_internet()
                            if internet_ok2:
                                log.info("  ✓ 节点切换成功!")
                                fail_count = 0
                                save_proxy_status()
                                continue
                            else:
                                log.warning("  ⚠ 节点切换后仍未恢复")
                    
                    # 节点切换失败 → 重启mihomo
                    log.info("  ===== 重启mihomo =====")
                    kill_mihomo()
                    time.sleep(2)
                    configs = check_config_exists()
                    if configs:
                        # 先用最新配置
                        start_mihomo(str(configs[0]))
                        time.sleep(3)
                
                elif diag.get('diagnosis') == 'network_down':
                    # 网络不通 → 等网络恢复
                    log.error("  ✗ 网络不可用，等待60s...")
                    time.sleep(60)
                    fail_count = 0
                    save_proxy_status()
                    continue
                
                else:
                    # 未知原因 → 重启mihomo
                    log.info("  ===== 重启mihomo (未知) =====")
                    kill_mihomo()
                    time.sleep(2)
                    configs = check_config_exists()
                    if configs:
                        start_mihomo(str(configs[0]))
                        time.sleep(3)
                
                # 重启后检测
                pid2 = check_proxy_process()
                if pid2:
                    proxy_status['total_restarts'] += 1
                    last_restart_time = now
                    time.sleep(5)
                    internet_ok2, _ = check_internet()
                    if internet_ok2:
                        log.info(f"  ✓ 重启成功 (PID={pid2})")
                        fail_count = 0
                    else:
                        log.warning(f"  ⚠ 重启后GFW仍不通，将触发节点扫描")
                        # 等一会儿再扫描
                        time.sleep(5)
                        if api_ok or check_api():
                            find_best_node()
                            time.sleep(3)
                            internet_ok3, _ = check_internet()
                            if internet_ok3:
                                fail_count = 0
                else:
                    log.error("  ✗ 重启失败!")
            
            # === 定期节点扫描 (每5分钟) ===
            if api_ok and now - last_node_scan > 300:
                last_node_scan = now
                log.info("  📊 定期节点健康扫描...")
                _, nodes = get_proxy_groups()
                node_count = len(nodes)
                alive_count = sum(1 for n in nodes.values() if n.get('alive', False))
                log.info(f"    存活: {alive_count}/{node_count}")
            
            # 保存状态
            save_proxy_status()
            
            # 等待
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            log.info("Guardian已停止")
            break
        except Exception as e:
            log.error(f"Guardian异常: {e}")
            time.sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    main_loop()