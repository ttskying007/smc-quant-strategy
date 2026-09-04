# -*- coding: utf-8 -*-
import json, io, os, sys, time
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

def mt(p):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(p))) if os.path.exists(p) else "不存在"

print("=== 主文件（research）vs 镜像（前端读取）===")
pairs = [
    ("paper_ledger.json", r"E:\test\smc_project\research\paper_ledger.json", r"E:\root\.hermes\smc_monitor\paper_ledger.json"),
    ("current_scanner_result.json", r"E:\test\smc_project\research\current_scanner_result.json", r"E:\root\.hermes\smc_monitor\current_scanner_result.json"),
    ("combo_dashboard.json", r"E:\test\smc_project\research\combo_dashboard.json", r"E:\root\.hermes\smc_monitor\combo_dashboard.json"),
]
for name, main, mirror in pairs:
    mm, mp = mt(main), mt(mirror)
    same = "✅" if mm == mp else "❌ 不同步"
    print(f"{name}: 主={mm} | 镜像={mp} {same}")

print("\n=== 前端读取的镜像内容 ===")
try:
    led = json.load(open(r"E:\root\.hermes\smc_monitor\paper_ledger.json", encoding="utf-8"))
    print(f"镜像 ledger: {len(led)} 笔 | 状态: {dict(Counter(t.get('status') for t in led))}")
    latest_sig = max([str(t.get('signal_date') or t.get('disclose_date') or '') for t in led])
    print(f"最新信号日期: {latest_sig}")
except Exception as e:
    print(f"镜像 ledger 读取失败: {e}")

try:
    s = json.load(open(r"E:\root\.hermes\smc_monitor\current_scanner_result.json", encoding="utf-8"))
    print(f"镜像 scanner: fresh={s.get('fresh_count')} coverage={s.get('coverage_pct')}% latest={s.get('latest_date')}")
except Exception as e:
    print(f"镜像 scanner 读取失败: {e}")
