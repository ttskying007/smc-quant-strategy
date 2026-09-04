# -*- coding: utf-8 -*-
"""多周期确认：周线趋势 + 日线延续腿（MARKUP结构+VWAP5%+低波动+固定10日）
用户核心"不同周期组合"—— 周线 UPTREND 确认日线信号"""
import io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
WK = r"E:\test\smc_project\hermes\kline_cache"
PIVOT = 3
FEE = 0.20


def bars(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
            out.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"]), "v": float(r["v"])})
    out.sort(key=lambda b: b["t"])
    return out


def weekly_file(sym):
    return os.path.join(WK, sym.replace(".", "_") + "_weekly_200.json")


def weekly_up(filepath, entry_date):
    """Weekly trend up: last weekly close above 12-week MA (weekly uptrend)."""
    try:
        raw = json.load(open(filepath, encoding="utf-8"))
    except Exception:
        return None
    wk = []
    for r in raw:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        if t and r.get("c"):
            wk.append({"t": t, "c": float(r["c"])})
    wk.sort(key=lambda b: b["t"])
    if len(wk) < 13:
        return None
    # find weekly bar containing entry_date
    i = None
    for k, b in enumerate(wk):
        if b["t"] >= entry_date[:6]:
            i = k
            break
    if i is None or i < 12:
        return None
    ma12 = sum(wk[k]["c"] for k in range(i - 11, i + 1)) / 12
    return wk[i]["c"] > ma12  # weekly close above 12w MA = weekly uptrend


def is_swing_low(bs, j):
    if j < PIVOT or j + PIVOT >= len(bs):
        return False
    return bs[j]["l"] < min(bs[k]["l"] for k in range(j - PIVOT, j)) and bs[j]["l"] <= min(bs[k]["l"] for k in range(j + 1, j + PIVOT + 1))


def stage_detailed(bs, i):
    if i < 61:
        return None
    w60 = bs[i - 60:i]
    ret60 = w60[-1]["c"] / w60[0]["c"] - 1
    v20 = sum(x["v"] for x in bs[i - 20:i]) / 20
    v60 = sum(x["v"] for x in bs[i - 60:i]) / 60
    vt = v20 / v60 if v60 else 1
    if ret60 < -0.15 and vt < 0.9:
        return "ACCUM"
    if ret60 > 0.30 and vt > 1.3:
        return "DISTRIB"
    if ret60 > 0.20 and vt > 1.1:
        return "MARKUP"
    if ret60 > 0:
        return "UPTREND"
    return "DOWNTREND"


all_rows = []
wk_checked = 0
wk_up_true = 0
n = 0
for p in sorted(os.listdir(KT)):
    if not p.endswith("_daily_800.json"):
        continue
    n += 1
    daily = bars(os.path.join(KT, p))
    if len(daily) < 400:
        continue
    sym = p.replace("_daily_800.json", "").replace("_", ".", 1)
    wf = weekly_file(sym)
    for i in range(80, len(daily) - 15):
        st = stage_detailed(daily, i)
        if st != "MARKUP":
            continue
        sl_tmp = None
        for j in range(i, PIVOT - 1, -1):
            if is_swing_low(daily, j):
                sl_tmp = daily[j]["l"]
                break
        if sl_tmp is None:
            continue
        if not (daily[i]["l"] <= sl_tmp * 1.01 and daily[i - 1]["c"] > sl_tmp):
            continue
        if daily[i]["c"] <= sl_tmp:
            continue
        entry_idx = i + 1
        if entry_idx >= len(daily) or entry_idx < 20 or entry_idx + 10 >= len(daily):
            continue
        ep = daily[entry_idx]["o"]
        if sl_tmp >= ep:
            continue
        pv = sum(daily[k]["c"] * daily[k]["v"] for k in range(entry_idx - 19, entry_idx + 1))
        vol = sum(daily[k]["v"] for k in range(entry_idx - 19, entry_idx + 1))
        if vol <= 0:
            continue
        vw = pv / vol
        if (daily[entry_idx]["c"] - vw) / vw < 0.05:
            continue
        w20 = daily[entry_idx - 20:entry_idx]
        vol20 = sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20 if len(w20) == 20 else 0
        wk_up = weekly_up(wf, daily[entry_idx]["t"])
        wk_checked += 1
        if wk_up:
            wk_up_true += 1
        all_rows.append({"symbol": sym, "entry_date": daily[entry_idx]["t"], "vol20": vol20,
                         "wk_up": wk_up, "net_pnl_pct": round((daily[entry_idx + 10]["c"] / ep - 1) * 100 - FEE, 4)})
    if n % 1500 == 0:
        print(f"  {n} files, rows {len(all_rows)}", flush=True)
print(f"rows: {len(all_rows)}, wk_checked: {wk_checked}, wk_up: {wk_up_true} ({100*wk_up_true/max(1,wk_checked):.0f}%)")
vols = sorted(r["vol20"] for r in all_rows)
vmed = vols[len(vols) // 2]


def report(label, rs):
    if len(rs) < 200:
        print(f"{label}: n={len(rs)} (过小)")
        return
    for t in rs:
        t["t1_violation"] = "False"
        t["year"] = str(t["entry_date"])[:4]
    gate = check_economic_gate(rs)
    o = gate["overall"]
    line = f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']}"
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if t["year"] == y]
        if ys:
            line += f" | {y}:{sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%"
    print(line)


print("\n=== 多周期确认（周线趋势 + 日线延续）===")
report("延续腿基线（低波动）", [r for r in all_rows if r["vol20"] < vmed])
report("+周线上行", [r for r in all_rows if r["vol20"] < vmed and r["wk_up"] is True])
report("周线非上行", [r for r in all_rows if r["vol20"] < vmed and r["wk_up"] is False])
