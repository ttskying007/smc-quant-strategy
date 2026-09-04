# -*- coding: utf-8 -*-
"""标记不合规持仓：修复前选入（无阶段/ADX 过滤）的 4 笔 → 前端显示备注"""
import io, json, sys
sys.path.insert(0, r"E:\test\smc_project\research")
import paper_sim as ps
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

violations = {"000651": "UPTREND/ADX38(修复前选入)", "603893": "UPTREND/ADX8(修复前选入)",
              "301078": "ADX13(修复前选入)", "603986": "ADX4(修复前选入)"}

led = ps.load_ledger()
n = 0
for t in led:
    if t.get("code") in violations and str(t.get("signal_date", "") or t.get("disclose_date", "")) >= "2026-08-17":
        t["note"] = "⚠️ 修复前选入（不满足阶段/ADX 过滤）" + violations[t["code"]]
        n += 1
ps.save_ledger(led)
print(f"标记 {n} 笔不合规持仓")
# verify sync
for m in ps.MIRRORS:
    import os
    print(f"  mirror {'OK' if os.path.exists(m) else 'MISS'}: {os.path.basename(os.path.dirname(m))}")
