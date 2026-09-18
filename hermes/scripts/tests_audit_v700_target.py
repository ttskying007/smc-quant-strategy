# -*- coding: utf-8 -*-
"""tests_audit_v700_target.py —— V700 扫描器 target「未被消费」语义属性测试.

审计 §3.7 P1 + Iteration 6 四端一致性: 扫描器(v700)与回放(V699)的目标语义必须一致,
否则扫描器放行的候选可能被回放拒绝(准入语义分裂)。

历史教训(20260918 发现):
  Iter1c(bf1a570) 只修了 V699 的消费检查, 且其判定(pivot高<sweep_low)与源合约矛盾
  (条件永假 => 恒 None => 18291 种子 0 成交)。本轮:
  (1) V699 已修复为正确语义(向上穿越 >= = 消费);
  (2) V700 扫描器的 target 原实现只查 pivot>minimum, 未验证消费 —— 与 V699 语义
      不一致, 本轮对齐并加回归锁。

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
    "v700", os.path.join(HERE, "v25", "v700_pure_smc_ssl_reclaim_current_scanner.py"))
src = open(os.path.join(HERE, "v25", "v700_pure_smc_ssl_reclaim_current_scanner.py"),
           encoding="utf-8").read()

# 仅提取测试需要的纯函数(pivot_high/target), 跳过模块级 /root/.hermes IO
import re  # noqa: E402
LEFT = RIGHT = 3
from typing import Any  # noqa: E402

FUNC_RE = re.compile(r"(def (pivot_high|target)\(.*?(?=\ndef |\Z))", re.S)
extracted = "\n".join(m.group(1) for m in FUNC_RE.finditer(src))
exec(compile(extracted, "v700_funcs", "exec"))


def make_bars(rows):
    """构造 OHLCV bars: rows=[(o,h,l,c)...], 索引即 idx."""
    return [{"t": "2024%02d%02d" % (i // 22 + 1, i % 22 + 1),
             "o": o, "h": h, "l": l, "c": c}
            for i, (o, h, l, c) in enumerate(rows)]


def base_fixture(spike_high, spike_at=9):
    """真实几何 fixture(满足源合约, v700 几何: response = sweep+1):

      idx0-4   : 100.0..100.4 平台(o=h=l=c)
      idx5     : pivot, high=115(左3根/右3根确认)
      idx6-8   : 100.5..100.7 回落(pivot 右侧确认窗内, 高点<=115)
      idx9     : spike/grab bar: high=spike_high, 收盘 101 < sweep 高 102
                 (不构成 response; spike 位于 pivot 确认后、sweep 前 —— 消费
                  检查的扫描区间内)
      idx10    : sweep bar: 向下扫荡, o=101 h=102 l=90 c=95
                 —— 全程(高/低)低于 pivot 115; 真实种子里必如此
      idx11    : response bar: o=96 h=104 l=95 c=103 —— 收盘 103 > sweep 高 102
                 (源合约满足); response 高 104 < pivot 115(pivot 为候选)
      minimum = max(response_high=104, response_close=103) = 104 < 115
    """
    rows = []
    px = 100.0
    for i in range(18):
        o = h = l = c = px
        if i == 5:
            o, h, l, c = 110.0, 115.0, 109.0, 111.0
        elif i == spike_at:
            o, h, l, c = 100.0, spike_high, 99.0, 101.0
        elif i == 10:
            o, h, l, c = 101.0, 102.0, 90.0, 95.0
        elif i == 11:
            o, h, l, c = 96.0, 104.0, 95.0, 103.0
        rows.append((o, h, l, c))
        px += 0.1
    return make_bars(rows)


def contract_ok(bars):
    """源合约断言: response(idx=11) 收盘 > sweep(idx=10) 高点。"""
    return bars[11]["c"] > bars[10]["h"]


print("== 0. fixture 源合约一致性 ==")
fixtures = [("未消费", base_fixture(104.0)),
            ("已消费(spike>pivot)", base_fixture(116.0)),
            ("边界(spike==pivot)", base_fixture(115.0))]
for name, fx in fixtures:
    ok("合约: %s fixture response收盘>sweep高点" % name, contract_ok(fx))

print("\n== 1. 未消费 pivot 被返回(真实几何回归锁: sweep低点90 < pivot高115) ==")
bars_a = base_fixture(104.0)
ta = target(bars_a, sweep=10, minimum=104.0)
print("  未消费场景 target =", ta)
ok("未消费 pivot 被返回(回归锁)", ta is not None and ta[0] == 5 and ta[1] == 115.0, ta)

print("\n== 2. 已消费 pivot 被排除(spike 高点 116 > pivot 115) ==")
bars_b = base_fixture(116.0)
tb = target(bars_b, sweep=10, minimum=104.0)
print("  已消费场景 target =", tb)
ok("已消费 pivot 被排除(向上穿越=消费, 与V699语义一致)", tb is None, tb)

print("\n== 3. 边界: bar 高点 == pivot 高点 视为已消费 ==")
bars_c = base_fixture(115.0)
tc = target(bars_c, sweep=10, minimum=104.0)
print("  边界场景 target =", tc)
ok("边界(==)视为消费被排除", tc is None, tc)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
