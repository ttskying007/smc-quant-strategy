# -*- coding: utf-8 -*-
"""Paper holdings 8-19 loss analysis: market beta vs stock-specific?
Check: 8-18->8-19 return distribution of 58 holdings vs market (600519/000001)."""
import json, io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))

rets = []
for t in led:
    code = t["code"]
    ex = "SH" if code.startswith("6") else "SZ"
    p = os.path.join(KT, f"{code}_{ex}_daily_800.json")
    if not os.path.exists(p):
        continue
    raw = json.load(open(p, encoding="utf-8"))
    dates = [b["t"] for b in raw]
    if "20260818" in dates and "20260819" in dates:
        i = dates.index("20260818")
        c18 = raw[i]["c"]
        c19 = raw[i + 1]["c"]
        if c18 > 0:
            rets.append((code, (c19 / c18 - 1) * 100))
print(f"持仓 8-18->8-19 收益: {len(rets)} 只")
if rets:
    vals = [r for _, r in rets]
    avg = sum(vals) / len(vals)
    neg = sum(1 for v in vals if v < 0)
    print(f"  平均: {avg:+.2f}% | 下跌: {neg}/{len(vals)} ({100*neg/len(vals):.0f}%)")
    vals.sort()
    print(f"  分布: min={vals[0]:+.1f}% med={vals[len(vals)//2]:+.1f}% max={vals[-1]:+.1f}%")

# market refs
for ref in ("600519_SH", "000001_SZ"):
    p = os.path.join(KT, ref + "_daily_800.json")
    if os.path.exists(p):
        raw = json.load(open(p, encoding="utf-8"))
        dates = [b["t"] for b in raw]
        if "20260818" in dates and "20260819" in dates:
            i = dates.index("20260818")
            r = (raw[i + 1]["c"] / raw[i]["c"] - 1) * 100
            print(f"  {ref}: 8-19 {r:+.2f}%")
