# -*- coding: utf-8 -*-
import json, io, sys
sys.path.insert(0, r"E:\test\smc_project\research")
import paper_sim as ps
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
# check 3 SL_HIT positions: entry/sl vs current price
targets = ["000651", "300637", "301308"]
codes = []
for t in led:
    if t.get("code") in targets and t.get("status") == "CLOSED":
        print(f"{t.get('code')} {t.get('name')}: 入场={t.get('entry_price')} SL={t.get('sl_price')} TP={t.get('tp_price')} exit={t.get('exit_reason')} pnl={t.get('pnl_pct')}% filled={t.get('filled_at')} exit_at={t.get('exit_date','-')}")
        codes.append(t.get("code"))
# realtime prices
if codes:
    prices = ps.realtime_prices(codes)
    print(f"\n当前实时价: {prices}")
