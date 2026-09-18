# -*- coding: utf-8 -*-
"""tests_audit_v699_visible_target.py —— V699 visible_target「未被消费」语义属性测试(修订版).

审计 §3.7 P1: "visible_target() 中的'未被消费'语义和上下文需要作为独立属性测试验证"

历史教训(20260918 发现, 修订本测试的原因):
  Iter1c(bf1a570) 曾用 pivot高<sweep_low 判定「已消费」。但源合约要求 response
  收盘突破 sweep 高点 => minimum_target>=response_high>sweep_high>sweep_low 恒成立,
  候选 pivot 高点必然高于 sweep 全程 => pivot高<sweep_low 永假 => visible_target
  恒返回 None => 20260918 全市场回放 18291 种子 0 成交(NO_VISIBLE_UPSIDE_TARGET)。
  旧版属性测试用了违反源合约的合成几何(sweep低点>pivot高), 故测试通过而生产全拒。

正确的 SMC 语义(预注册):
  摆动高点的流动性只在价格向上穿越它时被消费; sweep 低点穿透 pivot 高度是
  SSL 扫荡本身的一部分, 不是消费。pivot 确认后至 response 前无任何 bar 高点
  >= pivot 高 => 未消费(可作目标); bar 高点相等(==)视为已触及(消费)。

判据(预注册):
  ① 未消费 pivot 必须被返回 —— 含真实几何回归锁(sweep 低点 < pivot 高)
  ② 已消费 pivot(确认后至 response 前有 bar 高点 > pivot 高)必须被排除
  ③ 边界: bar 高点 == pivot 高点 视为已消费(排除)
  ④ 全部 fixture 满足源合约: response 收盘 > sweep 高点
"""
import importlib.util
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
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


spec = importlib.util.spec_from_file_location(
    "v699", os.path.join(HERE, "v25", "v699_pure_smc_ssl_reclaim_replay.py"))
src = open(os.path.join(HERE, "v25", "v699_pure_smc_ssl_reclaim_replay.py"),
           encoding="utf-8").read()

# 仅提取测试需要的函数定义(num/day/high_pivot/visible_target), 跳过模块级 IO
import re  # noqa: E402
LEFT = RIGHT = 3
STOP_BUFFER = 0.99
MAX_HOLD = 20
FEE_PCT = 0.20
from typing import Any  # noqa: E402

FUNC_RE = re.compile(r"(def (num|day|high_pivot|visible_target)\(.*?(?=\ndef |\Z))",
                     re.S)
extracted = "".join(m.group(1) for m in FUNC_RE.finditer(src))
exec(compile(extracted, "v699_funcs", "exec"))


def make_bars(rows):
    """构造 OHLC bars: rows=[(o,h,l,c)...], 索引即 idx."""
    return [{"t": "2024%02d%02d" % (i // 22 + 1, i % 22 + 1),
             "o": o, "h": h, "l": l, "c": c}
            for i, (o, h, l, c) in enumerate(rows)]


def base_fixture(spike_high, spike_at=11):
    """真实几何 fixture(满足源合约):

      idx0-5   : 100.0..100.5 平台(o=h=l=c)
      idx6     : pivot, high=115(左3根/右3根确认)
      idx7-9   : 100.6..100.8 回落(pivot 右侧确认窗内, 高点<=115)
      idx10    : sweep bar: 向下扫荡, o=101 h=102 l=90 c=95
                 —— 全程(高/低)低于 pivot 115。真实种子里必如此:
                    minimum_target>=response_high>sweep_high>sweep_low。
      idx11    : spike/grab bar: high=spike_high, 收盘 101 < sweep 高 102
                 (不构成 response; spike 位于 pivot 确认后、response 前)
      idx12    : response bar: o=101 h=104 l=100 c=103 —— 收盘 103 > sweep 高 102
                 (源合约满足); response 高 104 < pivot 115(pivot 为候选)
      minimum_target = max(entry=100, response_high=104) = 104 < 115
    """
    rows = []
    px = 100.0
    for i in range(18):
        o = h = l = c = px
        if i == 6:
            o, h, l, c = 110.0, 115.0, 109.0, 111.0
        elif i == 10:
            o, h, l, c = 101.0, 102.0, 90.0, 95.0
        elif i == spike_at:
            o, h, l, c = 100.0, spike_high, 99.0, 101.0
        elif i == 12:
            o, h, l, c = 101.0, 104.0, 100.0, 103.0
        rows.append((o, h, l, c))
        px += 0.1
    return make_bars(rows)


def contract_ok(bars):
    """源合约断言: response(idx=12) 收盘 > sweep(idx=10) 高点。"""
    return bars[12]["c"] > bars[10]["h"]


print("== 0. fixture 源合约一致性 ==")
fixtures = [("未消费", base_fixture(104.0)),
            ("已消费(spike>pivot)", base_fixture(116.0)),
            ("边界(spike==pivot)", base_fixture(115.0))]
for name, fx in fixtures:
    ok("合约: %s fixture response收盘>sweep高点" % name, contract_ok(fx))

print("\n== 1. 未消费 pivot 被返回(真实几何回归锁: sweep低点90 < pivot高115) ==")
bars_a = base_fixture(104.0)
ta = visible_target(bars_a, sweep_idx=10, response_idx=12, entry=100.0)
print("  未消费场景 visible_target =", ta)
ok("未消费 pivot 被返回(回归锁: Iter1c 曾因此全拒)",
   ta is not None and ta[0] == 6 and ta[1] == 115.0, ta)

print("\n== 2. 已消费 pivot 被排除(spike 高点 116 > pivot 115) ==")
bars_b = base_fixture(116.0)
tb = visible_target(bars_b, sweep_idx=10, response_idx=12, entry=100.0)
print("  已消费场景 visible_target =", tb)
ok("已消费 pivot 被排除(向上穿越=消费)", tb is None, tb)

print("\n== 3. 边界: bar 高点 == pivot 高点 视为已消费 ==")
bars_c = base_fixture(115.0)
tc = visible_target(bars_c, sweep_idx=10, response_idx=12, entry=100.0)
print("  边界场景 visible_target =", tc)
ok("边界(==)视为消费被排除", tc is None, tc)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
