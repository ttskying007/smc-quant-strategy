# -*- coding: utf-8 -*-
"""core/setup_exit.py + core/setup_engine.py 测试(V3 P0-1/P0-2)"""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.setup_exit import settle_from_record, EXIT_VERSION
from core.setup_engine import build_setup, validate_setup, ENGINE_VERSION

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + detail)

def _mk(i, o, h, l, c, v=1000):
    return {"t": f"202601{i:02d}", "o": o, "h": h, "l": l, "c": c, "v": v}

print("== 1. settle_from_record: SL / TP(3R) / TIME 三路径 ==")
# 构造: fill@10.0(i=2), SL=9.4, 3R tp=10+3×0.6=11.8
up = [_mk(1, 10.2, 10.3, 10.1, 10.2), _mk(2, 10.0, 10.2, 9.95, 10.05),
      _mk(3, 10.0, 10.1, 9.3, 9.4), _mk(4, 9.4, 9.6, 9.2, 9.5)] + \
     [_mk(k, 9.5, 9.7, 9.4, 9.6) for k in range(5, 22)]
r = settle_from_record(up, 1, 10.0, 9.7, fee_pct=0.2, max_bars=15, tp_rr=3.0)
ok("SL 触发", r["status"] == "SL" and r["exit_reason"] == "SL_HIT", str(r["status"]))
ok("SL ret 为负", r["ret_pct"] < 0)
# TP 路径: 强势上行
upt = [_mk(1, 10.0, 10.1, 9.95, 10.0), _mk(2, 10.0, 10.05, 9.9, 10.0)] + \
      [_mk(k, 10.0 + 0.5 * (k - 2), 10.0 + 0.5 * (k - 2) + 0.2, 10.0 + 0.5 * (k - 2) - 0.1, 10.0 + 0.5 * (k - 2)) for k in range(3, 10)]
r2 = settle_from_record(upt, 1, 10.0, 9.7, fee_pct=0.2, max_bars=15, tp_rr=3.0)
ok("TP 触发(3R 结构位)", r2["status"] == "TP" and r2["exit_reason"] == "TP_STRUCT", str(r2.get("status")))
ok("TP ret ≈ 3R-费", r2["ret_pct"] > 15, str(r2.get("ret_pct")))
# TIME 路径: 横盘
flat = [_mk(1, 10.0, 10.05, 9.95, 10.0), _mk(2, 10.0, 10.05, 9.95, 10.0)] + \
       [_mk(k, 10.0, 10.06, 9.94, 10.0) for k in range(3, 22)]
r3 = settle_from_record(flat, 1, 10.0, 9.0, fee_pct=0.2, max_bars=15, tp_rr=3.0)
ok("TIME 触发", r3["status"] == "TIME" and r3["exit_reason"] == "TIME_STOP")
ok("TIME ret≈-费", abs(r3["ret_pct"] + 0.2) < 0.05, str(r3["ret_pct"]))
ok("版本标记", r3["exit_version"] == EXIT_VERSION == "setup_exit_v1")
# OPEN(窗口未走完)
short = [_mk(1, 10.0, 10.05, 9.95, 10.0), _mk(2, 10.0, 10.05, 9.95, 10.0)]
r4 = settle_from_record(short, 1, 10.0, 9.0)
ok("数据不足→OPEN", r4["status"] == "OPEN" and r4["ret_pct"] is None)

print("== 2. build_setup: 统一 Setup 对象(完整链fixture复用 tests_sequence_v2) ==")
def _mkb(i, o, h, l, c):
    return {"t": f"202601{i:02d}", "o": o, "h": h, "l": l, "c": c, "v": 1000}
daily = []
for k in range(90):
    if 40 <= k <= 44:
        p = 10.0 if k == 42 else 10.15
        daily.append(_mkb(k + 1, p, p + 0.10, p - 0.10, p))
    else:
        daily.append(_mkb(k + 1, 10.6, 10.7, 10.5, 10.6))
daily.append(_mkb(91, 10.6, 10.7, 9.5, 10.05))
daily.append(_mkb(92, 10.05, 10.85, 10.0, 10.8))
daily.append(_mkb(93, 10.8, 11.4, 10.75, 11.35))
daily.append(_mkb(94, 11.35, 11.5, 11.05, 11.2))
daily.append(_mkb(95, 11.2, 11.9, 11.15, 11.85))
daily.append(_mkb(96, 11.85, 11.95, 11.35, 11.45))
for k in range(97, 102):
    daily.append(_mkb(k, 11.5, 11.8, 11.4, 11.7))
setup = build_setup(daily, len(daily) - 1, "TEST01")
if setup:
    ok("Setup 生成", setup is not None)
    ok("setup_id 稳定键", setup["setup_id"].startswith("SU-") and len(setup["setup_id"]) == 15
       and setup.get("setup_id_legacy", "").startswith("TEST01"), setup["setup_id"])
    ok("setup_id 幂等(同输入同hash)", build_setup(daily, len(daily) - 1, "TEST01")["setup_id"] == setup["setup_id"])
    ok("双版本标记", setup["engine_version"] == ENGINE_VERSION and setup["exit_version"] == EXIT_VERSION)
    ok("family 默认", setup["family"] == "SMC_REVERSAL")
    v, why = validate_setup(setup)
    ok("validate PASS", v, why)
else:
    ok("Setup 生成(链完整性)", False, "build_setup 返回 None")

print("== 3. validate_setup fail-closed ==")
bad = {"setup_id": "X", "symbol": "", "signal_date": "20260101"}
v2_, why2 = validate_setup(bad)
ok("缺字段拒绝", not v2_ and why2 == "symbol", why2)
bad2 = dict(setup) if setup else {}
if bad2:
    b3 = dict(bad2)
    b3["invalid_price"] = b3["poi"]["low"] + 1     # invalid 高于 poi.low 非法
    v3_, why3 = validate_setup(b3)
    ok("非法 invalid 位拒绝", not v3_ and why3 == "invalid_above_poi", why3)

print("== 4. 单源验证: PAPER 台账与回测共用 settle_from_record ==")
import core.setup_exit as SE
ok("exit 模块单函数入口", hasattr(SE, "settle_from_record") and hasattr(SE, "settle_setup"))
ok("EXIT_VERSION 可追溯", SE.EXIT_VERSION.startswith("setup_exit"))

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)