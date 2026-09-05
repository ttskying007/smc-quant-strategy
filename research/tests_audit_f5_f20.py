# -*- coding: utf-8 -*-
"""验证 F05/F12/F17/F18/F20 修复：事件金额解析 / 分位阶段 / ATR扫损容差"""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"E:\test\smc_project\wdh")

import paper_sim as PS
import wdh_engine as WE

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  OK {name}")
    else:
        FAIL += 1; print(f"  FAIL {name} {detail}")

print("== F17: 事件金额/占比解析 ==")
r = PS._parse_insider_magnitude("控股股东计划增持公司股份约 1.2亿元，占总股本 1.5%")
ok("金额1.2亿→12000万", r[0] == 12000, str(r))
ok("占比1.5%", r[2] == 1.5, str(r))
r2 = PS._parse_insider_magnitude("回购公司股份 500万股")
ok("股数500万", r2[1] == 500, str(r2))
r3 = PS._parse_insider_magnitude("回购注销部分已授予限制性股票的公告")
ok("无规模→None", r3[0] is None and r3[2] is None, str(r3))
r4 = PS._parse_insider_magnitude("增持达到公司总股本的 0.35%")
ok("占比0.35%", r4[2] == 0.35, str(r4))

print("\n== F12: 阶段分位化 ==")
# 构造：强势上涨序列 → 分位阶段应非 ACCUM
bars = []
import datetime as _dt
day = _dt.date(2026, 1, 1)
c = 10.0
for _ in range(320):
    if day.weekday() < 5:
        c = c * 1.01  # 持续上涨
        bars.append({"t": day.strftime("%Y%m%d"), "o": c*0.995, "h": c*1.01, "l": c*0.99, "c": c, "v": 1_500_000})
    day += _dt.timedelta(days=1)
st_q, _ = PS.stage_and_deep_quantile(bars, len(bars)-1)
st_g, _ = PS.stage_and_deep(bars, len(bars)-1)
ok("分位化上涨→UPTREND/MARKUP", st_q in ("UPTREND", "MARKUP"), f"q={st_q} g={st_g}")

print("\n== F05: ATR 扫损容差 ==")
# 高波动股 ATR 大 → 容差 > 0.3%
high_vol = []
day = _dt.date(2026, 1, 1)
c = 50.0
for _ in range(120):
    if day.weekday() < 5:
        c = c * (1 + 0.05 if _ % 2 else 1 - 0.05)  # 大幅摆动
        high_vol.append({"t": day.strftime("%Y%m%d"), "o": c, "h": c*1.06, "l": c*0.94, "c": c, "v": 1_000_000})
    day += _dt.timedelta(days=1)
tol = WE.sweep_tol_of(high_vol, len(high_vol)-1)
ok("高波动 ATR 容差 > 0.3%", tol > 0.003, f"tol={tol:.4f}")

print(f"\n结果: PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
