# -*- coding: utf-8 -*-
"""core/profile.py 单元测试（V2 ITERATION 5: Stock Profile）"""
import io, os, sys, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.profile import stock_profile, profile_cluster, profile_family_params

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + detail)

def mk_bars(closes, seed=1):
    rnd = random.Random(seed)
    out = []
    for i, c in enumerate(closes):
        o = closes[i-1] if i else c
        out.append({"t": f"202601{i+1:02d}", "o": o, "h": max(o, c) * (1 + rnd.uniform(0.005, 0.02)),
                    "l": min(o, c) * (1 - rnd.uniform(0.005, 0.02)), "c": c, "v": rnd.uniform(5e6, 2e7)})
    return out

print("== 1. 基础 Profile(V2 14特征) ==")
closes = [10 * (1 + 0.002 * i) for i in range(140)]  # 温和上行
bs = mk_bars(closes)
p = stock_profile(bs, len(bs) - 1, window=120)
ok("生成Profile", p is not None)
if p:
    ok("atr_pct>0", p["atr_pct"] > 0)
    ok("gap_freq 0-1", 0 <= p["gap_freq"] <= 1)
    ok("trend_persist 0-1", 0 <= p["trend_persist"] <= 1)
    ok("noise_adr_med>0", p["noise_adr_med"] > 0)
    ok("bars=121", p["bars"] == 121)
    # F8: 新增 5 特征
    for k in ("sweep_depth_med", "disp_mean", "disp_q75", "fvg_reaction", "ob_reaction", "typical_hold_pct"):
        ok(f"含特征 {k}", k in p, str(sorted(p.keys())))
    ok("sweep_depth_med>=0", p["sweep_depth_med"] >= 0)
    ok("disp 0-100", 0 <= p["disp_mean"] <= 100 and 0 <= p["disp_q75"] <= 100)
    ok("typical_hold>=0", p["typical_hold_pct"] is None or p["typical_hold_pct"] >= 0)

print("== 2. 高波动 Profile ==")
closes_hv = [10 * (1 + 0.05 * random.Random(i).uniform(-1, 1)) for i in range(140)]
bs_hv = mk_bars(closes_hv, seed=7)
p_hv = stock_profile(bs_hv, len(bs_hv) - 1)
ok("高波动atr更高", p_hv["atr_pct"] > p["atr_pct"], f"{p_hv['atr_pct']} vs {p['atr_pct']}")

print("== 3. 无前视 ==")
bsA = mk_bars(closes); bsB = mk_bars(closes)
bsB[-1]["l"] = 1.0; bsB[-1]["h"] = 99.0
pA = stock_profile(bsA, len(bsA) - 2)
pB = stock_profile(bsB, len(bsB) - 2)
ok("未来bar不影响Profile", pA == pB)
# F8: 新特征同样无前视(i=倒数第2, 未来bar改动不影响 sweep/disp/fvg/ob/hold)
ok("V2新特征无前视", pA == pB)

print("== 4. cluster 标签 ==")
c_lo = profile_cluster({"atr_pct": 1.5, "trend_persist": 0.6})
c_hi = profile_cluster({"atr_pct": 5.0, "trend_persist": 0.3})
ok("低波动标签", c_lo == "profile_low_persist", c_lo)
ok("高波动标签", c_hi == "profile_high_mr", c_hi)
ok("None安全", profile_cluster(None) is None)

print("== 5. 聚类参数族 ==")
fp_lo = profile_family_params(c_lo)
fp_hi = profile_family_params(c_hi)
ok("低波动更长持有", fp_lo["max_hold"] > fp_hi["max_hold"], f"{fp_lo['max_hold']} vs {fp_hi['max_hold']}")
ok("高波动更紧SL缓冲", fp_hi["sl_buf_atr"] < fp_lo["sl_buf_atr"])
ok("参数字段完整", all(k in fp_lo for k in ("sweep_floor", "disp_min", "sl_buf_atr", "max_hold")))

print("== 6. 边界 ==")
ok("窗口不足→None", stock_profile(bs, 50) is None)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)