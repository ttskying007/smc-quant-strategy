# -*- coding: utf-8 -*-
"""tests_fill_replay.py —— R8: fill-level 回放 + BAD_SL_GE_ENTRY 守卫(2026-09-13)。
四段:
  1) replay_one 撮合语义: 触价成交/开盘兜底/一字涨停 skip/TTL 过期/valid_from 无K线
  2) replay_one 退出语义: 与 core.execution.simulate 同一内核(基线口径 partial 0.3/BE/15bar)
  3) run_layer/aggregate: fill_rate/why 分布/PF/SL 率聚合, min_n gate
  4) 守卫: _tri_decompose bad_sl 守恒 + paper_sim 守卫分支(以源码 AST 校验 sl1>=limit_px fail-closed)
"""
import os, sys, json, inspect

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reject_fill_replay as RFR
import paper_sim
from core.execution import simulate
from core.reason_enums import REJECT_STAGES

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + str(detail))

def mk(bars):
    return bars

# ---------- fixtures: 10 根递增日 K, 基准 ----------
def mkbars(base=10.0, n=12, drift=0.01, vol=0.005, seed=7):
    import random
    random.seed(seed)
    bars, c = [], base
    for k in range(n):
        t = f"202606{k+1:02d}" if k < 30 else f"202607{k-29:02d}"
        o = c
        c = c * (1 + drift + random.uniform(-vol, vol))
        hi = max(o, c) * (1 + vol)
        lo = min(o, c) * (1 - vol)
        bars.append({"t": t, "o": round(o, 4), "h": round(hi, 4), "l": round(lo, 4),
                     "c": round(c, 4), "v": 1000 + k})
    return bars

print("== 1. 撮合语义 ==")
# 1a: 触价成交 —— signal 收盘10, limit=9.9, T+1 low 9.7<=9.9 → limit×(1+slip) 成交
bs = mkbars(base=10.0, n=6, drift=0.0, vol=0.001, seed=1)
bs[1]["l"] = 9.7  # 强制回踩
bs[1]["h"], bs[1]["c"], bs[1]["o"] = 10.2, 10.1, 10.0
r = RFR.replay_one("600000", bs[0]["t"], bs, "STAGE_PASS_ACCUM", 15.0)
ok("1a 触价成交 fill_rule=low<=ref", r and r["filled"] and r["fill_rule"].startswith("LIMIT_OR_OPEN: low<=ref"), r)

# 1b: 未触价 → 开盘兜底(仅 valid_from 日)
bs2 = mkbars(base=10.0, n=6, drift=0.02, vol=0.001, seed=2)  # 全程上行不回踩
r2 = RFR.replay_one("600000", bs2[0]["t"], bs2, "STAGE_PASS_ACCUM", 15.0)
ok("1b 开盘兜底 open_fallback", r2 and r2["filled"] and "open_fallback" in r2["fill_rule"], r2)

# 1c: 一字涨停 → SKIP_LIMIT_UP 未成交
bs3 = mkbars(base=10.0, n=4, drift=0.0, vol=0.001, seed=3)
pc = bs3[0]["c"]
bs3[1]["o"] = round(pc * 1.10, 4)  # 主板涨停开盘
bs3[1]["h"] = bs3[1]["l"] = bs3[1]["c"] = bs3[1]["o"]
r3 = RFR.replay_one("600000", bs3[0]["t"], bs3, "STAGE_PASS_ACCUM", 15.0)
ok("1c 一字涨停 SKIP_LIMIT_UP", r3 and (not r3["filled"]) and r3["why"] == "SKIP_LIMIT_UP", r3)

# 1d: TTL 3 交易日 —— valid_from 日无 open(o=0, 停牌/无开盘数据近似)且 3 日低点始终>limit
#     (limit_or_open 语义: 兜底仅 valid_from 日; 其后只认触价) → TTL_EXPIRED
bs4 = [{"t": "20260601", "o": 10.0, "h": 10.2, "l": 10.0, "c": 10.3, "v": 1000}]  # signal
for k, oc in enumerate((0.0, 10.5, 10.6)):  # day1 无open; day2/3 上行不触
    o = oc if k == 0 else bs4[-1]["c"] * 1.0
    bs4.append({"t": f"2026060{k+2}", "o": round(o, 4), "h": round(o * 1.02 + 0.01, 4),
                "l": round((o if o else 10.5) + 0.05, 4), "c": round((o if o else 10.5) + 0.1, 4), "v": 1000})
r4 = RFR.replay_one("600000", bs4[0]["t"], bs4, "STAGE_PASS_ACCUM", 15.0)
ok("1d TTL 过期(valid_from 无open且3td未触价)", r4 and (not r4["filled"]) and r4["why"] == "TTL_EXPIRED", r4)

# 1e: valid_from 无 K 线(signal 是最后一根) → None
bs5 = mkbars(n=3)
r5 = RFR.replay_one("600000", bs5[-1]["t"], bs5, "STAGE_PASS_ACCUM", 15.0)
ok("1e signal=末根(无 valid_from K线) → None", r5 is None, r5)

