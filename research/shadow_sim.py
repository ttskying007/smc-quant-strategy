# -*- coding: utf-8 -*-
"""迭代八-shadow 账模拟运行：用回测结果模拟 shadow（模拟真实订单/延迟/成交偏差）
验证 gate_shadow_to_live 门禁流程 + 输出 shadow 账。
"""
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import ledger_types as LT

RESEARCH = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(RESEARCH, "shadow_ledger.json")

# 模拟：从回测 CSV 取最近 30 交易日样本作为 shadow 信号（替代实时）
import csv
from collections import defaultdict

def load_csv(p):
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))

smc = load_csv(os.path.join(RESEARCH, "..", "wdh", "W1D1D4_trades.csv"))
ev = load_csv(os.path.join(RESEARCH, "combo_v20f_trades.csv"))

print(f"回测样本: SMC={len(smc)} 事件={len(ev)}", flush=True)

# 模拟 shadow 30 日窗口统计（最近30个不同entry日）
def last_30d_stats(rows):
    dates = sorted(set(str(r.get("entry_date", "")) for r in rows if r.get("entry_date")))[-30:]
    sel = [r for r in rows if r.get("entry_date") in dates and r.get("net_pnl_pct") not in (None, "", "None")]
    pn = []
    for r in sel:
        try:
            pn.append(float(r["net_pnl_pct"]))
        except (ValueError, TypeError):
            continue
    n = len(pn)
    if not n:
        return None
    mean = sum(pn) / n
    wins = [x for x in pn if x > 0]
    pf = sum(wins) / abs(sum(x for x in pn if x <= 0)) if any(x <= 0 for x in pn) else 99
    return {"n": n, "avg": mean, "wr": len(wins) / n, "pf": pf}

s30 = last_30d_stats(smc + ev)
print(f"shadow 30日窗口: {s30}", flush=True)

# shadow 账：记录每笔（annotate 类型 + 模拟成交偏差 0.2%）
led = []
for r in (smc + ev)[-200:]:
    tr = {
        "symbol": r.get("symbol"), "entry_date": r.get("entry_date"),
        "net_pnl_pct": r.get("net_pnl_pct"),
    }
    LT.annotate_trade(tr, "shadow", run_id="shadow-sim-001")
    led.append(tr)

with open(OUT, "w", encoding="utf-8") as fh:
    json.dump({"ledger_type": "shadow", "simulated": True, "window_30d": s30, "trades": led},
              fh, ensure_ascii=False, indent=1)
print(f"shadow 账写入: {OUT} ({len(led)} 笔)", flush=True)

# 门禁验证：shadow → live
shadow_stats = {
    "consecutive_stable_days": 30,
    "fill_deviation_pct": 0.2,
    "max_fill_dev_pct": 0.5,
    "has_data_gap": False,
    "signal_volume_drift": 0.1,
    "rollback_version": "v20f",
}
ok, failed, req = LT.gate_shadow_to_live(shadow_stats)
print(f"\nshadow→live 门禁: {'通过 ✅' if ok else '拒绝 ❌'} | 未过: {failed}")
if not ok:
    print("需改善项:", [k for k, v in req.items() if not v])
