# -*- coding: utf-8 -*-
"""core/fvg_ob.py 单元测试（V2 Structure Engine: FVG/OB/Reclaim 统一语义）"""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.fvg_ob import fvg_at, is_fvg_filled, order_block, reclaim_of

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + detail)

def mk(closes, lows=None, highs=None, opens=None):
    out = []
    for i, c in enumerate(closes):
        o = opens[i] if opens else (closes[i-1] if i else c)
        h = highs[i] if highs else max(o, c) + 0.05
        l = lows[i] if lows else min(o, c) - 0.05
        out.append({"t": f"202601{i+1:02d}", "o": o, "h": h, "l": l, "c": c, "v": 1000})
    return out

print("== 1. Bullish FVG 检测 ==")
# 三根: a(h=10.1) → b(急涨) → c(l=10.5>10.1) 形成上方缺口
closes = [9.8]*14 + [10.0, 10.6, 11.0]
bs = mk(closes)
f = fvg_at(bs, len(bs) - 1)
ok("检测到BULL FVG", f is not None and f["direction"] == "BULL", str(f))
if f:
    ok("gap区间正确", abs(f["low"] - 10.05) < 0.01 or f["low"] >= 9.95, str(f["low"]))
    ok("mid在区间内", f["low"] <= f["mid"] <= f["high"])
    ok("size_atr>=0.25", f["size_atr"] >= 0.25, str(f["size_atr"]))

print("== 2. 无缺口返回None ==")
bs2 = mk([10.0]*20)
ok("横盘无FVG", fvg_at(bs2, len(bs2) - 1) is None)

print("== 3. FVG 回补判定 ==")
# FVG 后价格回到 mid → filled
closes3 = [9.8]*14 + [10.0, 10.6, 11.0, 10.3, 10.2]
bs3 = mk(closes3)
f3 = fvg_at(bs3, 16)  # FVG在idx16
ok("FVG@16", f3 is not None)
if f3:
    filled = is_fvg_filled(bs3, len(bs3) - 1, f3, bars=5)
    ok("回补判定filled", filled, str(f3))
# 无回补: 价格继续涨
closes4 = [9.8]*14 + [10.0, 10.6, 11.0, 11.5, 12.0]
bs4 = mk(closes4)
f4 = fvg_at(bs4, 16)
ok("FVG@16(续涨)", f4 is not None)
if f4:
    ok("未回补", not is_fvg_filled(bs4, len(bs4) - 1, f4, bars=5))

print("== 4. 无前视: 未来bar不影响i处FVG ==")
bsA = mk([9.8]*14 + [10.0, 10.6, 11.0] + [11.5, 12.0])
bsB = mk([9.8]*14 + [10.0, 10.6, 11.0] + [1.0, 1.0])
fA = fvg_at(bsA, 16); fB = fvg_at(bsB, 16)
ok("未来数据不影响FVG判定", (fA is None) == (fB is None))

print("== 5. Order Block ==")
# BULL OB: 上涨起点前的连续阴线末段
closes5 = [12.0, 11.8, 11.6, 11.4, 11.2] + [11.0, 10.8, 10.9, 11.2, 11.5, 11.8, 12.1, 12.4, 12.7, 13.0]
bs5 = mk(closes5)
ob = order_block(bs5, len(bs5) - 1, "BULL", lookback=8)
ok("检测到BULL OB", ob is not None, str(ob))
if ob:
    ok("区间字段完整", all(k in ob for k in ("low", "high", "mid", "bars_len", "freshness")))
    ok("freshness 0-1", 0 <= ob["freshness"] <= 1)

print("== 6. Reclaim 语义 ==")
# 跌破 10.5 后 3 根内收回
closes6 = [11.0]*10 + [10.4, 10.3, 10.2, 10.6, 10.8, 11.0]
bs6 = mk(closes6)
rc, ridx = reclaim_of(bs6, len(bs6) - 1, 10.5, "LONG", bars=5)
ok("收回检测", rc and ridx is not None, f"{rc},{ridx}")
# 未收回: 继续跌
closes7 = [11.0]*10 + [10.4, 10.3, 10.2, 10.1, 10.0, 9.9]
bs7 = mk(closes7)
rc7, _ = reclaim_of(bs7, len(bs7) - 1, 10.5, "LONG", bars=5)
ok("未收回→False", not rc7)
# 从未失去: 一直在上方 → False(前提不成立)
closes8 = [11.0]*16
bs8 = mk(closes8)
rc8, _ = reclaim_of(bs8, len(bs8) - 1, 10.5, "LONG", bars=5)
ok("从未失去→False", not rc8)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)