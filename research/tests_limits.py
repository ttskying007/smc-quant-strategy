# -*- coding: utf-8 -*-
"""core/limits.py 测试（第四轮 A8: 板块统一涨跌停）+ profile A8 回归"""
import io, os, sys, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.limits import daily_limit_pct, is_limit_up, is_limit_down

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + detail)

print("== 1. 板块幅度 ==")
ok("主板SH 10%", daily_limit_pct("600000") == 10.0)
ok("主板SZ 10%", daily_limit_pct("000001") == 10.0)
ok("带后缀 10%", daily_limit_pct("000001_SZ") == 10.0)
ok("创业板30xxxx 20%", daily_limit_pct("300750") == 20.0)
ok("科创板68 20%", daily_limit_pct("688981") == 20.0)
ok("创业板 2020 前 10%", daily_limit_pct("300750", "20200101") == 10.0)
ok("创业板 2020 后 20%", daily_limit_pct("300750", "20240101") == 20.0)
ok("北交所 30%", daily_limit_pct("832000") == 30.0)
ok("ST 5%", daily_limit_pct("600000", is_st=True) == 5.0)
ok("缺码默认10%", daily_limit_pct("") == 10.0)

print("== 2. 涨跌停判定 ==")
ok("涨停10%", is_limit_up(11.0, 10.0, "600000"))
ok("非涨停", not is_limit_up(10.5, 10.0, "600000"))
ok("涨停20%", is_limit_up(12.0, 10.0, "300750"))
ok("10%在创业板不算停(2024)", not is_limit_up(11.0, 10.0, "300750", "20240101"))
ok("跌停", is_limit_down(9.0, 10.0, "600000"))
ok("零昨收安全", not is_limit_up(11.0, 0, "600000"))

print("== 3. profile A8 回归(带code) ==")
from core.profile import stock_profile
def mk_bars2(closes, seed=1):
    rnd = random.Random(seed)
    out = []
    for i, c in enumerate(closes):
        o = closes[i-1] if i else c
        out.append({"t": f"202601{i+1:02d}", "o": o, "h": max(o, c) * (1 + rnd.uniform(0.005, 0.02)),
                    "l": min(o, c) * (1 - rnd.uniform(0.005, 0.02)), "c": c, "v": rnd.uniform(5e6, 2e7)})
    return out
closes = [10 * (1 + 0.002 * i) for i in range(140)]
bs = mk_bars2(closes)
p = stock_profile(bs, len(bs) - 1, code="600000")
ok("profile 正常生成(带code)", p is not None and 0 <= p["limit_freq"] <= 1)
p2 = stock_profile(bs, len(bs) - 1, code="300750")
ok("profile 创业板", p2 is not None)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)