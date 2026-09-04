# -*- coding: utf-8 -*-
"""SSL sweep depth layering: deeper liquidity raid (>1%, >2%) = stronger harvest?
Deepen the ONLY validated SMC signal (SSL sweep chain)."""
import io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\wdh")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
import wdh_engine as we
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"


def bars(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        o, h, l, c, v = we.f(r.get("o")), we.f(r.get("h")), we.f(r.get("l")), we.f(r.get("c")), we.f(r.get("v"))
        if t and o and h and l and c:
            out.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v})
    out.sort(key=lambda b: b["t"])
    return out


def sweep_depth(daily, i, swept):
    """How deep the sweep went below the SSL swing low (%)."""
    ssl = daily[swept]["l"]
    if ssl <= 0:
        return 0
    return (daily[i]["l"] - ssl) / ssl  # negative = below SSL


bar_cache = {}
def get_bars(sym):
    if sym not in bar_cache:
        bar_cache[sym] = bars(os.path.join(KT, sym.replace(".", "_") + "_daily_800.json"))
    return bar_cache[sym]


rows = []
n = 0
for p in sorted(os.listdir(KT)):
    if not p.endswith("_daily_800.json"):
        continue
    n += 1
    daily = bars(os.path.join(KT, p))
    if len(daily) < 400:
        continue
    sym = p.replace("_daily_800.json", "").replace("_", ".", 1)
    for sd in we.build_seeds(sym, daily):
        r20 = sd.get("r20")
        if r20 == "" or r20 is None or not (0 <= float(r20) < 0.15):
            continue
        entry_idx = int(sd["entry_idx"])
        if entry_idx < 61:
            continue
        w60 = daily[entry_idx - 60:entry_idx]
        ret60 = w60[-1]["c"] / w60[0]["c"] - 1
        if ret60 <= 0:
            continue  # UPTREND/MARKUP
        tr = we.replay_tp2(sd, daily)
        if not tr:
            continue
        # sweep depth: find the sweep bar (SSL low breach) - use seed sweep info via date
        swept_date = str(sd.get("sweep_date") or "")
        si = next((k for k, b in enumerate(daily) if b["t"] == swept_date), entry_idx - 3)
        depth = sweep_depth(daily, si, None) if False else None
        # simpler: depth = how far low went below zone_low on touch/reclaim period
        zl = we.f(sd["zone_low"])
        # sweep depth proxy: min low between sweep and entry vs entry price
        lo_min = min(daily[k]["l"] for k in range(max(0, entry_idx - 15), entry_idx))
        depth = (lo_min / zl - 1) if zl else 0  # negative = below zone
        rows.append({"symbol": sym, "entry_date": tr["entry_date"], "net_pnl_pct": tr["net_pnl_pct"],
                     "depth": depth, "t1_violation": "False"})
    if n % 1500 == 0:
        print(f"  {n} files, rows {len(rows)}", flush=True)
print(f"rows: {len(rows)}")


def report(label, rs):
    if len(rs) < 50:
        print(f"{label}: n={len(rs)} (过小)"); return
    for t in rs:
        t["t1_violation"] = str(t.get("t1_violation", "")).lower() in ("true", "1", "yes")
        t["year"] = str(t["entry_date"])[:4]
    gate = check_economic_gate(rs)
    o = gate["overall"]
    print(f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']}")
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if t["year"] == y]
        if ys:
            wy = sum(1 for t in ys if t["net_pnl_pct"] > 0)
            print(f"    {y}: n={len(ys)} WR={100*wy/len(ys):.0f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%")


print("\n=== SSL sweep 深度分层 ===")
valid = [r for r in rows if r["depth"] is not None]
report("基线（全部 SSL sweep）", valid)
report("深度 >1%（低于zone 1%以上）", [r for r in valid if r["depth"] < -0.01])
report("深度 >2%", [r for r in valid if r["depth"] < -0.02])
report("深度 >3%", [r for r in valid if r["depth"] < -0.03])
report("浅扫（<1%）", [r for r in valid if r["depth"] >= -0.01])
