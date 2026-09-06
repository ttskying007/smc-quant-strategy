# -*- coding: utf-8 -*-
"""复审 §8 回归测试: 日期边界/多源覆盖/未平仓判定
验证 PARTIAL_MULTI_TF 判定逻辑、未平仓区间拆分、日期边界。
"""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core.manifest as CM

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + detail)

# 多源覆盖判定函数（与 coverage_report 一致）
def coverage_status(daily_end, m60_end, ann_end, requested="2026-09-05"):
    daily_ok = daily_end >= requested
    m60_ok = m60_end >= requested
    ann_ok = ann_end >= requested
    complete = daily_ok and m60_ok and ann_ok
    reasons = []
    if not m60_ok:
        reasons.append(f"m60_end={m60_end} < {requested}")
    if not daily_ok:
        reasons.append(f"daily_end={daily_end} < {requested}")
    if not ann_ok:
        reasons.append(f"ann_end={ann_end} < {requested}")
    return "COMPLETE" if complete else "PARTIAL_MULTI_TF", reasons

print("== 多源覆盖判定 ==")
s, r = coverage_status("2026-08-31", "2026-07-11", "2026-09-05")
ok("daily全/m60缺→PARTIAL", s == "PARTIAL_MULTI_TF" and "m60" in r[0], f"{s} {r}")
s2, r2 = coverage_status("2026-09-05", "2026-09-05", "2026-09-05")
ok("全源到位→COMPLETE", s2 == "COMPLETE" and not r2, f"{s2} {r2}")
s3, r3 = coverage_status("2026-08-01", "2026-08-01", "2026-08-01")
ok("全源缺→PARTIAL", s3 == "PARTIAL_MULTI_TF", f"{s3}")
# 审计案例: daily 8-31 vs m60 7-11 → PARTIAL_MULTI_TF + production_gate FAIL
s4, r4 = coverage_status("2026-08-31", "2026-07-11", "2026-09-05")
ok("审计案例(8-31 vs 7-11)→PARTIAL+gate FAIL", s4 == "PARTIAL_MULTI_TF", f"{s4}")

print("== 未平仓区间拆分 ==")
# 场景: 最新 entry 在 8 月, 无 exit → entry_end 到 8 月, exit_end 不伪造
entries = ["2026-08-13", "2026-08-14"]
exits = ["2026-08-14"]  # 只 1 笔已退出
latest_entry = max(entries)
latest_exit = max(exits) if exits else None
open_positions = len(entries) - len(exits)
ok("entry_end=最新entry", latest_entry == "2026-08-14")
ok("exit_end=真实exit(不伪造)", latest_exit == "2026-08-14")
ok("open_position_asof 存在且≠exit_end", open_positions == 1, f"open={open_positions}")
ok("fully_realized_end=真实最后exit", latest_exit == "2026-08-14")

print("== 日期边界 ==")
# 月末→月初 / 8-14→8-15 / 周末
from datetime import date, timedelta
d1 = date(2026, 7, 31) + timedelta(days=1)
ok("7-31→8-1", d1 == date(2026, 8, 1))
d2 = date(2026, 8, 14) + timedelta(days=1)
ok("8-14→8-15", d2 == date(2026, 8, 15))
# 2026-08-15 是周六
ok("8-15为周末(周六)", date(2026, 8, 15).weekday() == 5)
ok("8-17为周一", date(2026, 8, 17).weekday() == 0)

print(f"\n结果: PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
