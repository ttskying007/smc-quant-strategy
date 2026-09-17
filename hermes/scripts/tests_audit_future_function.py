# -*- coding: utf-8 -*-
"""tests_audit_future_function.py —— 未来函数静态检查回归锁(审计§3.1 P0).

审计要求: 任何 future_*、lookahead_*、entry_idx + N 生成的目标必须被静态
检查拒绝(除非只用于事后统计).

交付物: future_function_scan.py —— 全库静态检查器, 分类 A/B/C.
本测试固化:
  1. 检查器运行且无 A(真未来)红线
  2. 检查器可重复(确定性)
  3. 已修复文件(V500)不含未来结构目标
  4. 构造一个真未来函数样例 -> 检查器必须识别(A>=1) —— 证明检查器有效
"""
import io
import os
import subprocess
import sys

# 注: 不重定向 stdout(-X utf8 已保证 UTF-8), 避免 Windows buffer 关闭问题
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


SCANNER = os.path.join(HERE, "future_function_scan.py")
PY = sys.executable

print("== 1. 全库扫描无真未来红线 ==")
r = subprocess.run([PY, "-X", "utf8", SCANNER],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
out = r.stdout + r.stderr
ok("检查器 exit=0(无 A 红线)", r.returncode == 0, "rc=%s" % r.returncode)
ok("输出含汇总行", "汇总: A" in out, out[-200:])
ok("输出无 '红线命中' 段(若 A>0 会出现)", "红线命中" not in out or "未发现" in out)

print("== 2. 检查器可重复(确定性) ==")
r2 = subprocess.run([PY, "-X", "utf8", SCANNER],
                    capture_output=True, text=True, encoding="utf-8", errors="replace")
sum1 = [l for l in out.split("\n") if "汇总:" in l]
sum2 = [l for l in (r2.stdout + r2.stderr).split("\n") if "汇总:" in l]
ok("两次运行汇总一致", sum1 == sum2, (sum1, sum2))

print("== 3. 构造真未来样例 -> 检查器必须识别 ==")
import importlib.util  # noqa: E402
import tempfile  # noqa: E402
sample = (
    "def f(ohlcv, entry_idx, swings):\n"
    "    future_highs = [(j, p) for j, p in swings['highs'] if j > entry_idx]\n"
    "    if future_highs:\n"
    "        target = future_highs[0][1]  # 未来摆动高作目标(红线)\n"
    "    return target\n"
)
tmp = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8")
tmp.write(sample)
tmp.close()
# 直接调用检查器的 scan()(单文件), 而非 subprocess(只扫 v11/v25 目录)
spec = importlib.util.spec_from_file_location("ffs", SCANNER)
ffs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ffs)
hits = ffs.scan(tmp.name)
a_hits = hits["A_TRUE_FUTURE"]
ok("样例被识别为红线(A>=1)", len(a_hits) >= 1, a_hits)
os.unlink(tmp.name)

print("== 4. V500 已修复文件无未来结构目标 ==")
src = open(os.path.join(HERE, "v11", "v500_structural_backtest.py"),
           encoding="utf-8").read()
ok("V500 collect_structural_tps 用 <= entry_idx(已修复)",
   "sh['idx'] <= entry_idx" in src or "<= entry_idx" in src)
ok("V500 无 '> entry_idx' 未来收集",
   "sh['idx'] > entry_idx" not in src)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)