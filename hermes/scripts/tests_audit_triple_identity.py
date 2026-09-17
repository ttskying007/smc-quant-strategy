# -*- coding: utf-8 -*-
"""tests_audit_triple_identity.py — 事件流引擎 vs V697 generator vs V698 oracle 三路身份一致(Iter2)."""
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
import v698_pure_smc_ssl_reclaim_oracle as v698
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
def v698_events(bars, symbol="T"):
    # V698 oracle 返回 (symbol,swing,sweep,response); 忽略 symbol 取 [1:]
    tup = [(b["t"], b["o"], b["h"], b["l"], b["c"], b["v"]) for b in bars]
    return {s[1:] for s in v698.oracle_for(symbol, tup)}
PAD = [("2023-12-%02d" % (i + 1), 100, 101, 99, 100, 100) for i in range(20)]
def build_scene(events, tail=6):
    bars = make_bars(PAD + events)
    last = bars[-1]
    for i in range(tail):
        bars.append({"t": "2026-12-%02d" % (i + 1),
                     "o": last["o"], "h": last["h"] * 1.01,
                     "l": last["l"] * 0.99, "c": last["c"], "v": last["v"]})
    return bars
def triple_check(scene, label):
    e, g, o = engine_events(scene), v697_events(scene), v698_events(scene)
    ne, ng, no = norm(e), norm(g), norm(o)
    print("  %s: 引擎=%s V697=%s V698=%s" % (label, ne, ng, no))
    ok("%s: 三路身份一致" % label, ne == ng == no, (ne, ng, no))
print("== 1. 单事件 ==")
B1 = build_scene([
    ("2024-01-06", 100, 101, 95.0, 100, 100),
    ("2024-01-07", 100, 101, 99, 100, 100),
    ("2024-01-08", 100, 101, 99, 100, 100),
    ("2024-01-09", 100, 101, 99, 100, 100),
    ("2024-01-12", 100, 100, 92.0, 98, 500),
    ("2024-01-13", 100, 102, 99, 102, 300),
])
triple_check(B1, "单事件")
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
triple_check(B2, "消费场景")
print("== 3. 多事件 ==")
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
triple_check(B3, "多事件")
print("== 4. 无事件 ==")
B4 = build_scene([
    ("2024-01-06", 100, 101, 95.0, 100, 100),
    ("2024-01-07", 100, 101, 99, 100, 100),
    ("2024-01-08", 100, 101, 99, 100, 100),
    ("2024-01-09", 100, 101, 99, 100, 100),
    ("2024-01-12", 100, 100, 92.0, 98, 500),
    ("2024-01-13", 100, 101, 99, 99, 300),
])
triple_check(B4, "无事件")
print("== 5. V698 oracle 无 outcome 字段(源码检查) ==")
src = open(os.path.join(V25, "v698_pure_smc_ssl_reclaim_oracle.py"), encoding="utf-8").read()
ok("V698 无 outcome 字段读取", all(k not in src for k in ("net_pnl", "mfe_pct", "mae_pct", "won")))
print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
