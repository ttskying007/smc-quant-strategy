# -*- coding: utf-8 -*-
"""r38_industry_probe.py —— industry_map.json 结构与覆盖探明.

上一轮发现 industry_map.json (1.26MB, 5530 项) 是**唯一未接入特征集的真实新信息源**。
本轮检验行业维度假设: 内部人增持是否在行业内聚集, 聚集是否预测更优结果?

先探明结构: 元素形态 / 字段 / 覆盖 EVENT 959 个唯一 symbol 的比例。
纯诊断, 不修改生产。
"""
import csv
import io
import json
import os
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

IM = r"E:\test\smc_project\hermes\data\industry_map.json"
CSV = r"E:\test\smc_project\research\combo_v20f_trades.csv"

d = json.load(open(IM, encoding="utf-8"))
print("=" * 90)
print("industry_map.json 结构")
print("=" * 90)
print("顶层类型 = %s | 长度 = %d" % (type(d).__name__, len(d)))
print("\n前 3 个元素:")
for i, x in enumerate(d[:3]):
    print("  [%d] type=%s" % (i, type(x).__name__))
    if isinstance(x, dict):
        for k, v in x.items():
            sv = str(v)
            print("      %-16s = %s" % (k, sv[:80]))
    else:
        print("      %r" % (x,))

print("\n字段名汇总(前 200 元素):")
keys = Counter()
for x in d[:200]:
    if isinstance(x, dict):
        for k in x:
            keys[k] += 1
for k, n in keys.most_common():
    print("  %-20s %d" % (k, n))

# 覆盖核对
ev = [r for r in csv.DictReader(open(CSV, encoding="utf-8-sig")) if r.get("src") == "EVENT"]
syms = sorted({str(r["symbol"]).split(".")[0] for r in ev})
print("\n" + "=" * 90)
print("覆盖核对")
print("=" * 90)
print("EVENT 唯一 symbol = %d" % len(syms))

# 尝试多种可能的映射形态
code_field = None
ind_field = None
if d and isinstance(d[0], dict):
    for c in ("code", "symbol", "stock_code", "ts_code", "sec_code"):
        if c in d[0]:
            code_field = c
            break
    for c in ("industry", "industry_name", "sector", "sw_l1", "name"):
        if c in d[0]:
            ind_field = c
            break
print("推测 code 字段 = %r | industry 字段 = %r" % (code_field, ind_field))

if code_field:
    codes = set()
    for x in d:
        if isinstance(x, dict):
            codes.add(str(x.get(code_field) or "").split(".")[0][:6])
    hit = sum(1 for s in syms if s in codes)
    print("覆盖: %d / %d (%.1f%%)" % (hit, len(syms), 100 * hit / len(syms)))

if ind_field:
    ind = Counter(str(x.get(ind_field) or "?") for x in d if isinstance(x, dict))
    print("\n行业数 = %d | 最大行业:" % len(ind))
    for k, n in ind.most_common(12):
        print("  %-24s %d" % (k, n))