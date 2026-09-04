# -*- coding: utf-8 -*-
"""TP1/SL 距离分布：事件腿分层止盈止损相对入场的距离
验证 TP1（swing high）/SL（swing low）距离是否合理（不过近也不过远）"""
import io, json, os, sqlite3, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
active = [t for t in led if t.get("tp1")]
print(f"持仓样本: {len(active)}\n")

tp1_d = []
sl_d = []
for t in active:
    ep = t.get("entry_price") or t.get("filled_price") or 0
    if ep <= 0:
        continue
    if t.get("tp1"):
        tp1_d.append((t["tp1"] / ep - 1) * 100)
    if t.get("sl1"):
        sl_d.append((t["sl1"] / ep - 1) * 100)

print("=== TP1 相对入场距离（%）===")
if tp1_d:
    tp1_s = sorted(tp1_d)
    n = len(tp1_s)
    print(f"  P25: {tp1_s[n//4]:+.1f}% | P50: {tp1_s[n//2]:+.1f}% | P75: {tp1_s[3*n//4]:+.1f}%")
    print(f"  <2%: {sum(1 for x in tp1_s if x<2)/n:.0%} | 2-5%: {sum(1 for x in tp1_s if 2<=x<5)/n:.0%} | >5%: {sum(1 for x in tp1_s if x>=5)/n:.0%}")

print("\n=== SL1 相对入场距离（%）===")
if sl_d:
    sl_s = sorted(sl_d)
    n = len(sl_s)
    print(f"  P25: {sl_s[n//4]:+.1f}% | P50: {sl_s[n//2]:+.1f}% | P75: {sl_s[3*n//4]:+.1f}%")
    print(f"  >-3%: {sum(1 for x in sl_s if x>-3)/n:.0%} | -3~-10%: {sum(1 for x in sl_s if -10<=x<=-3)/n:.0%} | <-10%: {sum(1 for x in sl_s if x<-10)/n:.0%}")

# risk-reward
print("\n=== 盈亏比（TP1/SL 距离比）===")
rr = []
for t in active:
    ep = t.get("entry_price") or t.get("filled_price") or 0
    if ep <= 0:
        continue
    if t.get("tp1") and t.get("sl1"):
        up = (t["tp1"] / ep - 1) * 100
        down = (1 - t["sl1"] / ep) * 100
        if down > 0:
            rr.append(up / down)
if rr:
    rr_s = sorted(rr)
    n = len(rr_s)
    print(f"  中位盈亏比: {rr_s[n//2]:.2f} | P25: {rr_s[n//4]:.2f} | P75: {rr_s[3*n//4]:.2f}")
