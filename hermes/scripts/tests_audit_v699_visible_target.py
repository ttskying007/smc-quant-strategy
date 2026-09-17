# -*- coding: utf-8 -*-
"""tests_audit_v699_visible_target.py —— V699 visible_target「未被消费」语义属性测试.

审计 §3.7 P1: "visible_target() 中的'未被消费'语义和上下文需要作为独立属性测试验证"

审计关切: visible_target 注释声称 "an already consumed swing high is not an
upside structural target"（已被消费的摆动高点不能作为上行目标），但实现(L77-80)
只检查 pivot 高度 > max(entry, response_high)，**没有验证该 pivot 是否在 sweep
时已被穿透** —— 若 sweep 低点已经打到/穿透 pivot 高度，说明该流动性已被扫掉
（消费），不应再作为目标。

本测试:
  ① 构造: pivot 在 sweep 时被穿透(消费) 但仍被返回 -> 证明缺陷
  ② 构造: pivot 未被消费 -> 应正常返回
  ③ 修复后: 已消费 pivot 必须被排除

判据(预注册): 已消费(被 sweep 穿透)的 pivot 不得作为目标。
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


def make_bars(prices):
    """构造 OHLCV bars: prices=[(o,h,l,c)...]"""
    return [{"t": "2024%02d%02d" % (i // 22 + 1, i % 22 + 1),
             "o": o, "h": h, "l": l, "c": c}
            for i, (o, h, l, c) in enumerate(prices)]


print("== 1. 缺陷验证: 已消费 pivot 被返回(审计关切) ==")
# 构造: sweep_idx=10, response_idx=11, entry=100
#   - pivot 在 idx=6 (high=115) —— 需 LEFT=3 前/ RIGHT=3 后确认
#   - sweep bar(idx=10) 低点 = 112(未穿透 pivot 115) -> 未消费 -> 应返回
#   反向: sweep 低点 = 113?? 不对, 需低于115才算穿透。
#   设计两组对照:
#   A(未消费): sweep low=113 < 115? 113<115 穿透了! 重新设计.
#   B(已消费): sweep low=110 < pivot 115 -> 穿透
#   关键: 若实现不检查消费, 两组都返回 pivot -> 缺陷成立
# 用简单价格序列(每根 o=h=l=c 近似, 仅 pivot 处特殊)

def test_case(consume):
    """consume=True 时 sweep 低点穿透 pivot."""
    bars = []
    px = 100.0
    for i in range(18):
        o = h = l = c = px
        if i == 6:
            # pivot: 高点 115 (响应高点112之下, 因此成为候选)
            o = h = l = c = 115.0
        elif i == 10:
            # sweep bar: 低点 110(穿透 pivot 115) 或 118(未穿透)
            o = h = l = c = 118.0 if not consume else 110.0
        elif i == 11:
            # response bar: 高 112 (高于 entry 100, 低于 pivot 115)
            o = h = l = c = 112.0
        elif i == 12:
            o = h = l = c = 117.0
        bars.append({"t": "2024%02d%02d" % (i // 22 + 1, i % 22 + 1),
                     "o": o, "h": h, "l": l, "c": c})
        px += 0.1
    return bars

# 未消费: sweep 低=118 > pivot高115? 118>115 未穿透 -> 未消费
# 响应高=112 < pivot115 -> pivot 是候选; minimum_target=max(100,112)=112 <115
bars_a = test_case(consume=False)
ta = visible_target(bars_a, sweep_idx=10, response_idx=11, entry=100.0)
print("  未消费场景 visible_target =", ta)
ok("未消费 pivot 被返回(基线正确)", ta is not None and ta[1] > 100, ta)

# 已消费: sweep 低=110 < pivot高115 -> 穿透(流动性被扫掉)
bars_b = test_case(consume=True)
tb = visible_target(bars_b, sweep_idx=10, response_idx=11, entry=100.0)
print("  已消费场景 visible_target =", tb)
# 审计关切: 已消费 pivot 不应是目标。当前实现(L77-80)只查 pivot>response_high,
# 未检查 sweep 是否穿透 -> 大概率仍返回 pivot -> 缺陷
ok("已消费 pivot 应被排除(修复目标)", tb is None, tb)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
print("\n注: 若 '已消费 pivot 应被排除' 失败 => 证实审计§3.7关切(注释与实现不一致),")
print("    需修复 visible_target 加入消费检查(sweep 前穿透则跳过)。")
sys.exit(1 if FAIL else 0)