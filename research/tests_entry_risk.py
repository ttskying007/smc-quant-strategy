# -*- coding: utf-8 -*-
"""core/entry.py + core/risk.py 单元测试（V2 ITERATION 7/8）"""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.entry import entry_zone, fill_in_zone
from core.risk import structured_tp_sl

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + detail)

def mk(closes, wick=0.1):
    out = []
    for i, c in enumerate(closes):
        o = closes[i-1] if i else c
        out.append({"t": f"202601{i+1:02d}", "o": o, "h": max(o, c) + wick,
                    "l": min(o, c) - wick, "c": c, "v": 1000})
    return out

print("== 1. entry_zone 几何 ==")
poi = {"low": 10.0, "high": 10.4, "mid": 10.2, "size_atr": 0.8}
z = entry_zone(poi, price=10.25, invalid_price=9.8, atr_pct=0.02)
ok("生成zone", z is not None)
if z:
    ok("zone区间=POI", z["zone_low"] == 10.0 and z["zone_high"] == 10.4)
    ok("optimal=mid", z["optimal_entry"] == 10.2)
    ok("invalid合法", z["invalid_price"] < z["zone_low"])
    ok("risk>0", z["risk_at_optimal"] > 0)
    ok("tp1=opt+risk", abs(z["tp1"] - (10.2 + z["risk_at_optimal"])) < 0.001)
    ok("entry_score 0-100", 0 <= z["entry_score"] <= 100)

print("== 2. late entry 识别(蓝图 §44) ==")
z_late = entry_zone(poi, price=11.5, invalid_price=9.8, atr_pct=0.02)
ok("现价远超zone→late_flag", z_late is not None and z_late["late_flag"], str(z_late))
z_near = entry_zone(poi, price=10.25, invalid_price=9.8, atr_pct=0.02)
ok("现价在zone附近→非late", not z_near["late_flag"])

print("== 3. 非法几何防御 ==")
ok("invalid>zone_low→自动回退", entry_zone({"low": 10.0, "high": 10.4, "mid": 10.2},
                                            price=10.2, invalid_price=10.5)["invalid_price"] < 10.0)
ok("zone倒挂→None", entry_zone({"low": 10.5, "high": 10.0}, 10.2, 9.5) is None)

print("== 4. fill_in_zone 撮合语义 ==")
# 序列: i 之后价格回落到 zone
closes = [10.8, 10.7, 10.6, 10.5, 10.4, 10.3, 10.25, 10.2, 10.15, 10.1,
          10.05, 10.0, 9.95, 10.02, 10.1, 10.3, 10.5, 10.8, 11.0, 11.2,
          11.4, 11.6, 11.8, 12.0]
bs = mk(closes)
i0 = 10  # 现价 10.05 附近, 决策点
z2 = entry_zone({"low": 10.0, "high": 10.4, "mid": 10.2}, price=10.05, invalid_price=9.5, atr_pct=0.02)
f = fill_in_zone(bs, i0, z2, max_bars=5)
ok("回落成交", f is not None and f["fill_price"] is not None, str(f))
if f and f["fill_price"]:
    ok("成交价在zone内", z2["zone_low"] - 0.01 <= f["fill_price"] <= z2["zone_high"] + 0.01, str(f["fill_price"]))
# 先破 invalid → 放弃
closes_bad = [10.8, 10.7, 10.6, 9.0, 8.5, 8.0, 7.5]
bs_bad = mk(closes_bad)
f_bad = fill_in_zone(bs_bad, 2, z2, max_bars=5)
ok("先破invalid→放弃", f_bad is not None and f_bad["mode"] == "INVALIDATED_BEFORE_FILL", str(f_bad))
# 5根内不回 zone → None(价格始终在 zone 上方, low > zone_high)
closes_up = [10.2, 10.9, 11.4, 11.9, 12.4, 12.9, 13.4, 13.9, 14.4, 14.9]
bs_up = mk(closes_up, wick=0.05)
# bar1: o=10.2 c=10.9 l=10.15 → 仍触 zone_high 10.4 → 用 i=1 起测(此时前bar已收10.9)
z_up = entry_zone({"low": 9.9, "high": 10.3, "mid": 10.1}, price=10.9, invalid_price=9.5, atr_pct=0.02)
f_up = fill_in_zone(bs_up, 1, z_up, max_bars=5)
ok("不回zone→None", f_up is None, str(f_up))

print("== 5. 无前视 ==")
bsA = mk(closes); bsB = mk(closes)
bsB[-1]["l"] = 1.0
zA = entry_zone(poi, 10.25, 9.8); zB = entry_zone(poi, 10.25, 9.8)
fA = fill_in_zone(bsA, 10, zA, 5); fB = fill_in_zone(bsB, 10, zB, 5)
ok("未来bar不影响撮合", (fA is None) == (fB is None) and (fA or fB) is not None)

print("== 6. structured_tp_sl ==")
# 长序列造 BSL 池(swing highs)
closes_long = [10.0, 10.3, 10.1, 10.4, 10.2, 10.5, 10.3, 10.6, 10.4, 10.7,
               10.5, 10.8, 10.6, 10.9, 10.7, 11.0, 10.8, 11.1, 10.9, 11.2,
               11.0, 11.3, 11.1, 11.4, 11.2, 11.5, 11.3, 11.6, 11.4, 11.7]
bs_long = mk(closes_long, wick=0.15)
iL = len(bs_long) - 1
z3 = entry_zone({"low": 11.3, "high": 11.5, "mid": 11.4}, price=11.42, invalid_price=10.9, atr_pct=0.02)
rs = structured_tp_sl(bs_long, iL, z3)
ok("生成结构化TP/SL", rs is not None)
if rs:
    ok("SL在invalid下方(缓冲)", rs["sl"] < z3["invalid_price"], f"{rs['sl']} vs {z3['invalid_price']}")
    ok("TP递增", rs["tp1"] < rs["tp2"] < rs["tp3"])
    ok("RR均>0.6", all(rs[k] > 0.6 for k in ("rr1", "rr2", "rr3")), str(rs))
    ok("ev_est存在", isinstance(rs["ev_est"], float))
    ok("RR1均值≥1(修TP偏近)", rs["rr1"] >= 1.0, str(rs["rr1"]))

print("== 7. 无池兜底(TP=fixed R) ==")
bs_flat = mk([10.0] * 40)
z4 = entry_zone({"low": 9.9, "high": 10.1, "mid": 10.0}, price=10.0, invalid_price=9.7, atr_pct=0.02)
rs4 = structured_tp_sl(bs_flat, 39, z4)
ok("无池兜底仍生成", rs4 is not None and rs4["tp1"] > z4["optimal_entry"])
if rs4:
    ok("兜底RR=1/2/3", (rs4["rr1"], rs4["rr2"], rs4["rr3"]) == (1.0, 2.0, 3.0), str(rs4))
    ok("structure_based=False", not rs4["structure_based"])

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)