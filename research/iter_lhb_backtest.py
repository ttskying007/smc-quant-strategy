# -*- coding: utf-8 -*-
"""龙虎榜信号完整回测：2026-06~07 净买信号 → 次日开盘入场 → 5/10日
（本地 K 线到 8-19，6-7 月信号有完整未来）"""
import io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

LHB = r"E:\test\smc_project\hermes\lhb_cache"
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


def build_trades(threshold):
    trades = []
    for f in sorted(os.listdir(LHB)):
        rows = json.load(open(os.path.join(LHB, f), encoding="utf-8"))
        for r in rows:
            code = str(r.get("SECURITY_CODE", ""))
            net = float(r.get("BILLBOARD_NET_AMT") or 0)
            if net < threshold:
                continue
            bs = bars_of(code)
            if not bs:
                continue
            dates = [b["t"] for b in bs]
            td = str(r.get("TRADE_DATE", ""))[:10].replace("-", "")
            if td not in dates:
                continue
            i = dates.index(td)
            if i + 1 >= len(bs) or i + 11 >= len(bs):
                continue
            ep = bs[i + 1]["o"]
            if ep <= 0:
                continue
            trades.append({"entry_date": bs[i + 1]["t"],
                           "net_pnl_pct": round((bs[i + 11]["c"] / ep - 1) * 100 - 0.20, 4),
                           "t1_violation": "False"})
    return trades


def report(label, rs):
    if len(rs) < 50:
        print(f"{label}: n={len(rs)} (过小)")
        return
    for t in rs:
        t["t1_violation"] = "False"
        t["year"] = str(t["entry_date"])[:4]
    gate = check_economic_gate(rs)
    o = gate["overall"]
    line = f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']}"
    print(line)


print("\n=== 龙虎榜信号（2026-06~08，10日持有）===")
report("全部龙虎榜", build_trades(-1e18))
report("净买>0", build_trades(0))
report("净买>500万", build_trades(5e6))
report("净买>1000万", build_trades(1e7))
report("净买>5000万", build_trades(5e7))
