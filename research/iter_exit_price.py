# -*- coding: utf-8 -*-
"""卖点价格合理性：分层 TP/SL 触发时的滑点分析
SL_HIT/TP 触发价 vs 实际 bar 收盘（触发当日滑点）"""
import json, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
import paper_sim as ps

led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
closed = [t for t in led if t.get("status") == "CLOSED"]
print(f"CLOSED {len(closed)} 笔\n")

# SL_HIT slippage: exit pnl vs theoretical SL pnl
sl_hits = [t for t in closed if "SL" in str(t.get("exit_reason", ""))]
tps = [t for t in closed if "TP" in str(t.get("exit_reason", "")) or t.get("exit_reason") == "HOLD_EXIT"]

print("=== SL_HIT 止损价格合理性 ===")
if sl_hits:
    for t in sl_hits[:6]:
        ep = t.get("entry_price") or t.get("filled_price") or 0
        sl = t.get("sl_price") or 0
        pnl = t.get("pnl_pct")
        sl_pnl = round((sl / ep - 1) * 100 - 0.20, 4) if ep and sl else 0
        slippage = (pnl or 0) - sl_pnl
        print(f"  {t.get('code')} {t.get('name')} ep={ep} SL={sl} pnl={pnl}% 理论SL={sl_pnl}% 滑点={slippage:+.2f}pp exit={t.get('exit_reason')}")

print("\n=== TP 止盈价格合理性 ===")
if tps:
    for t in tps[:6]:
        ep = t.get("entry_price") or t.get("filled_price") or 0
        tp = t.get("tp_price") or 0
        pnl = t.get("pnl_pct")
        tp_pnl = round((tp / ep - 1) * 100 - 0.20, 4) if ep and tp else 0
        slippage = (pnl or 0) - tp_pnl
        print(f"  {t.get('code')} {t.get('name')} ep={ep} TP={tp} pnl={pnl}% 理论TP={tp_pnl}% 滑点={slippage:+.2f}pp exit={t.get('exit_reason')}")

# summary
if sl_hits:
    ep0 = [t.get("entry_price") or t.get("filled_price") or 0 for t in sl_hits]
    sl0 = [t.get("sl_price") or 0 for t in sl_hits]
    pnl0 = [t.get("pnl_pct", 0) for t in sl_hits]
    theory = [round((sl0[i] / ep0[i] - 1) * 100 - 0.20, 4) if ep0[i] else 0 for i in range(len(sl_hits))]
    slips = [pnl0[i] - theory[i] for i in range(len(sl_hits))]
    if slips:
        print(f"\nSL_HIT 平均滑点: {sum(slips)/len(slips):+.2f}pp（正=成交价优于SL，负=滑点损失）")
