# -*- coding: utf-8 -*-
"""v4_f7_refresh.py —— F7 armB 增量重放(60m 数据已修复到 0911)
复用 v2_f7_multitf 的判定链, 但窗口推到 09-11(上次跑到 09-04 附近 + 新增 5 交易日)。
目标: n≥100 → VALIDATION(预注册 #40 的 B2)。"""
import json, os, sys, io, time
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 直接调 v2_f7_multitf 的主函数(如果结构化) / 否则内联复制判定链
import importlib.util
spec = importlib.util.spec_from_file_location("f7", r"E:\test\smc_project\research\v2_f7_multitf.py")
print("读取 v2_f7_multitf.py 结构...")
src = open(r"E:\test\smc_project\research\v2_f7_multitf.py", encoding="utf-8").read()
print(f"长度 {len(src)} 字符")
print("头部 60 行:")
print("\n".join(src.splitlines()[:60]))