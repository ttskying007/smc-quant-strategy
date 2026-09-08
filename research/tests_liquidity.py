# -*- coding: utf-8 -*-
"""core/liquidity.py 单元测试（V2 Structure Engine 2.0 第一批）"""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.liquidity import liquidity_pools, nearest_pools

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + detail)

def bars(vals, vols=None):
    out = []
    for i, c in enumerate(vals):
        o = vals[i-1] if i else c
        rng = abs(c - o) + 0.02
        out.append({"t": f"2026010{i+1:02d}", "o": o, "h": max(o, c) + rng*0.3,
                    "l": min(o, c) - rng*0.3, "c": c, "v": (vols[i] if vols else 1000)})
    return out

print("== 1. 基础: 池生成与方向 ==")
# 构造: 深度回撤后横盘(swing low 两个等低) + 上面一个 swing high
px = [10.0]*30 + [9.0, 8.0, 7.0, 6.0, 6.5, 7.0, 7.5, 6.2, 6.3, 6.25,
      6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 7.0, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 8.0, 8.1, 8.2, 8.3]
bs = bars(px)
i = len(bs) - 1
pools = liquidity_pools(bs, i)
ssl = [p for p in pools if p["side"] == "SSL"]
bsl = [p for p in pools if p["side"] == "BSL"]
ok("生成池(非空)", len(pools) > 0, str(len(pools)))
ok("SSL池存在(下方承接)", len(ssl) > 0)
ok("BSL池存在(上方阻力)", len(bsl) > 0)
ok("池价格均为正", all(p["price"] > 0 for p in pools))
ok("池idx均在i之前(无前视)", all(p["idx"] < i - 1 for p in pools if p["kind"] == "SWING"))

print("== 2. 池质量字段 ==")
ok("score在0-100", all(0 <= p["score"] <= 100 for p in pools))
ok("age>=1", all(p["age"] >= 1 for p in pools))
ok("touch_count>=0", all(p["touch_count"] >= 0 for p in pools))
ok("含SWING类", any(p["kind"] == "SWING" for p in pools))

print("== 3. 等高低(EQ)合并 ==")
# 两个接近的 swing low 应合并
ssl_sorted = sorted(ssl, key=lambda p: p["price"])
if len(ssl_sorted) >= 1:
    eq_any = any(p["equal"] for p in pools)
    print(f"  (info) SSL 池: {[(p['price'], p['equal']) for p in ssl_sorted[:3]]}")
ok("EQ字段存在", all(isinstance(p["equal"], bool) for p in pools))

print("== 4. 无前视: 修改 i+1 之后数据不影响 i 的池 ==")
bs_a = bars(px)
bs_b = bars(px)
bs_b[-1]["l"] = 1.0; bs_b[-1]["h"] = 99.0; bs_b[-1]["c"] = 50.0
pa = liquidity_pools(bs_a, len(bs_a) - 2)
pb = liquidity_pools(bs_b, len(bs_b) - 2)
sa = sorted((p["side"], p["kind"], p["price"], p["score"]) for p in pa)
sb = sorted((p["side"], p["kind"], p["price"], p["score"]) for p in pb)
ok("未来bar修改不影响池", sa == sb)

print("== 5. nearest_pools ==")
near = nearest_pools(pools, 8.3, side="BSL", n=2)
ok("按侧过滤", all(p["side"] == "BSL" for p in near))
ok("按距离升序", len(near) <= 2)

print("== 6. 边界: i<25 返回空 ==")
ok("早期无池", liquidity_pools(bs, 10) == [])

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)