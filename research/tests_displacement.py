# -*- coding: utf-8 -*-
"""core/displacement.py 单元测试（V1 迭代 2）"""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.displacement import displacement_score

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + detail)

def bars(prices, vols=None):
    """从收盘序列合成 bar（o=prev c, h/l 微幅, 指定成交量）"""
    out = []
    for i, c in enumerate(prices):
        o = prices[i-1] if i else c
        v = (vols[i] if vols else 1000)
        rng = abs(c - o) + 0.05
        out.append({"t": f"2026010{i+1}", "o": o, "h": max(o, c) + rng*0.2,
                    "l": min(o, c) - rng*0.2, "c": c, "v": v})
    return out

print("== 1. 平淡 bar → 低分 ==")
flat = bars([10.0]*30)
r = displacement_score(flat, 25)
ok("平淡 bar 低分(<20)", r["score"] < 20, str(r))

print("== 2. 放量大阳+突破 → 高分 ==")
px = [10.0]*25 + [10.0, 10.2, 10.1, 10.3, 10.2, 10.4, 10.3, 10.5, 10.4, 10.6, 11.5]
vv = [1000]*(len(px)-1) + [5000]
bs = bars(px, vv)
r2 = displacement_score(bs, len(bs)-1)
ok("放量大阳高分(≥60)", r2["score"] >= 60, str(r2))
ok("body_atr 满分段", r2["parts"]["body_atr"] >= 25, str(r2["parts"]))
ok("volume 组件>0", r2["parts"]["volume"] > 0, str(r2["parts"]))
ok("close_loc 高", r2["parts"]["close_loc"] >= 12, str(r2["parts"]))

print("== 3. 组件边界 ==")
# 阴线大实体: gap/struct 无加成但 body_atr 计入（位移是双向概念，符号由调用方判）
px3 = [11.0]*25 + [11.0, 10.8, 10.9, 11.0, 10.9, 10.5]
vv3 = [1000]*(len(px3)-1) + [5000]
r3 = displacement_score(bars(px3, vv3), 30)
ok("阴线也有 body_atr", r3["parts"]["body_atr"] > 10, str(r3["parts"]))
ok("阴线 gap=0", r3["parts"]["gap"] == 0, str(r3["parts"]))

print("== 4. 分桶单调 ==")
r_lo = displacement_score(flat, 25)["score"]
r_hi = r2["score"]
ok("分桶单调: 平淡<突破", r_lo < r_hi, f"{r_lo} vs {r_hi}")
ok("分桶文本正确", r2["bucket"] in ("30-60 正常", "60-80 强", "≥80 极强"), r2["bucket"])

print("== 5. 无前视：只用 i 及以前 ==")
# 修改 i+1 之后的 bar 不改变 i 的分数
bs_a = bars(px, vv)
bs_b = bars(px, vv)
bs_b[-1] = {"t": "2026099", "o": 99.0, "h": 99.0, "l": 99.0, "c": 99.0, "v": 1}
ra = displacement_score(bs_a, len(bs_a)-2)
# 注意: 末根被改的是 index len-1, 打分 index len-2 → 两边应完全一致
rb = displacement_score(bs_b, len(bs_b)-2)
ok("修改未来bar不影响当前分", ra["score"] == rb["score"], f"{ra['score']} vs {rb['score']}")

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)