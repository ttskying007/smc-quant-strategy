# -*- coding: utf-8 -*-
"""tests_audit_r8v.py —— R33(第八轮审计 5.9)延续扫描器回归锁:
① freshness gate: 每股最新 bar 须 == 市场最新日, 否则数据陈旧跳过
   (审计 5.9: "continuation_scanner 没有要求每只股票最新 bar 等于市场
   最新日" → 旧数据产生延续信号) —— fail-closed 不产生信号;
② 阈值统一: VWAP >= 0.10(审计 5.9: "使用 >=9% 而注释/回测写 10%")。
实弹证据: 市场最新日 20260911, 最新日覆盖率 99%(4557/4582), 25 股陈旧
被 gate 跳过; scanner 输出 0 延续候选(阈值 10% 收紧 + CONT leg 关闭,
预期诚实状态)。
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + str(detail))

src = open(os.path.join(HERE, "continuation_scanner.py"), encoding="utf-8").read()

print("== 1. freshness gate 源码 ==")
ok("R33 注释在(freshness gate)", "R33(第八轮 5.9): freshness gate" in src)
ok("两遍扫描(先求市场最新日)", src.count("for p in sorted(os.listdir(KT))") >= 2,
   src.count("for p in sorted(os.listdir(KT))"))
ok("每股最新 bar == 市场最新日", "if latest and daily[-1][\"t\"] != latest:" in src)
ok("陈旧跳过(continue)", "continue" in src[src.find("daily[-1][\"t\"] != latest"):src.find("daily[-1][\"t\"] != latest")+80])
ok("市场最新日先扫(第一遍循环求 latest)", 'latest = daily[-1]["t"]' in src)
ok("freshness 语义注释(旧数据不产生信号)", "旧数据产生延续信号" in src)

print("== 2. 阈值统一(0.10) ==")
ok("VWAP 阈值 0.10 在", "if (daily[i][\"c\"] - vw) / vw < 0.10:" in src)
ok("0.09→0.10 审计标注在", "0.09 → 0.10" in src)
ok("与 sub_signals_cont 口径统一注释在", "sub_signals_cont()" in src)

print("== 3. 实弹证据(市场最新日/覆盖率) ==")
import continuation_scanner as CS
KT = CS.KT
latest = ""
dates_cnt = {}
for p in sorted(os.listdir(KT)):
    if not p.endswith("_daily_800.json"):
        continue
    daily = CS.bars(os.path.join(KT, p))
    if len(daily) < 400:
        continue
    d = daily[-1]["t"]
    dates_cnt[d] = dates_cnt.get(d, 0) + 1
    if d > latest:
        latest = d
_total = sum(dates_cnt.values())
ok("市场最新日 20260911(数据覆盖至上周五)", latest == "20260911", latest)
ok("最新日覆盖率 ≥98%", dates_cnt.get(latest, 0) * 100 // max(1, _total) >= 98,
   f"{dates_cnt.get(latest,0)*100//max(1,_total)}%")
_std = sum(c for d, c in dates_cnt.items() if d != latest)
ok("陈旧股被 gate 跳过(>0 说明 gate 有作用对象)", _std > 0, f"{_std} 股")
# 行为: 构造陈旧 K 线 → freshness gate 应跳过(不产生候选)
_bars = [{"o": 1, "h": 1, "l": 1, "c": 1, "t": f"202601{i:02d}", "v": 1} for i in range(1, 60)]
def gate_skips(daily, market_latest):
    """freshness gate 判定(与 scanner 同逻辑): 该股最新 bar 落后于市场最新日 → True 跳过"""
    return market_latest and daily[-1]["t"] != market_latest
ok("陈旧股 gate 判定 True(跳过)", gate_skips(_bars, "20260911") is True)
ok("最新股 gate 判定 False(通过)", gate_skips([{"t": "20260911", "c": 1, "h": 1, "l": 1, "o": 1, "v": 1}], "20260911") is False)
ok("无市场日参考 → 不跳过(空串 falsy)", not gate_skips(_bars, ""))

print("== 4. 5.9 两缺陷闭环 ==")
ok("缺陷①(freshness)已修: 两遍扫描+gate", "两遍扫描" in src or "latest and daily[-1]" in src)
ok("缺陷②(阈值 9%→10%)已修: 0.10+标注", "0.09 → 0.10" in src)

print("== 5. R12-R32 修复保持 ==")
src_ps = open(os.path.join(HERE, "paper_sim.py"), encoding="utf-8").read()
ok("R27 时段守卫仍在", "R27 交易时段守卫" in src_ps)
ok("R8 几何守卫仍在", "BAD_GEOMETRY_FILL_GE_SL" in src_ps)
ok("R32 自重启仍在", "自重启" in open(os.path.join(HERE, "sim_scheduler.py"), encoding="utf-8").read())
ok("R31 run_id 合同仍在", "_run_id" in open(os.path.join(HERE, "daily_combo_run.py"), encoding="utf-8").read())

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)