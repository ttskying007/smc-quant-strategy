# -*- coding: utf-8 -*-
"""core/mss.py 单元测试（V2 Structure Engine: MSS/CHOCH/BOS 精确语义）v2
fixture 用显式 OHLC(可指定 swing wick), 避免 o=prevc 的对称wick 使 swing 湮灭。"""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.mss import confirmed_swings, trend_before, structure_shift, find_shifts, PIVOT_R

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + detail)

def mkbars2(closes, wick=0.1, shw=None, slw=None):
    """显式 OHLC: o=前收, h=max(o,c)+wick(可对指定bar加大wick造swing), l=min(o,c)-wick。"""
    shw = shw or {}
    slw = slw or {}
    out = []
    for i, c in enumerate(closes):
        o = closes[i-1] if i else c
        out.append({"t": f"202601{i+1:02d}", "o": o,
                    "h": max(o, c) + shw.get(i, wick),
                    "l": min(o, c) - slw.get(i, wick), "c": c, "v": 1000})
    return out

print("== 1. 确认swing无前视 ==")
# 下行系列, idx8 为 swing high(加长wick); 序列足够长(i>=25)
closes_dn = [12.4, 12.2, 12.0, 11.8, 11.7, 11.8, 12.0, 12.1, 12.3, 12.0, 11.7, 11.4, 11.1, 10.8,
             10.5, 10.2, 9.9, 9.6, 9.3, 9.0, 9.5, 10.1, 10.8, 11.5, 12.3, 12.8, 13.0, 13.1]
bs = mkbars2(closes_dn, shw={8: 0.5})
i = len(bs) - 1
highs, lows = confirmed_swings(bs, i)
ok("找到swing high(含长wick)", any(h["idx"] == 8 for h in highs), str([(h['idx'], h['price']) for h in highs]))
ok("swing距i超过PIVOT_R", all(i - h["idx"] > PIVOT_R for h in highs))
bs2 = [dict(b) for b in bs]
bs2[-1]["h"] = 99.0; bs2[-1]["l"] = 1.0
h1, _ = confirmed_swings(bs, len(bs) - 3)
h2, _ = confirmed_swings(bs2, len(bs2) - 3)
ok("未来数据不影响已判定swing", [x["idx"] for x in h1] == [x["idx"] for x in h2])

print("== 2. CHOCH: 下行趋势中上破最近确认swing ==")
# 同系列: 最后bar close 13.1 > swing高 12.8, 前20根为下行结构
s2 = structure_shift(bs, i)
ok("检测到结构转移", s2 is not None, "None")
if s2:
    ok("方向LONG", s2["direction"] == "LONG")
    ok("类型CHOCH(逆势上破)", s2["type"] == "CHOCH", s2["type"])
    ok("trend_before=-1(下行)", s2["trend_before"] == -1, str(s2["trend_before"]))
    ok("level=swing高12.8", abs(s2["level"] - 12.8) < 0.01, str(s2["level"]))

print("== 3. BOS: 上行趋势中上破(延续) ==")
# 涨→回调(造swing high)→再涨破: 峰 idx10 加大wick
closes_up = [10.0, 10.2, 10.4, 10.6, 10.8, 11.0, 11.2, 11.4, 11.6, 11.8, 12.0,
             11.8, 11.6, 11.4, 11.2, 11.4, 11.6, 11.8, 12.0, 12.2, 12.4, 12.6,
             12.8, 13.0, 13.2, 13.4]
bs3 = mkbars2(closes_up, shw={10: 0.4})  # h[10]=12.4 峰
s3 = structure_shift(bs3, len(bs3) - 1)
ok("上破检测", s3 is not None and s3["direction"] == "LONG", str(s3))
if s3:
    ok("类型BOS(顺势延续)", s3["type"] == "BOS", s3["type"])
    ok("trend_before=+1(上行)", s3["trend_before"] == 1, str(s3["trend_before"]))
    ok("level=峰高12.4", abs(s3["level"] - 12.4) < 0.01, str(s3["level"]))

print("== 4. 强度字段 ==")
if s2:
    ok("strength 0-100", 0 <= s2["strength"] <= 100)
    ok("break_idx=i", s2["break_idx"] == i)

print("== 5. 横盘无结构转移 ==")
bs4 = mkbars2([10.0] * 40)
ok("横盘None", structure_shift(bs4, len(bs4) - 1) is None)

print("== 6. find_shifts 事件流 ==")
shifts = find_shifts(bs, 20, i)
ok("扫描到事件", len(shifts) >= 1, str(len(shifts)))
ok("事件间隔>=2(去抖)", all(shifts[k+1]["break_idx"] - shifts[k]["break_idx"] >= 2
                          for k in range(len(shifts) - 1)))

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)