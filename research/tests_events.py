# -*- coding: utf-8 -*-
"""core/events.py 单元测试（审计 G25）：20 条真实标题分类"""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import events as EV

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + detail)

TITLES = [
    ("控股股东计划增持公司股份约1.2亿元", True, "HOLDER_INCREASE", +1),
    ("关于以集中竞价交易方式回购公司A股股份方案的公告", True, "BUYBACK", +1),
    ("关于股份回购实施结果暨股份变动的公告", False, None, 0),
    ("关于终止增持计划的公告", False, None, 0),
    ("关于控股股东减持公司股份的公告", False, None, -1),
    ("关于回购注销2022年限制性股票激励计划部分限制性股票的公告", True, "BUYBACK", +1),
    ("关于增持公司股份达到总股本1.5%的公告", True, "HOLDER_INCREASE", +1),
    ("关于回购股份进展的公告", False, None, 0),
    ("关于持股5%以上股东减持股份达到1%的公告", False, None, -1),
    ("首次回购公司股份的公告", True, "BUYBACK", +1),
    ("关于增持计划完成的公告", False, None, 0),
    ("回购注销部分限制性股票的公告", True, "BUYBACK", +1),
    ("关于公司股东增持公司股份计划的公告", True, "HOLDER_INCREASE", +1),
    ("关于2025年限制性股票激励计划回购注销的公告", True, "BUYBACK", +1),
    ("关于回购公司股份达到总股本2%的公告", True, "BUYBACK", +1),
    ("前十大股东增持股份的公告", False, None, 0),
    ("关于股东增持公司股份的进展公告", False, None, 0),
    ("关于调整回购股份方案的公告", False, None, 0),
    ("控股股东增持公司股份的公告", True, "HOLDER_INCREASE", +1),
    ("关于解除一致行动人关系的公告", False, None, 0),
]

for i, (t, exp_is, exp_kind, exp_pol) in enumerate(TITLES):
    is_ev, kind, pol, amt, pct = EV.classify_title(t)
    ok(f"T{i+1}: {t[:24]}", is_ev == exp_is and kind == exp_kind and pol == exp_pol,
       f"got({is_ev},{kind},{pol}) exp({exp_is},{exp_kind},{exp_pol})")

print(f"\n结果: PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
