# -*- coding: utf-8 -*-
"""R37: PAPER 持仓敞口快报 (开盘前审查)
对 OPEN/FILLED 订单: hold_days / mark_pnl / 距SL空间 / 距TP空间 / 集中度。
READ-ONLY, 输出 handover/r37_paper_exposure.json
"""
import json, os, sys, datetime
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
led = json.load(open(os.path.join(HERE, "paper_ledger.json"), encoding="utf-8"))
led = led if isinstance(led, list) else led.get("orders", [])

open_st = {"OPEN", "FILLED", "PENDING"}
ops = [o for o in led if o.get("status") in open_st]
today = datetime.date(2026, 9, 20)

def days(a):
    try:
        d = datetime.date.fromisoformat(str(a)[:10])
        return (today - d).days
    except Exception:
        return None

def f(x):
    try: return float(x)
    except Exception: return None

rep = {"asof": str(today), "n_open": len(ops), "orders": []}
tot_mark = 0.0
for o in ops:
    ep = f(o.get("entry_price")); mp = f(o.get("mark_price"))
    sl = f(o.get("sl_price") or o.get("sl")); tp = f(o.get("tp_price") or o.get("tp2") or o.get("tp"))
    pnl = (mp/ep - 1) * 100 if (ep and mp) else f(o.get("mark_pnl_pct"))
    rec = {
        "code": o.get("code"), "name": o.get("name"), "status": o.get("status"),
        "entry_date": o.get("entry_date") or o.get("pick_date"), "hold_days": days(o.get("entry_date") or o.get("pick_date")),
        "entry": ep, "mark": mp, "pnl_pct": round(pnl, 2) if pnl is not None else None,
        "sl_dist_pct": round((ep - sl) / ep * 100, 2) if (ep and sl) else None,
        "tp_room_pct": round((tp - mp) / mp * 100, 2) if (tp and mp) else None,
        "family": o.get("family") or o.get("signal_combo") or o.get("source"),
    }
    rep["orders"].append(rec)
    if pnl is not None: tot_mark += pnl

rep["mark_pnl_sum_pct"] = round(tot_mark, 2)
neg = [o for o in rep["orders"] if (o["pnl_pct"] or 0) < 0]
rep["underwater_n"] = len(neg)
rep["underwater_avg"] = round(sum(o["pnl_pct"] for o in neg)/len(neg), 2) if neg else 0

print(f"活跃订单: {rep['n_open']}  浮动合计 {rep['mark_pnl_sum_pct']:+.2f}%  水下 {rep['underwater_n']} 笔(avg {rep['underwater_avg']}%)")
for o in rep["orders"]:
    print(f"  {o['code']} {o.get('name') or ''} {o['status']:<8} hold={o['hold_days']}d pnl={o['pnl_pct']}% SL余量={o['sl_dist_pct']}% TP空间={o['tp_room_pct']}%")

json.dump(rep, open(os.path.join(HERE, "handover", "r37_paper_exposure.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("写出 handover/r37_paper_exposure.json")
