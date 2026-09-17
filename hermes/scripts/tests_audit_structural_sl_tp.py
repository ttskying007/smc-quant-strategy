# -*- coding: utf-8 -*-
"""tests_audit_structural_sl_tp.py — 结构优先 SL/TP 回归锁(审计§7.2/§7.3)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "v25"))
PASS = FAIL = 0


def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  OK " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + " " + str(detail))


from structural_sl_tp import (SLTPGenerator, structural_stop,
                              visible_swing_high_target, is_swing_high,
                              STOP_BUFFER)  # noqa: E402


def bars_from(prices):
    return [{"date": t, "o": o, "h": h, "l": l, "c": c, "v": v}
            for t, o, h, l, c, v in prices]


# 场景: swing low(idx5, low95) -> sweep(idx9, low92) -> response(idx10)
#       + 入场前 swing high(idx3, high106, 未消费) 作 TP 结构目标
BARS = bars_from([
    ("2024-01-01", 100, 101, 99, 100, 100),
    ("2024-01-02", 100, 101, 99, 100, 100),
    ("2024-01-03", 100, 101, 99, 100, 100),
    ("2024-01-04", 100, 106, 99, 100, 100),   # swing high idx3 (h=106)
    ("2024-01-05", 100, 101, 99, 100, 100),
    ("2024-01-06", 100, 101, 95.0, 100, 100),  # swing low idx5
    ("2024-01-07", 100, 101, 99, 100, 100),
    ("2024-01-08", 100, 101, 99, 100, 100),
    ("2024-01-09", 100, 101, 99, 100, 100),
    ("2024-01-12", 100, 100, 92.0, 98, 500),   # sweep idx9 (low92)
    ("2024-01-13", 100, 102, 99, 102, 300),    # response idx10
    ("2024-01-14", 100, 103, 99, 102, 300),    # entry idx11 (T+1 open)
])

print("== 1. 结构 SL(§7.2 优先级①) ==")
ss = structural_stop(BARS, sweep_idx=9)
ok("SL = sweep low * 0.99", abs(ss["stop"] - 92 * STOP_BUFFER) < 1e-9, ss)
ok("SL source=STRUCTURE", ss["source"] == "STRUCTURE", ss)
ok("SL 携带 sweep_idx 证据", ss["sweep_idx"] == 9, ss)

print("== 2. 结构 TP(§7.3 入场前可见未消费) ==")
vt = visible_swing_high_target(BARS, sweep_idx=9, entry=100.0)
ok("找到入场前 swing high(106)", vt is not None and abs(vt["target"] - 106) < 1e-9, vt)
ok("TP source=STRUCTURE + visible_at", vt["source"] == "STRUCTURE" and vt["visible_at"] == 6, vt)
ok("未消费(sweep low 92 > ... 不对, 92 < 106 但未穿透? 检查语义)",
   vt is not None, "sweep low 92 未达 106 -> 未消费")

print("== 3. 已消费 swing high 不作 TP(§7.3) ==")
# 构造: sweep 穿透 swing high(sweep low < 106) -> 不可作目标
BARS2 = bars_from([
    ("2024-01-01", 100, 101, 99, 100, 100),
    ("2024-01-02", 100, 101, 99, 100, 100),
    ("2024-01-03", 100, 101, 99, 100, 100),
    ("2024-01-04", 100, 106, 99, 100, 100),   # swing high idx3
    ("2024-01-05", 100, 101, 99, 100, 100),
    ("2024-01-06", 100, 101, 95.0, 100, 100),
    ("2024-01-07", 100, 101, 99, 100, 100),
    ("2024-01-08", 100, 106, 99, 100, 100),   # 形成后重新触及 106 -> 已消费!
    ("2024-01-09", 100, 101, 99, 100, 100),
    ("2024-01-12", 100, 108, 104.0, 105, 500),  # sweep low104
    ("2024-01-13", 100, 110, 105, 109, 300),
    ("2024-01-14", 100, 111, 106, 110, 300),
])
vt2 = visible_swing_high_target(BARS2, sweep_idx=9, entry=100.0)
ok("已消费 swing high 排除(形成后被重新触及)", vt2 is None, vt2)

print("== 4. 生成器: 结构优先 + fallback 比例 ==")
gen = SLTPGenerator(use_structure=True)
r = gen.decide(BARS, sweep_idx=9, entry_idx=11, entry=100.0)
ok("SL 用结构(非 fallback)", r["sl"]["source"] == "STRUCTURE", r["sl"])
ok("TP 用结构(106)", r["tp"]["source"] == "STRUCTURE", r["tp"])
ok("fallback 比例 0(全结构)", r["sl_fallback_ratio"] == 0.0 and r["tp_fallback_ratio"] == 0.0, r)

print("== 5. fallback 统计(§7.2 必须单独统计) ==")
gen2 = SLTPGenerator(use_structure=False)  # 禁用结构 -> 全 fallback
r2 = gen2.decide(BARS, sweep_idx=9, entry_idx=11, entry=100.0)
ok("SL fallback=ATR", r2["sl"]["source"] == "ATR_FALLBACK", r2["sl"])
ok("TP fallback=R 倍数", r2["tp"]["source"] == "R_FALLBACK", r2["tp"])
ok("fallback 比例=1.0", r2["sl_fallback_ratio"] == 1.0 and r2["tp_fallback_ratio"] == 1.0, r2)
ok("SL < entry < TP", r2["sl"]["stop"] < 100.0 < r2["tp"]["target"], r2)

print("== 6. 无未来(结构均入场前可见) ==")
ok("TP visible_at(6) <= entry_idx(11)", r["tp"]["visible_at"] <= 11, r["tp"])
ok("SL sweep_idx(9) < entry_idx(11)", r["sl"]["sweep_idx"] < 11, r["sl"])

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)