# -*- coding: utf-8 -*-
"""大宗交易折价接筹信号回测：折价大宗（大资金低价接筹）→ 次日入场 → 10日
（本地 K 线到 8-19，6-7 月信号有完整未来）"""
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

BT = r"E:\test\smc_project\hermes\blocktrade_cache\blocktrade_2026h2.json"
KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
code2file = {f.split("_")[0]: os.path.join(KT, f) for f in os.listdir(KT) if f.endswith("_daily_800.json")}
bar_cache = {}
def bars_of(code):
    if code not in bar_cache:
        p = code2file.get(code)
        if not p:
            bar_cache[code] = []
            return bar_cache[code]
        raw = json.load(open(p, encoding="utf-8"))
        bs = []
        for r in raw:
            t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
            if t and r.get("o") and r.get("h") and r.get("l") and r.get("c"):
                bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"])})
        bs.sort(key=lambda b: b["t"])
        bar_cache[code] = bs
    return bar_cache[code]

rows = json.load(open(BT, encoding="utf-8"))
print("大宗交易:", len(rows))


def build(prem_max, amt_min):
    trades = []
    seen = set()
    for r in rows:
        code = str(r.get("SECURITY_CODE", ""))
        td = str(r.get("TRADE_DATE", ""))[:10].replace("-", "")
        if (code, td) in seen:
            continue
        seen.add((code, td))
        prem = float(r.get("PREMIUM_RATIO") or 0)
        amt = float(r.get("DEAL_AMT") or 0)
        if prem > prem_max or amt < amt_min:
            continue
        bs = bars_of(code)
        if not bs:
            continue
        dates = [b["t"] for b in bs]
        if td not in dates:
            continue
        i = dates.index(td)
        if i + 1 >= len(bs) or i + 11 >= len(bs):
            continue
        ep = bs[i + 1]["o"]
        if ep <= 0:
            continue
        trades.append({"entry_date": bs[i + 1]["t"],
                       "net_pnl_pct": round((bs[i + 11]["c"] / ep - 1) * 100 - 0.20, 4), "t1_violation": "False"})
    return trades


def report(label, rs):
    if len(rs) < 100:
        print(f"{label}: n={len(rs)} (过小)")
        return
    for t in rs:
        t["t1_violation"] = "False"
        t["year"] = str(t["entry_date"])[:4]
    gate = check_economic_gate(rs)
    o = gate["overall"]
    line = f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']}"
    print(line)


print("\n=== 大宗交易折价接筹信号（10日持有）===")
report("全部大宗（折价或溢价）", build(1e9, 0))
report("折价（<0%）", build(0, 0))
report("折价>3%", build(-3, 0))
report("折价>5% + 金额>500万", build(-5, 5e6))
