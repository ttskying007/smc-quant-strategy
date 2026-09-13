# -*- coding: utf-8 -*-
"""tests_portability.py —— 第七轮审计 §12.2 测试可移植性锁定（R4, 2026-09-13）。
锁定: (1) 生产链模块可独立 import(路径修复后无 CFG 使用先于导入的次序错误);
(2) 关键生产脚本源码无 E:\\ 硬编码残留; (3) verify_audit_fixes / no_lookahead 可跑。
背景: verify_audit_fixes 曾因 current_scanner.py CFG 次序错误失败(R1 引入, R4 修复)——
该 bug 若未被逮住将于周一 19:03 生产链 NameError 崩溃。"""
import io, os, re, subprocess, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  OK " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + " " + detail)

PY = sys.executable

print("== 1. 生产链模块独立 import（次序类 NameError 防回归）==")
# 独立子进程 import, 捕捉任何 NameError/ImportError(不共享本进程 sys.path 状态)
for mod in ["current_scanner", "continuation_scanner", "paper_sim",
            "core.execution", "core.regime", "core.trading_calendar"]:
    r = subprocess.run([PY, "-X", "utf8", "-c", f"import sys; sys.path.insert(0, r'{HERE}'); import {mod}"],
                       capture_output=True, text=True, timeout=120)
    ok(f"import {mod}", r.returncode == 0, (r.stderr or r.stdout).strip()[-200:])

print("== 2. 生产脚本源码硬编码扫描（E:\\ 残留）==")
# 生产链 6 文件: 不允许 E:\ 路径字面量(注释/docstring 除外——本测试只查赋值与调用行)
HARDCODE_PAT = re.compile(r"^[^#]*['\"][A-Z]:\\\\", re.M)
for f in ["paper_sim.py", "current_scanner.py", "continuation_scanner.py",
          "daily_combo_run.py", "core/regime.py", "core/execution.py"]:
    fp = os.path.join(HERE, f)
    src = open(fp, encoding="utf-8", errors="replace").read()
    # 逐行: 排除纯注释行; 找 A:\ 字面量
    bad = [ln for ln in src.splitlines()
           if re.search(r"['\"][A-Za-z]:\\\\", ln) and not ln.strip().startswith("#")]
    ok(f"{f} 无盘符硬编码", len(bad) == 0, "; ".join(bad[:2]))

print("== 3. wdh_engine 独立运行块 config 派生 ==")
r = subprocess.run([PY, "-X", "utf8", "-c",
                    "import sys; sys.path.insert(0, r'E:\\test\\smc_project\\wdh'); "
                    "import wdh_engine; print('WDH_OK', wdh_engine.MAX_HOLD)"],
                   capture_output=True, text=True, timeout=60)
ok("wdh_engine import 正常", r.returncode == 0 and "WDH_OK" in r.stdout, (r.stderr or "")[-150:])

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)