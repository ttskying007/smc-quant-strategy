# -*- coding: utf-8 -*-
"""core/adaptive.py 单元测试（蓝图迭代四）"""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import adaptive as AD

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + detail)

def mk(closes, vols=None, start_price=10.0, half_range=0.02):
    """half_range: 每根 K 的 h/l 相对 c 的半幅（控制真实 ATR）。"""
    bars = []
    c = start_price
    for i, x in enumerate(closes):
        c = c * (1 + x)
        bars.append({"t": f"20260{1+i%9:02d}{10+i%20:02d}", "o": c*0.995,
                     "h": c*(1+half_range), "l": c*(1-half_range), "c": c,
                     "v": (vols[i] if vols else 1_000_000)})
    return bars

print("== 波动率分层 ==")
ok("low <2%", AD.vol_bucket(0.01) == "low")
ok("mid 2-4%", AD.vol_bucket(0.03) == "mid")
ok("high >4%", AD.vol_bucket(0.05) == "high")
ok("None→default", AD.vol_bucket(None) == "default")

print("== resolve_params ==")
# 低波动股（h/l 半幅 0.005 → ATR≈1%）
low = mk([0.001]*60, half_range=0.005)
b, p, d = AD.resolve_params(low, 59)
ok("低波动→low档", b == "low", b)
ok("low 档 sweep_atr=0.5", p["sweep_atr"] == 0.5)
# 高波动股（h/l 半幅 0.03 → ATR≈6%）
high = mk([0.03]*60, half_range=0.03)
b2, p2, d2 = AD.resolve_params(high, 59)
ok("高波动→high档", b2 == "high", b2)
ok("high 档 sweep_atr=0.7", p2["sweep_atr"] == 0.7)
ok("diag 含 atr_pct", d2["atr_pct"] is not None)

print("== sweep_tol_for ==")
tol_low = AD.sweep_tol_for(low, 59, p)
tol_high = AD.sweep_tol_for(high, 59, p2)
ok("高波动扫损容差 >= 低波动", tol_high >= tol_low, f"{tol_low:.4f} vs {tol_high:.4f}")

print("== sl_for ==")
sl_low = AD.sl_for(low, 59, 9.0, 10.0, p)
sl_high = AD.sl_for(high, 59, 9.0, 10.0, p2)
ok("SL 有缓冲(≤结构低)", sl_low <= 9.0)
ok("高波动 SL 更保守(更低)", sl_high <= sl_low, f"{sl_low:.4f} vs {sl_high:.4f}")

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
