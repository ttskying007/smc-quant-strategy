# -*- coding: utf-8 -*-
"""RANGE-skip test (historical v255 hint: RANGE state = 44% WR, must skip).
Use simplified ADX(14) to detect trendless (RANGE) states; test skipping them
in the three-TF TP2-R20 SMC signal (frozen replay)."""
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
        o, h, l, c = we.f(r.get("o")), we.f(r.get("h")), we.f(r.get("l")), we.f(r.get("c"))
        if t and o and h and l and c:
            out.append({"t": t, "o": o, "h": h, "l": l, "c": c})
    out.sort(key=lambda b: b["t"])
    return out


def adx14(daily, i):
    """Simplified ADX(14) at bar i (PIT). Returns None if insufficient."""
    if i < 30:
        return None
    # directional movement
    plus_dm = 0.0
    minus_dm = 0.0
    tr_sum = 0.0
    for k in range(i - 14, i):
        h, l, pc = daily[k]["h"], daily[k]["l"], daily[k - 1]["c"]
        up = h - daily[k - 1]["h"]
        dn = daily[k - 1]["l"] - l
        plus_dm += up if (up > dn and up > 0) else 0
        minus_dm += dn if (dn > up and dn > 0) else 0
        tr = max(h - l, abs(h - pc), abs(l - pc))
        tr_sum += tr
    if tr_sum <= 0:
        return None
    pdi = 100 * plus_dm / tr_sum
    mdi = 100 * minus_dm / tr_sum
    if pdi + mdi == 0:
        return None
    dx = 100 * abs(pdi - mdi) / (pdi + mdi)
    return dx


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
        if r20 == "" or r20 is None:
            continue
        if not (0 <= float(r20) < 0.15):
            continue
        tr = we.replay_tp2(sd, daily)
        if not tr:
            continue
        entry_idx = int(sd["entry_idx"])
        adx = adx14(daily, entry_idx)
        rows.append({"symbol": sym, "entry_date": tr["entry_date"], "net_pnl_pct": tr["net_pnl_pct"],
                     "adx": adx, "t1_violation": "False"})
    if n % 1500 == 0:
        print(f"  {n} files, rows {len(rows)}", flush=True)
print(f"rows: {len(rows)}, with adx: {sum(1 for r in rows if r['adx'] is not None)}")
if rows:
    adxs = [r["adx"] for r in rows if r["adx"] is not None]
    if adxs:
        print(f"ADX 分布: min={min(adxs):.0f} med={sorted(adxs)[len(adxs)//2]:.0f} max={max(adxs):.0f}")


def report(label, rs):
    if len(rs) < 80:
        print(f"{label}: n={len(rs)} (过小)"); return
    for t in rs:
        t["t1_violation"] = str(t.get("t1_violation", "")).lower() in ("true", "1", "yes")
    gate = check_economic_gate(rs)
    o = gate["overall"]
    print(f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']}")
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if str(t["entry_date"]).startswith(y)]
        if ys:
            wy = sum(1 for t in ys if t["net_pnl_pct"] > 0)
            print(f"    {y}: n={len(ys)} WR={100*wy/len(ys):.0f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%")


print("\n=== RANGE 跳过（ADX<20 = 盘整）===")
valid = [r for r in rows if r["adx"] is not None]
report("基线（全部）", valid)
report("跳过 RANGE（ADX>=20）", [r for r in valid if r["adx"] >= 20])
report("仅 RANGE（ADX<20）", [r for r in valid if r["adx"] < 20])
report("跳过 RANGE（ADX>=25 严格）", [r for r in valid if r["adx"] >= 25])
