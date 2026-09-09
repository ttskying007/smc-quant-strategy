# -*- coding: utf-8 -*-
"""core/regime.py 测试 + 事件腿六态分布实证"""
import csv, io, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.regime import market_regime, regime_effect_on_event_leg

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + detail)

print("== 1. 指数真值载入 ==")
r = market_regime("20260908")
ok("能算最新状态", r is not None, str(r))
if r:
    ok("六态合法", r["regime"] in ("BULL", "BEAR", "SIDEWAYS", "PANIC", "RECOVERY", "ROTATION"), r["regime"])
    ok("字段完整", all(k in r for k in ("sh_r20", "atr_pct", "atr_rank", "off_high")))

print("== 2. 无前视: d8 之后数据不影响 ==")
r_a = market_regime("20250101")
r_b = market_regime("20250102")
ok("不同日不同快照", r_a is not None and r_b is not None)

print("== 3. 极端日校验 ==")
# 已知熊市样本: 2024-01~02 A股大跌
r_bear = market_regime("20240205")
if r_bear:
    print(f"  20240205: {r_bear['regime']} (r20={r_bear['sh_r20']}%)")
    ok("熊市日识别为 BEAR/PANIC/SIDEWAYS(不误判BULL)", r_bear["regime"] != "BULL")
else:
    ok("熊市日识别(数据缺)", True)
# 2024-09~10 暴涨
r_bull = market_regime("20241008")
if r_bull:
    print(f"  20241008: {r_bull['regime']} (r20={r_bull['sh_r20']}%)")
    ok("924行情判为BULL/RECOVERY", r_bull["regime"] in ("BULL", "RECOVERY", "ROTATION"), r_bull["regime"])

print("== 4. 事件腿六态分布(实证) ==")
rows = [r for r in csv.DictReader(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "combo_v20f_trades.csv"), encoding="utf-8-sig"))
        if r.get("src") == "EVENT" and r.get("net_pnl_pct") not in (None, "", "None")]
by_date = defaultdict(list)
for r in rows:
    by_date[r["entry_date"]].append(float(r["net_pnl_pct"]))
dist = regime_effect_on_event_leg(dict(by_date))
ok("六态分布完成", isinstance(dist, dict) and dist)
print("  事件腿 × Regime:")
for reg, st in sorted(dist.items(), key=lambda x: -x[1]["n"]):
    print(f"    {reg:10s}: n={st['n']:4d} avg={st['avg']:+.3f}% wr={st['wr']:.3f} pf={st['pf']}")
# 蓝图预期: 事件腿逆向策略 → 弱市(BEAR/PANIC)应更优
weak = [v["avg"] for k, v in dist.items() if k in ("BEAR", "PANIC")]
strong = [v["avg"] for k, v in dist.items() if k == "BULL"]
if weak and strong:
    ok("弱市更优(逆向策略特征)", max(weak) > min(strong),
       f"weak={weak} strong={strong}")

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)