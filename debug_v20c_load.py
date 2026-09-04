# -*- coding: utf-8 -*-
import csv, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
try:
    bt = []
    with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            row["net_pnl_pct"] = float(row.get("net_pnl_pct", 0))
            row["hold"] = 10 if row.get("src") == "CONT" else 15
            bt.append(row)
    print("加载成功:", len(bt))
    t = [x for x in bt if str(x.get("symbol", "")) == "000001.SZ"]
    print("000001:", len(t), t[0] if t else "")
except Exception as e:
    print("FAIL:", e)