print("== 2. 退出语义(与 simulate 同内核) ==")
# 2a: 回放退出结果与手工 simulate(baseline 口径 partial 0.3/BE/15) 完全一致
bsA = mkbars(base=10.0, n=20, drift=0.02, vol=0.01, seed=11)
d8 = bsA[0]["t"]
rA = RFR.replay_one("600000", d8, bsA, "STAGE_PASS_ACCUM", 15.0)
ok("2a 回放产出含 simulate reason/net/hold", rA and rA["filled"] and
   {"reason", "net_pnl_pct", "hold_bars", "mfe_pct", "mae_pct"} <= set(rA.keys()), rA)
sig = inspect.signature(RFR.replay_one)
src = inspect.getsource(RFR.replay_one)
ok("2b 基线口径 partial_tp1=0.3 stop_to_be=True max_hold=15",
   "partial_tp1=0.3" in src and "stop_to_be=True" in src and ("max_hold or 15" in src or "max_hold=max_hold or 15" in src), src[-200:])
# 2c: 独立 simulate 交叉验证同一 fill 价的退出
if rA and rA["filled"]:
    dates = [b["t"] for b in bsA]
    vi = dates.index(__import__("core.trading_calendar", fromlist=["next_td"]).next_td(d8)) if False else 1
    sim = simulate(bsA, vi, rA["fill_price"], rA["sl1"], tp1=rA["tp1"], tp2=rA["tp4"], tp3=None,
                  code="600000", partial_tp1=0.3, stop_to_be=True, max_hold=15)
    ok("2c 退出与 simulate 逐字段一致", sim["reason"] == rA["reason"] and
       abs(sim["net_pnl_pct"] - rA["net_pnl_pct"]) < 1e-9 and sim["hold_bars"] == rA["hold_bars"],
       (sim.get("reason"), rA["reason"], sim.get("net_pnl_pct"), rA["net_pnl_pct"]))

print("== 3. 聚合 ==")
recs = [{"code": "600000", "date": bs4[0]["t"], "stage": "ADX_LT20", "adx": 12},
        {"code": "600000", "date": bsA[0]["t"], "stage": "ADX_LT20", "adx": 13}]
_bars_map = {bs4[0]["t"]: bs4, bsA[0]["t"]: bsA}
res = RFR.run_layer(recs, bars_of=lambda c: (bs4 if recs[0]["date"] == bs4[0]["t"] else bsA), ttl_td=3, min_n=1) if False else \
      RFR.run_layer(recs, bars_of=lambda c: None, ttl_td=3, min_n=1)  # placeholder replaced below
# 直接分别跑两个日期: 用 bars_of 按 signal_date 路由不可行(bars_of 参数只有 code), 改为逐条 replay_one + aggregate
_t1 = RFR.replay_one("600000", bs4[0]["t"], bs4, "ADX_LT20", 12)
_t2 = RFR.replay_one("600000", bsA[0]["t"], bsA, "ADX_LT20", 13)
_trades = [t for t in (_t1, _t2) if t and t.get("filled")]
_notf = [t for t in (_t1, _t2) if t and not t.get("filled")]
a = RFR.aggregate(_trades, _notf, 0, min_n=1)
ok("3a n_candidates=2", a["n_candidates"] == 2, a)
ok("3b not_filled_why 含 TTL_EXPIRED", a["not_filled_why"].get("TTL_EXPIRED") == 1, a["not_filled_why"])
ok("3c min_n_gate(n>=1)", a["min_n_gate"] is True, a)
ok("3d PF/SL 率聚合字段齐", all(k in a for k in ("pf", "sl_rate", "tp_rate", "avg_mfe", "avg_mae")), a)

print("== 4. BAD_SL_GE_ENTRY 守卫 ==")
# 4a: tri_decompose bad_sl 计入 quality 且守恒
tri = paper_sim._tri_decompose(raw=10, hard=2, soft=1, soft_delta=1, skipped_stage=1,
                               skipped_adx=1, nodata=1, dup=1, orders=1, bad_sl=1)
ok("4a 守恒 raw=quality+nodata+dup+orders(bad_sl 已含在 quality 内, 双重计入会破坏守恒)",
   tri["quality_reject"] == 2+1+1+1+1+1 and tri["execution_capacity"]["bad_sl"] == 1
   and tri["quality_reject"] + tri["data_missing"] + tri["execution_capacity"]["dup"]
      + tri["orders_created"] == 10, tri)
# 4b: 守卫分支源码存在(paper_sim 源码文本校验, 防回归删除)
psrc = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_sim.py"),
            encoding="utf-8").read()
ok("4b paper_sim 有 sl1>=limit_px fail-closed 分支",
   "BAD_SL_GE_ENTRY" in psrc and "sl1 >= limit_px" in psrc, "guard missing")
# 4c: 枚举登记
ok("4c reject 枚举已登记 BAD_SL_GE_ENTRY(R8)",
   "BAD_SL_GE_ENTRY" in REJECT_STAGES and isinstance(REJECT_STAGES, frozenset))

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)