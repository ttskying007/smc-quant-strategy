# -*- coding: utf-8 -*-
"""R9 audit: v20c contract == code (VWAP5%, MARKUP, low-vol, hold 10, structure support)"""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

checks = [
    ("VWAP 5%", "0.05", r"E:\test\smc_project\research\combo_v20c_run.py" if os.path.exists(r"E:\test\smc_project\research\combo_v20c_run.py") else r"E:\test\smc_project\research\v20c_finalize.py"),
    ("MARKUP 阶段", "MARKUP", r"E:\test\smc_project\research\v20c_finalize.py"),
    ("结构支撑", "sl_tmp * 1.01", r"E:\test\smc_project\research\v20c_finalize.py"),
    ("固定10日", "+ 10", r"E:\test\smc_project\research\v20c_finalize.py"),
    ("低波动", "vol20 < vmed", r"E:\test\smc_project\research\v20c_finalize.py"),
    ("事件ADX20", "adx < 20", r"E:\test\smc_project\research\combo_v18_run.py"),
    ("事件DEEP20/非15", "20 if deep else 15", r"E:\test\smc_project\research\combo_v18_run.py"),
]
for label, pat, path in checks:
    txt = open(path, encoding="utf-8", errors="replace").read()
    print(f"  [{'OK' if pat in txt else 'MISS'}] {label}: '{pat}' in {os.path.basename(path)}")
