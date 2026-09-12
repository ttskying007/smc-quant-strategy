# -*- coding: utf-8 -*-
"""v4_f7_armB60.py —— 最终版: F7 的 60m 数据源究竟是哪个缓存?
F7 实验脚本里读的路径 = 权威。查 v4 F7 脚本的 60m 路径 + 各候选缓存的新鲜度。"""
import glob, io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import subprocess
r = subprocess.run(["powershell", "-Command",
    "Get-ChildItem E:\\test\\smc_project\\research\\*.py | Select-String -Pattern 'kline_cache_60min|kline_cache_15min|60m' -List | Select-Object -First 8 Path"],
    capture_output=True, text=True, encoding="utf-8")
print(r.stdout)
# 各缓存新鲜度
for d in ("kline_cache_60min", "kline_cache_60min_baostock", "kline_cache_15min"):
    p = os.path.join(r"E:\test\smc_project\hermes", d)
    fs = glob.glob(os.path.join(p, "*.json"))
    if not fs:
        print(f"{d}: 0 文件")
        continue
    try:
        j = json.load(open(sorted(fs)[0], encoding="utf-8"))
        last = str(j[-1].get("t") or "")[:8]
        print(f"{d}: {len(fs)} 文件, 首文件末bar={last}")
    except Exception as e:
        print(f"{d}: {len(fs)} 文件, 读失败 {e}")