# -*- coding: utf-8 -*-
"""tests_audit_r8f.py —— R17(第八轮审计 5.8) CONT 回测因果修复回归锁:
① signal 日口径(VWAP/vol20 不含 entry 日数据);
② 逐日滚动截面 V_MED(不再用当前文件末端阈值回看历史);
③ 阈值 0.10 统一;
④ 旧泄漏版本与新版产物分离(旧 CSV 数字不再作为 OOS 证据)。
"""
import os, sys, csv

HERE = os.path.dirname(os.path.abspath(__file__))
PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + str(detail))

src = open(os.path.join(HERE, "gen_cont_v20f.py"), encoding="utf-8").read()

print("== 1. 5.8①: signal 日口径 ==")
ok("VWAP 窗 [i-19, i](signal 日止)", "for k in range(i - 19, i + 1)" in src)
ok("vol20 窗 [i-20, i)(不含 entry)", "w20 = daily[i - 20:i]" in src)
ok("旧 entry 日 VWAP 已移除", "range(entry_idx - 19, entry_idx + 1)" not in src)
ok("旧 entry 日 vol20 已移除", "daily[entry_idx - 20:entry_idx]" not in src)

print("== 2. 5.8②: 逐日滚动截面 V_MED ==")
ok("按 signal 日分组", 'by_day[c["signal_date"]].append(c)' in src)
ok("滚动中位数(该日及以前)", "_running.extend(by_day[d])" in src and "vmed_by_day" in src)
ok("旧全局末端 V_MED 已移除", "vols.sort()" not in src and "V_MED = vols[" not in src)
ok("阈值按日取", 'c["vol20"] >= vmed_by_day[d]' in src)

print("== 3. 5.8③: 阈值统一 ==")
ok("VWAP 阈值 0.10", "vw_gap < 0.10" in src)
ok("旧 0.09 已移除", "< 0.09" not in src)

print("== 4. 产物分离与语义保持 ==")
ok("退出语义保持(10日收盘−0.2)", 'daily[entry_idx + 10]["c"]' in src and "- 0.20" in src)
ok("阶段1存退出收盘(单遍历消除索引不一致)", '"exit_c": daily[entry_idx + 10]["c"]' in src)
ok("输出文件名保持(前端兼容)", "cont_v20f_new.csv" in src)
# 实跑产物
_p = os.path.join(HERE, "cont_v20f_new.csv")
ok("cont_v20f_new.csv 存在", os.path.exists(_p))
if os.path.exists(_p):
    rows = [r for r in csv.DictReader(open(_p, encoding="utf-8-sig")) if r.get("net_pnl_pct") not in (None, "", "None")]
    ok("产物非空(R17 实跑 334 笔)", len(rows) > 300, len(rows))
    _dates = sorted(r["entry_date"] for r in rows)
    ok("覆盖 2023-09 起", _dates[0] >= "20230901", _dates[0])
    ok("src 全 CONT", all(r["src"] == "CONT" for r in rows))
    _nets = [float(r["net_pnl_pct"]) for r in rows]
    _avg = sum(_nets) / len(_nets)
    ok("avg 与实跑一致(±0.01)", abs(_avg - 5.37) < 0.01, _avg)

print("== 5. R12-R16 修复保持 ==")
src_ps = open(os.path.join(HERE, "paper_sim.py"), encoding="utf-8").read()
ok("leg_flags 仍在", '"leg_flags"' in src_ps)
ok("_market_proxy(code, d8) 仍在", "def _market_proxy(code, d8=None)" in src_ps)
ok("CAPACITY_REJECT gate 仍在", '"stage": "CAPACITY_REJECT"' in src_ps)
ok("shadow_replay 存在", os.path.exists(os.path.join(HERE, "shadow_replay.py")))

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)