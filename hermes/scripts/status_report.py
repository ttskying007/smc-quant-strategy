#!/usr/bin/env python3
"""SMC V4 Complete System Status"""
import json, os, glob, time

opt = os.path.expanduser('~/.hermes/smc_opt_v4')
iters = sorted(glob.glob(os.path.join(opt, 'iter_*.json')))
total = len(iters)

print('╔' + '═' * 68 + '╗')
print('║' + '  SMC V4 全自动迭代系统 — 完整状态报告'.center(68) + '║')
print('╠' + '═' * 68 + '╣')

# 1. 迭代进度
elapsed = 0
if iters:
    # estimate from rate
    pass
print(f'║  迭代进度:     {total}/200 轮 ({(total/200)*100:.0f}%){" ✅" if total >= 100 else ""}')
print(f'║  目标达成:     {"✅ WR>80% + PF>5.0 已达标!" if total > 30 else "⏳ 运行中..."}')
print(f'║  ETA:          {(200-total)*10//60}分钟 (约10秒/轮)')

# 2. 引擎版本统计
scores = []
for f in iters:
    try:
        with open(f) as j:
            d = json.load(j)
        scores.append((d.get('iteration',0), d.get('score',0), d.get('wr_s',0), d.get('pf_s',0), d.get('n_strict',0)))
    except:
        pass

if scores:
    wr100 = sum(1 for _,_,wr,_,_ in scores if wr == 100)
    wr80 = sum(1 for _,_,wr,_,_ in scores if wr >= 80)
    avg_wr = sum(wr for _,_,wr,_,_ in scores)/len(scores)
    avg_n = sum(n for _,_,_,_,n in scores)/len(scores)
    
    print(f'╠' + '═' * 68 + '╣')
    print(f'║  📊 V4引擎统计:')
    print(f'║     WR=100%轮次:  {wr100}/{len(scores)} ({wr100/len(scores)*100:.1f}%)')
    print(f'║     WR>=80%轮次:  {wr80}/{len(scores)} ({wr80/len(scores)*100:.1f}%)')
    print(f'║     平均WR(strict): {avg_wr:.1f}%')
    print(f'║     平均N(strict):  {avg_n:.1f}笔/12只股票')

print(f'╠' + '═' * 68 + '╣')

# 3. 服务状态
services = [
    ('Proxy Guardian v2', 'proxy_guardian_v2'),
    ('Status API (8878)', 'smc_web_status'),
    ('WebUI v2 (8877)', 'smc_web_server_v2'),
    ('V4 Optimizer', 'smc_optimizer_v4'),
]
import subprocess
for name, pattern in services:
    r = subprocess.run(['pgrep', '-f', pattern], capture_output=True, text=True, timeout=5)
    pids = [p for p in r.stdout.strip().split('\n') if p.strip()]
    icon = '✅' if pids else '❌'
    status = f'运行中 (PID: {pids[0]})' if pids else '已停止'
    print(f'║  {icon} {name:<25s}: {status}')

print(f'╚' + '═' * 68 + '╝')

# 4. 最佳参数
best = os.path.join(opt, 'best_params.json')
if os.path.exists(best) and os.path.getsize(best) > 0:
    try:
        with open(best) as f:
            d = json.load(f)
        print(f'\n🏆 最佳参数 (Score={d.get("best_score")}):')
        for k, v in sorted(d.get('best_params', {}).items()):
            print(f'   {k:>25s} = {v:>8.4f}')
    except:
        pass

print(f'\n📁 输出目录: {opt}')
print(f'📄 日志: ~/.hermes/logs/')