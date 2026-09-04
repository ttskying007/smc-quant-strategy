# -*- coding: utf-8 -*-
"""Experiment A: is 2026 (esp May-Jul) a systematic market downturn?
Check market-wide distribution of daily returns by month 2024-2026.
Also: TP2 trade pnl vs market context (equal-weight market return on trade window)."""
import io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
OUT = r"E:\test\smc_project\research"
os.makedirs(OUT, exist_ok=True)


def bars(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        if t and r.get("c") and r.get("o"):
            out.append({"t": t, "c": float(r["c"]), "o": float(r["o"])})
    out.sort(key=lambda b: b["t"])
    return out


# 1. market-wide daily return distribution by month (equal-weight sample of 500 stocks)
import random
random.seed(42)
files = sorted(os.listdir(KT))[:]  # all
sample = random.sample(files, min(500, len(files)))
monthly_ret = defaultdict(list)   # month -> list of market daily returns
market = defaultdict(dict)        # date -> avg return
for f in sample:
    b = bars(os.path.join(KT, f))
    prev = None
    for x in b:
        if prev:
            r = x["c"] / prev - 1
            market[x["t"]][f] = r
        prev = x["c"]
print("sample stocks:", len(sample))
# aggregate by date
date_ret = {}
for d, vals in market.items():
    date_ret[d] = sum(vals.values()) / len(vals)
for d in sorted(date_ret):
    monthly_ret[d[:6]].append(date_ret[d])

print("\n=== 全市场等权日均收益（按月）===")
for m in sorted(monthly_ret):
    rs = monthly_ret[m]
    if m < "202401":
        continue
    avg = sum(rs) / len(rs)
    neg = sum(1 for r in rs if r < 0) / len(rs)
    cum = sum(rs)
    flag = " <<<" if avg < -0.001 else ""
    print(f"  {m}: n={len(rs)} 日均={avg*100:+.3f}% 月累计={cum*100:+.1f}% 下跌日占比={neg*100:.0f}%{flag}")
