# -*- coding: utf-8 -*-
"""check_r88_production.py — 验收: 定时任务跑的订单是否带 v23/Jev 双标"""
import json, sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = os.path.dirname(os.path.abspath(__file__))
led = json.load(open(os.path.join(ROOT, "paper_ledger.json"), encoding="utf-8"))
orders = led if isinstance(led, list) else led.get("orders", [])
print(f"总订单: {len(orders)}")

recent = [o for o in orders if isinstance(o, dict) and str(o.get("signal_date") or "") >= "2026-09-18"]
print(f"9/18 以来订单: {len(recent)}\n")

ok_v23 = sum(1 for o in recent if o.get("v23"))
ok_jev = sum(1 for o in recent if o.get("jev"))
print(f"带 v23 标: {ok_v23}/{len(recent)}")
print(f"带 jev 判型: {ok_jev}/{len(recent)}\n")

for o in sorted(recent, key=lambda x: -int(str(x.get("signal_date") or "").replace("-", "")))[:15]:
    v, j = o.get("v23"), o.get("jev")
    vf = "w=" + str(v.get("weight")) + " [" + ",".join(v.get("flags") or []) + "]" if v else "未打v23"
    jf = "{}@{}".format(j.get("event_kind"), str(j.get("event_conf"))[:4]) if j else "无jev"
    print("  {} {} {} | {} | jev: {}".format(o.get("code"), o.get("signal_date"), o.get("status"), vf, jf))

# 漏斗计数器看上游是否空窗
p = os.path.join(ROOT, "combo_monitor_state.json")
if os.path.exists(p):
    m = json.load(open(p, encoding="utf-8"))
    hist = m.get("funnel_history") or []
    print("\n漏斗近期(最后5条):")
    for h in hist[-5:]:
        print(" ", h)
