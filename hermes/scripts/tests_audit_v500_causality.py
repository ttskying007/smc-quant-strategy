# -*- coding: utf-8 -*-
"""tests_audit_v500_causality.py —— 外部审计修复回归锁(2026-09).

修复来源: 外部审计报告(SMC 量化策略审计与重构) + 本工作区核实。
修复内容(v500_structural_backtest.py):
  ① collect_structural_tps: 仅收入场前(<=entry_idx)结构 —— 消除未来函数
  ② 元组索引: c[3]->c[2](source 在索引2), 排序 x[2]->x[3](按距离)
同时修复的编译阻断: run_v11_full.py(截断补全) / validate_skills.py(6处 f-string)

本测试固化:
  1. 未来函数: 入场后(>entry_idx)的结构不得作为 TP
  2. 入场前结构保留
  3. 元组结构正确: (bar_idx, price, source, distance_pct)
  4. 排序按距离(索引3)
  5. 编译阻断文件可编译(compileall 已证, 此处检查 ast 可解析)
"""
import ast
import importlib.util
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
PASS = FAIL = 0


def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  OK " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + " " + str(detail))


# ── 加载被测模块 ──
V500 = os.path.join(HERE, "v11", "v500_structural_backtest.py")
spec = importlib.util.spec_from_file_location("v500_audit", V500)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

print("== 1. 未来函数消除 ==")
swings = {"highs": [{"idx": 8, "price": 110.0},    # 入场前 -> 应保留
                    {"idx": 15, "price": 130.0}],  # 入场后 -> 必须排除
          "lows": []}
tps = m.collect_structural_tps([], 10, 100.0, swings, [])
future = [t for t in tps if t[0] > 10]
pre = [t for t in tps if t[0] <= 10]
ok("入场后(未来)结构被排除", len(future) == 0, future)
ok("入场前结构被保留", len(pre) == 1 and pre[0][0] == 8, pre)

print("== 2. 元组结构与排序 ==")
# 多个入场前 TP: 距离不同 -> 应按距离升序(索引3)
sw2 = {"highs": [{"idx": 6, "price": 103.0},   # dist 3%
                 {"idx": 8, "price": 110.0},   # dist 10%
                 {"idx": 9, "price": 106.0}],  # dist 6%
       "lows": []}
tps2 = m.collect_structural_tps([], 10, 100.0, sw2, [])
ok("返回按距离升序", all(tps2[i][3] <= tps2[i + 1][3] for i in range(len(tps2) - 1)),
   [(t[3], t[2]) for t in tps2])
ok("元组结构 (bar, price, source, dist)", all(len(t) == 4 for t in tps2), tps2)
ok("source 为字符串(索引2)", all(isinstance(t[2], str) for t in tps2), tps2)

print("== 3. 入场前 OB/FVG/CHOCH 结构作 TP ==")
# OB_Bull confirmed_at=9(入场前) -> 保留; confirmed_at=12(入场后) -> 排除
signals = [{"type": "OB_Bull", "upper": 112.0, "idx": 8, "confirmed_at": 9},
           {"type": "OB_Bull", "upper": 125.0, "idx": 10, "confirmed_at": 12}]
tps3 = m.collect_structural_tps([], 10, 100.0, {"highs": [], "lows": []}, signals)
ok("入场前 OB 保留", any(t[0] <= 10 and abs(t[1] - 112.0) < 1e-6 for t in tps3), tps3)
ok("入场后 OB 排除", not any(t[0] > 10 for t in tps3), tps3)

print("== 4. 编译阻断文件可解析 ==")
for f in ("run_v11_full.py", "validate_skills.py"):
    p = os.path.join(HERE, f)
    try:
        ast.parse(open(p, encoding="utf-8").read())
        ok("%s 可解析" % f, True)
    except SyntaxError as e:
        ok("%s 可解析" % f, False, e)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)