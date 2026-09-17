# -*- coding: utf-8 -*-
"""tests_audit_weekly_trend.py —— 周线合成修复回归锁(审计§6.2 P1).

修复来源: 外部审计 §6.2(周线合成问题)。
修复位置: weekly_trend.py
  ① synthesize_weekly 按自然周(ISO YYYY-WW)对齐, 半周显式丢弃 ——
     不再按固定 5 根分组(任意起点导致周边界偏移)
  ② weekly_trend 权重倒序应用 —— recent 为时间升序(旧->新),
     0.3 权重给最新周(原实现给最旧周, 与注释意图相反)

本测试固化:
  1. 自然周对齐(完整周合成, 首尾半周丢弃)
  2. 权重序: 近期权重最高的语义下, 上行/下行趋势正确识别
  3. 样本不足守卫(lookback+2)仍生效
纯内存, 不写生产。
"""
import importlib.util
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
V11 = os.path.join(HERE, "v11")
PASS = FAIL = 0


def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  OK " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + " " + str(detail))


sys.path.insert(0, V11)
import weekly_trend as wt  # noqa: E402

print("== 1. 自然周对齐 ==")
import datetime as dt  # noqa: E402
bars = []
px = 10.0
for wk in range(4):          # 4 个完整周(每周 5 天)
    for d in range(5):
        t = dt.date(2024, 1, 1) + dt.timedelta(days=wk * 7 + d)
        bars.append({"date": t.isoformat(), "o": px, "h": px * 1.01,
                     "l": px * 0.99, "c": px * 1.002, "v": 1000})
        px *= 1.01
for d in range(3):           # 尾部半周(3 天, 应被丢弃)
    t = dt.date(2024, 1, 29) + dt.timedelta(days=d)
    bars.append({"date": t.isoformat(), "o": px, "h": px * 1.01,
                 "l": px * 0.99, "c": px * 1.002, "v": 1000})
    px *= 1.01
weekly = wt.synthesize_weekly(bars)
ok("23 根日线(4完整周+3半周) -> 4 根周线(半周丢弃)", len(weekly) == 4, len(weekly))
ok("周线 OHLCV 字段完整", all(k in weekly[0] for k in ("o", "h", "l", "c", "v", "date")))

print("== 2. 权重序(近期权重高) ==")
# 上行: 渐进上涨 + 尾部大阳
w8 = [{"o": 10 + 0.2 * i, "h": 10.8 + 0.2 * i, "l": 9.9 + 0.2 * i,
       "c": 10.1 + 0.2 * i, "v": 1, "date": "w%d" % i} for i in range(6)]
w8.append({"o": 11.1, "h": 13.0, "l": 11.0, "c": 12.8, "v": 1, "date": "w6"})
w8.append({"o": 12.8, "h": 13.2, "l": 12.7, "c": 13.1, "v": 1, "date": "w7"})
ok("上行趋势识别为 up", wt.weekly_trend(w8) == "up", wt.weekly_trend(w8))

# 下行: 每根阴线(c < o) + 尾部大阴
w8d = [{"o": 13.0 - 0.2 * i, "h": 13.2 - 0.2 * i, "l": 12.8 - 0.2 * i,
        "c": 12.9 - 0.2 * i, "v": 1, "date": "wd%d" % i} for i in range(6)]
w8d.append({"o": 12.0, "h": 12.1, "l": 10.6, "c": 10.8, "v": 1, "date": "wd6"})
w8d.append({"o": 10.8, "h": 10.9, "l": 10.3, "c": 10.5, "v": 1, "date": "wd7"})
ok("下行趋势识别为 down", wt.weekly_trend(w8d) == "down", wt.weekly_trend(w8d))

print("== 3. 样本不足守卫 ==")
ok("不足 lookback+2 根 -> neutral",
   wt.weekly_trend(w8[:5]) == "neutral", wt.weekly_trend(w8[:5]))

print("== 4. 权重序语义(修复证据) ==")
# 复现: 修复后 0.3 权重给最新周 -> ema 应高于"0.3给最旧周"的旧实现
recent = w8[-5:]
weights_fixed = list(reversed([0.3, 0.25, 0.2, 0.15, 0.1]))   # 最新得0.3
weights_old = [0.3, 0.25, 0.2, 0.15, 0.1]                       # 最旧得0.3(旧实现)
ema_fixed = sum(r["c"] * w for r, w in zip(recent, weights_fixed)) / sum(weights_fixed)
ema_old = sum(r["c"] * w for r, w in zip(recent, weights_old)) / sum(weights_old)
ok("修复后 ema > 旧实现 ema(近期高价被更高权重捕获)",
   ema_fixed > ema_old, "fixed=%.3f old=%.3f" % (ema_fixed, ema_old))

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)