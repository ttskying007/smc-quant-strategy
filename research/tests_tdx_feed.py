# -*- coding: utf-8 -*-
"""core/tdx_feed.py 单元测试（easy_tdx/pytdx/腾讯 统一适配器）
验证：后端状态探测、腾讯回退、统一 bars schema、实时/资金接口安全降级。
"""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import tdx_feed as TF

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + detail)

# 1. 腾讯后端路径存在（默认主源）
ok("T1: 腾讯K线目录存在", os.path.isdir(TF.KLINE_TENCENT), TF.KLINE_TENCENT)

# 2. 后端状态结构
st = TF.backend_status()
ok("T2: 状态含三后端+active", {"active", "tencent", "pytdx", "easy_tdx"} <= set(st.keys()), str(list(st.keys())))
ok("T3: 腾讯状态为可用", st["tencent"]["available"] is True)

# 3. 腾讯日线读取（600519 茅台，现存股票）
bars = TF.get_daily("600519", backend="tencent")
ok("T4: 600519 腾讯日线>500根", len(bars) > 500, f"n={len(bars)}")
if bars:
    b = bars[-1]
    ok("T5: bars schema 含 t/o/h/l/c/v", {"t", "o", "h", "l", "c", "v"} <= set(b.keys()), str(list(b.keys())))
    ok("T6: t 为 YYYYMMDD 8位", isinstance(b["t"], str) and len(b["t"]) == 8, repr(b["t"]))

# 4. 自动回退（backend=None 时走腾讯，因 pytdx/easy 不可用）
bars_auto = TF.get_daily("600519")
ok("T7: 自动回退腾讯", len(bars_auto) == len(bars) or (len(bars_auto) > 500), f"n={len(bars_auto)}")

# 5. 不存在代码返回空（不崩）
ok("T8: 不存在代码返回[]", TF.get_daily("999999", backend="tencent") == [])

# 6. 实时报价安全降级（网络不可用 → 空 dict，不抛异常）
rt = TF.get_realtime(["600519"])
ok("T9: 实时报价安全降级(不抛异常)", isinstance(rt, dict), repr(rt)[:80])

# 7. 资金流向安全降级
ff = TF.get_fundflow("600519")
ok("T10: 资金流向安全降级(不抛异常)", isinstance(ff, dict), repr(ff)[:80])

# 8. pytdx 后端显式请求失败返回 []（网络不可用，不崩）
pb = TF._pytdx_daily("600519")
ok("T11: pytdx网络不可用返回[]", pb == [], f"n={len(pb)}")

# 9. easy_tdx 探测不崩溃
easy_dir = TF._easy_tdx_available()
ok("T12: easy_tdx 探测返回目录或None", easy_dir is None or isinstance(easy_dir, str), repr(easy_dir))

print(f"\n结果: PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)