# -*- coding: utf-8 -*-
"""tests_audit_v699_limit_model.py —— V699 涨跌停可成交性建模回归锁(审计 §7.4/Iteration 3).

审计 §7.4 A股约束: 涨跌停不可成交/停牌和缺失行情/复权口径与实际成交价口径一致。
审计 Iteration 3: 保留 V699 的 strict T+1、SL 优先、跳空和成本规则, 增加涨跌停建模。

实现语义(预注册, 保守):
  ① 涨停开盘: 买单不可成交 -> 拒绝(LIMIT_UP_OPEN_UNTRADABLE)。
     板块判定: 688/689+300/301/302 ±20%, BJ ±30%, 主板 ±10%;
     ST ±5% 无法从代码识别(需名称数据) -> 近似按主板, 诚实标注限制。
  ② 跌停开盘: 卖出申报进排队(卖方队列深) -> 整个 bar 退出不可成交(保守),
     持仓顺延, 退出发生在下一个可成交 bar。略保守: 价格盘中脱离跌停时高于
     跌停价的止损卖出本可成交, 此模型忽略(诚实标注)。
  ③ TIME20 收盘在跌停: 持仓未平 -> OPEN_DATA(不记 TIME20 成交)。
  ④ qfq 前复权数据同段内相邻日比率守恒, 调整价近似正确; epsilon 容忍
     交易所 0.01 取整与浮点噪声(相对 5bp)。

判据(预注册):
  ① 涨停开盘入场被拒绝; 低于涨停的入场正常放行
  ② 跌停开盘的 GAP_SL 被顺延, 退出发生在下一个可成交 bar 的开盘价
  ③ 连续跌停 -> 持仓卡死 -> OPEN_DATA
  ④ 无涨跌停事件的基线 TP/SL 不受影响(回归锁)
  ⑤ 全部 fixture 满足源合约: response 收盘 > sweep 高点
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

# 仅提取测试需要的纯函数+常量, 跳过模块级 /root/.hermes IO
import re  # noqa: E402
LEFT = RIGHT = 3
STOP_BUFFER = 0.99
MAX_HOLD = 20
FEE_PCT = 0.20
from typing import Any  # noqa: E402

FUNC_RE = re.compile(r"(def (num|day|high_pivot|limit_ratio|visible_target|pct|replay)\(.*?(?=\ndef |\Z))",
                     re.S)
extracted = "\n".join(m.group(1) for m in FUNC_RE.finditer(src))
exec(compile(extracted, "v699_funcs", "exec"))


def make_bars(rows):
    """构造 OHLC bars: rows=[(o,h,l,c)...], 索引即 idx."""
    return [{"t": "2024%02d%02d" % (i // 22 + 1, i % 22 + 1),
             "o": o, "h": h, "l": l, "c": c}
            for i, (o, h, l, c) in enumerate(rows)]


def base_bars(entry_bar=None, path_bars=None):
    """基础 fixture(满足源合约, 真实几何):

      idx0-5 : 100.0..100.5 平台(o=h=l=c)
      idx6   : pivot, high=115(左3根/右3根确认, 未消费 -> 目标(6,115))
      idx7-9 : 100.7..100.9 回落
      idx10  : sweep bar: o=101 h=102 l=90 c=95(全程低于 pivot 115)
      idx11  : response bar: o=96 h=104 l=95 c=103(收盘 103 > sweep 高 102)
      idx12  : entry bar(默认 o=100 h=101 l=99 c=100.5)
      path   : entry 之后的可退出路径 bar
      stop = 90*0.99 = 89.1; target = 115; entry limit参考 = response收盘 103
    """
    rows = []
    px = 100.0
    for i in range(10):
        rows.append((110.0, 115.0, 109.0, 111.0) if i == 6 else (px, px, px, px))
        px += 0.1
    rows.append((101.0, 102.0, 90.0, 95.0))                # idx10 sweep
    rows.append((96.0, 104.0, 95.0, 103.0))                # idx11 response
    rows.append(entry_bar or (100.0, 101.0, 99.0, 100.5))  # idx12 entry
    rows.extend(path_bars or [])
    return make_bars(rows)


def seed_row(bars):
    return {"symbol": "000001.SZ",
            "entry_eligible_date": bars[12]["t"], "sweep_date": bars[10]["t"],
            "sweep_low": 90.0, "response_date": bars[11]["t"], "sweep_idx": "10"}


print("== 0. fixture 源合约一致性 ==")
for name, fx in [("基础", base_bars()),
                 ("涨停入场", base_bars(entry_bar=(113.3, 113.3, 112.0, 113.3))),
                 ("跌停顺延", base_bars(path_bars=[(88.0, 89.0, 87.0, 88.5), (87.0, 88.0, 86.0, 87.5)]))]:
    ok("合约: %s fixture response收盘>sweep高点" % name, fx[11]["c"] > fx[10]["h"])

print("\n== 1. 涨停开盘入场被拒绝(113.3 >= 103*1.1-eps) ==")
b1 = base_bars(entry_bar=(113.3, 113.3, 112.0, 113.3))
r1 = replay(seed_row(b1), b1)
print("  涨停入场 replay =", {"status": r1.get("status"), "reason": r1.get("reason")})
ok("涨停开盘被拒绝(LIMIT_UP_OPEN_UNTRADABLE)",
   r1.get("status") == "SKIP" and r1.get("reason") == "LIMIT_UP_OPEN_UNTRADABLE", r1)

print("\n== 2. 低于涨停的入场正常放行(112 < 103*1.1-eps) ==")
b2 = base_bars(entry_bar=(112.0, 113.0, 111.0, 112.0),
               path_bars=[(101.0, 102.0, 100.0, 101.5)])
r2 = replay(seed_row(b2), b2)
print("  低于涨停 replay =", {"status": r2.get("status"), "reason": r2.get("reason")})
ok("低于涨停不被误拒(正常放行)",
   not (r2.get("reason") == "LIMIT_UP_OPEN_UNTRADABLE"), r2)

print("\n== 3. 跌停开盘 GAP_SL 被顺延 -> 退出在下一个可成交 bar 的开盘价 ==")
b3 = base_bars(path_bars=[(88.0, 89.0, 87.0, 88.5), (87.0, 88.0, 86.0, 87.5)])
r3 = replay(seed_row(b3), b3)
print("  跌停顺延 replay =", {"status": r3.get("status"), "reason": r3.get("reason"),
                        "exit_price": r3.get("exit_price"), "hold_bars": r3.get("hold_bars")})
ok("跌停bar不退出, 退出在下一可成交bar(88被顺延, 87成交)",
   r3.get("status") == "CLOSED" and r3.get("reason") == "GAP_SL"
   and r3.get("exit_price") == 87.0 and r3.get("hold_bars") == 2, r3)

print("\n== 4. 连续跌停 -> 持仓卡死 -> OPEN_DATA ==")
b4 = base_bars(path_bars=[(88.0, 89.0, 87.0, 88.5), (79.0, 80.0, 78.0, 79.5)])
r4 = replay(seed_row(b4), b4)
print("  连续跌停 replay =", {"status": r4.get("status"), "reason": r4.get("reason")})
ok("连续跌停持仓卡死(OPEN_DATA)",
   r4.get("status") == "OPEN_DATA", r4)

print("\n== 5. 基线 TP 不受影响(无涨跌停事件) ==")
b5 = base_bars(path_bars=[(101.0, 116.0, 100.0, 115.0)])
r5 = replay(seed_row(b5), b5)
print("  基线TP replay =", {"status": r5.get("status"), "reason": r5.get("reason"),
                       "exit_price": r5.get("exit_price")})
ok("基线TP_STRUCTURAL(target=115成交, 回归锁)",
   r5.get("status") == "CLOSED" and r5.get("reason") == "TP_STRUCTURAL"
   and r5.get("exit_price") == 115.0, r5)

print("\n== 6. 基线 SL 不受影响(无涨跌停事件) ==")
b6 = base_bars(path_bars=[(101.0, 102.0, 89.0, 90.0)])
r6 = replay(seed_row(b6), b6)
print("  基线SL replay =", {"status": r6.get("status"), "reason": r6.get("reason"),
                       "exit_price": r6.get("exit_price")})
ok("基线SL(stop=89.1成交, 回归锁)",
   r6.get("status") == "CLOSED" and r6.get("reason") == "SL"
   and r6.get("exit_price") == 89.1, r6)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
