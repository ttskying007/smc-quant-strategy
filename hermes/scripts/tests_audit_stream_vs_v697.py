# -*- coding: utf-8 -*-
"""tests_audit_stream_vs_v697.py — 事件流引擎 vs V697 generator 交叉验证(Iter2)."""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
V25 = os.path.join(HERE, "v25")
sys.path.insert(0, V25)
PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + str(detail))
from causal_stream import CausalEventEngine
import v697_pure_smc_ssl_reclaim_seed as v697
def make_bars(prices):
    return [{"t": t, "o": o, "h": h, "l": l, "c": c, "v": v} for t, o, h, l, c, v in prices]
def norm(ev_set):
    out = set()
    for s in ev_set:
        out.add(tuple("".join(c for c in d if c.isdigit())[:8] for d in s))
    return out
def engine_events(bars, symbol="T"):
    eng = CausalEventEngine(symbol)
    for b in bars:
        eng.step(b)
    return {(e[1], e[2], e[3]) for e in eng.event_ids()}
def v697_events(bars, symbol="T"):
    seeds = v697.scan_symbol(symbol, bars)
    return {(s["swing_date"], s["sweep_date"], s["response_date"]) for s in seeds}
PAD = [("2023-12-%02d" % (i + 1), 100, 101, 99, 100, 100) for i in range(20)]
def build_scene(events, tail=6):
    bars = make_bars(PAD + events)
    last = bars[-1]
    for i in range(tail):
        bars.append({"t": "2099-%02d-%02d" % (i // 28 + 1, i % 28 + 1),
                     "o": last["o"], "h": last["h"] * 1.01,
                     "l": last["l"] * 0.99, "c": last["c"], "v": last["v"]})
    return bars
print("== 1. 单事件场景 ==")
B1 = build_scene([
    ("2024-01-06", 100, 101, 95.0, 100, 100),
    ("2024-01-07", 100, 101, 99, 100, 100),
    ("2024-01-08", 100, 101, 99, 100, 100),
    ("2024-01-09", 100, 101, 99, 100, 100),
    ("2024-01-12", 100, 100, 92.0, 98, 500),
    ("2024-01-13", 100, 102, 99, 102, 300),
])
ee1, ve1 = engine_events(B1), v697_events(B1)
print("  引擎:", norm(ee1), "| V697:", norm(ve1))
ok("单事件: 引擎与 V697 一致", norm(ee1) == norm(ve1), (norm(ee1), norm(ve1)))
print("== 2. 消费场景 ==")
B2 = build_scene([
    ("2024-01-06", 100, 101, 95.0, 100, 100),
    ("2024-01-07", 100, 101, 99, 100, 100),
    ("2024-01-08", 100, 101, 99, 100, 100),
    ("2024-01-09", 100, 101, 99, 100, 100),
    ("2024-01-10", 100, 101, 94.0, 96, 300),
    ("2024-01-13", 100, 100, 92.0, 98, 500),
    ("2024-01-14", 100, 102, 99, 102, 300),
])
ee2, ve2 = engine_events(B2), v697_events(B2)
print("  引擎:", norm(ee2), "| V697:", norm(ve2))
ok("消费场景: 一致(均无)", norm(ee2) == norm(ve2) == set(), (norm(ee2), norm(ve2)))
print("== 3. 多事件场景 ==")
B3 = build_scene([
    ("2024-01-06", 100, 101, 95.0, 100, 100),
    ("2024-01-07", 100, 101, 99, 100, 100),
    ("2024-01-08", 100, 101, 99, 100, 100),
    ("2024-01-09", 100, 101, 99, 100, 100),
    ("2024-01-12", 100, 100, 92.0, 98, 500),
    ("2024-01-13", 100, 102, 99, 102, 300),
    ("2024-02-01", 105, 106, 103, 105, 100),
    ("2024-02-02", 105, 106, 103, 105, 100),
    ("2024-02-05", 105, 106, 103, 105, 100),
    ("2024-02-06", 105, 106, 103, 105, 100),
    ("2024-02-07", 105, 106, 103, 105, 100),
    ("2024-02-08", 105, 106, 101.0, 105, 100),
    ("2024-02-09", 105, 106, 104, 105, 100),
    ("2024-02-12", 105, 106, 104, 105, 100),
    ("2024-02-13", 105, 106, 104, 105, 100),
    ("2024-02-14", 105, 105, 99.0, 103, 500),
    ("2024-02-15", 105, 107, 104, 107, 300),
])
ee3, ve3 = engine_events(B3), v697_events(B3)
print("  引擎:", norm(ee3), "| V697:", norm(ve3))
ok("多事件: 引擎与 V697 一致", norm(ee3) == norm(ve3), (norm(ee3), norm(ve3)))
print("== 4. 无事件场景 ==")
B4 = build_scene([
    ("2024-01-06", 100, 101, 95.0, 100, 100),
    ("2024-01-07", 100, 101, 99, 100, 100),
    ("2024-01-08", 100, 101, 99, 100, 100),
    ("2024-01-09", 100, 101, 99, 100, 100),
    ("2024-01-12", 100, 100, 92.0, 98, 500),
    ("2024-01-13", 100, 101, 99, 99, 300),
])
ee4, ve4 = engine_events(B4), v697_events(B4)
print("  引擎:", norm(ee4), "| V697:", norm(ve4))
ok("无事件: 一致(均空)", norm(ee4) == norm(ve4) == set(), (norm(ee4), norm(ve4)))
print("== 5. V697 无 outcome 字段 ==")
seeds = v697.scan_symbol("T", B1)
if seeds:
    s = seeds[0]
    no_outcome = all(k not in s for k in ("net_pnl_pct", "mfe_pct", "mae_pct",
                                          "exit", "pnl", "won"))
    ok("V697 seeds 无 outcome 字段", no_outcome, list(s.keys()))
else:
    ok("V697 seeds 无 outcome 字段", False, "no seeds produced")
print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
