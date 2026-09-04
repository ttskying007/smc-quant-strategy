# -*- coding: utf-8 -*-
"""检查挂单状态：PENDING_ORDER 挂单价 vs 当前实时价（为什么未成交）"""
import io, json, sys, time
sys.path.insert(0, r"E:\test\smc_project\research")
import paper_sim as ps
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# wait for monitor write to finish
time.sleep(2)
led = None
for _ in range(3):
    try:
        led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
        break
    except Exception:
        time.sleep(2)
if led is None:
    print("ledger 读取失败（监控写入中）")
    sys.exit()

pending = [t for t in led if t.get("status") == "PENDING_ORDER"]
print(f"挂单中: {len(pending)} 笔\n")

# get realtime prices
codes = [t["code"] for t in pending]
if codes:
    prices = ps.realtime_prices(codes)
    for t in pending:
        code = t["code"]
        entry = t.get("entry_price", 0)
        rp = prices.get(code)
        rp_s = f"{rp:.2f}" if rp else "获取失败"
        hit = "✅可成交(≤挂单价)" if (rp and entry and rp <= entry) else "未达(高于挂单价)"
        print(f"  {code} {t.get('name')} 挂单={entry} 实时={rp_s} → {hit}")
