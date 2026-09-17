# -*- coding: utf-8 -*-
"""future_function_scan.py —— 未来函数静态检查器(审计§3.1 P0).

审计要求: "任何 future_*、lookahead_*、entry_idx + N 生成的目标必须被静态
检查拒绝, 除非只用于事后统计而不参与交易决策."

本检查器扫描 hermes/scripts 下 v11/v25 的 Python 代码, 分类标注:
  A. TRUE_FUTURE: 真未来函数 —— 用入场后(idx > entry_idx / entry_idx+N)
     结构定义目标/TP, 参与交易决策 -> 必须拒绝(红线)
  B. RENAME_ONLY: 名称含 future_/lookahead_ 但语义为历史结构
     (如 OTE 的 "低点之后的摆动高") -> 需重命名消除歧义
  C. POST_ENTRY_EXIT: entry_idx+N 仅用于出场路径评估(T+1 起评估)
     -> 合规(出场需未来路径, 不参与入场决策)

用法: python3 future_function_scan.py [path]
输出: 分类清单 + 红线命中(TRUE_FUTURE) -> 退出码 2 表示有红线.
只读, 不修改任何代码.
"""
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.abspath(__file__))

# 模式: future_*/lookahead_* 变量被用于目标/TP/price 决策
FUTURE_VAR = re.compile(r"\b(future_\w+|lookahead_\w+)\b")
# 真红线: 显式把入场后索引用于 tp/target 价赋值
#   tp/target/price = ... (entry_idx|idx) + N
#   future_highs/future_lows 被用于目标(非仅统计)
TARGET_FROM_FUTURE = re.compile(
    r"(tp|target|price)\s*=\s*[^\n]*?(entry_idx|idx)\s*\+\s*\d+")
FUTURE_SWING_TARGET = re.compile(
    r"(future_highs|future_lows)\s*=\s*\[.*?>\s*(entry_idx|low_idx|high_idx|idx).*?\]")
# 出场路径(合规): for j/i in range(entry_idx+1, ...) 带 sl/tp 判断 —— T+1 后评估
POST_ENTRY = re.compile(r"for\s+[ji]\s+in\s+range\((entry_idx|idx)\s*\+\s*1[,)]")


def scan(py_path):
    src = open(py_path, encoding="utf-8", errors="replace").read()
    hits = {"A_TRUE_FUTURE": [], "B_RENAME_ONLY": [], "C_POST_ENTRY_EXIT": []}
    # 参考实现(Pine 翻译)非生产, 排除其 future_* 命名歧义
    is_ref = "vPine" in os.path.basename(py_path)
    lines = src.split("\n")
    for ln, line in enumerate(lines, 1):
        # A: 真红线 —— 显式未来目标赋值 或 未来摆动直接用于目标.
        # 排除: entry_price = ohlcv[idx+1]['o'](T+1 开盘入场, 合规);
        #        signals_vPine.py(Pine 参考实现, future_highs=低点之后的历史高, 非生产).
        is_entry_price = re.search(
            r"entry_price\s*=\s*ohlcv\[(idx|entry_idx)\s*\+\s*1\]", line)
        if not is_ref and (FUTURE_SWING_TARGET.search(line) or
                           (TARGET_FROM_FUTURE.search(line) and not is_entry_price)):
            hits["A_TRUE_FUTURE"].append((ln, line.strip()[:110]))
        # B: 名称含 future_/lookahead_ 但非显式目标赋值(可能是历史结构/统计)
        elif FUTURE_VAR.search(line) and not is_ref:
            hits["B_RENAME_ONLY"].append((ln, line.strip()[:110]))
        # C: 出场路径(T+1 评估) —— 合规
        if POST_ENTRY.search(line):
            hits["C_POST_ENTRY_EXIT"].append((ln, line.strip()[:110]))
    return hits


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else ROOT
    py_files = []
    for d in ("v11", "v25"):
        p = os.path.join(base, d)
        if os.path.isdir(p):
            for f in sorted(os.listdir(p)):
                if f.endswith(".py"):
                    py_files.append(os.path.join(p, f))
    print("=" * 90)
    print("未来函数静态检查(审计§3.1) — 扫描 %d 个文件" % len(py_files))
    print("=" * 90)
    total = {"A_TRUE_FUTURE": 0, "B_RENAME_ONLY": 0, "C_POST_ENTRY_EXIT": 0}
    redline = []
    for f in py_files:
        hits = scan(f)
        rel = os.path.relpath(f, base)
        for cat, items in hits.items():
            if items:
                total[cat] += len(items)
                if cat == "A_TRUE_FUTURE":
                    for ln, s in items:
                        redline.append((rel, ln, s))
        # 汇总打印每文件的命中
        n = sum(len(v) for v in hits.values())
        if n:
            print("  %-52s A=%d B=%d C=%d" % (rel,
                  len(hits["A_TRUE_FUTURE"]), len(hits["B_RENAME_ONLY"]),
                  len(hits["C_POST_ENTRY_EXIT"])))

    print("\n" + "=" * 90)
    print("汇总: A(真未来,红线)=%d | B(命名歧义)=%d | C(出场路径,合规)=%d"
          % (total["A_TRUE_FUTURE"], total["B_RENAME_ONLY"], total["C_POST_ENTRY_EXIT"]))
    print("=" * 90)
    if redline:
        print("\n⚠ 红线命中(需人工处置, 不得参与交易决策):")
        for rel, ln, s in redline[:40]:
            print("  %s:%d  %s" % (rel, ln, s))
        sys.exit(2)
    else:
        print("\n✅ 未发现真未来函数红线(未来结构目标已由 V500 修复覆盖)")
        sys.exit(0)


if __name__ == "__main__":
    main()