# -*- coding: utf-8 -*-
"""M1 MARGIN_CONFIRMED_SMC_STRUCTURE_TAKEOVER - outcome-free seed builder.

SMC main line (fixed, no look-ahead): swing low -> SSL sweep -> CHOCH/BOS event ->
demand OB POI -> touch -> reclaim -> eligible next-open entry (from v88_reverify).
Margin confirmation (PIT, D-1 disclosed): RCHANGE5DCP>0 OR RZJME5D>0.
Control M0 = same SMC without margin confirmation.

Frozen parameters (pre-registration): pivot 3/3, sweep 0.3%, POI half-body discount,
max_wait 5, SL zone_low*0.99, TP pre-entry swing high, max_hold 40, fee 0.20%.
"""
import csv, io, json, os, sqlite3, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERMES = r"E:\test\smc_project\hermes"
KLINE = os.path.join(HERMES, "kline_cache")
MARGIN_DB = r"E:\test\smc_project\margin\smc_margin.db"
OUT = r"E:\test\smc_project\margin"
PIVOT_L = PIVOT_R = 3
SWEEP_PCT = 0.003
LOOKBACK = 5
MAX_WAIT = 5


def f(x, d=0.0):
    try:
        return float(x) if x not in (None, "") else d
    except Exception:
        return d


def date8(b):
    s = "".join(c for c in str(b.get("t") or b.get("date") or "") if c.isdigit())
    return s[:8] if len(s) >= 8 else ""


def bars_for(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = date8(r)
        o, h, l, c = f(r.get("o")), f(r.get("h")), f(r.get("l")), f(r.get("c"))
        if t and o and h and l and c:
            out.append({"t": t, "o": o, "h": h, "l": l, "c": c})
    out.sort(key=lambda b: b["t"])
    return out


# ---------- SMC main line (fixed, outcome-free) ----------
def is_swing_low(ks, j):
    if j < PIVOT_L or j + PIVOT_R >= len(ks):
        return False
    lo = ks[j]["l"]
    return lo < min(ks[k]["l"] for k in range(j - PIVOT_L, j)) and lo <= min(ks[k]["l"] for k in range(j + 1, j + PIVOT_R + 1))


def is_swing_high(ks, j):
    if j < PIVOT_L or j + PIVOT_R >= len(ks):
        return False
    hi = ks[j]["h"]
    return hi > max(ks[k]["h"] for k in range(j - PIVOT_L, j)) and hi >= max(ks[k]["h"] for k in range(j + 1, j + PIVOT_R + 1))


def build_smc_seeds(symbol, ks):
    """Return list of SMC event seeds: {entry_idx, entry_date, entry_price, zone_low,
    zone_high, target, target_swing_idx, event_date, identity, ...} outcome-free."""
    seeds = []
    swing_lows = [j for j in range(PIVOT_L, len(ks) - PIVOT_R) if is_swing_low(ks, j)]
    for i in range(LOOKBACK, len(ks) - 2):
        b = ks[i]
        # SSL sweep: low breaches a confirmed swing low by >=0.3% and closes back above
        swept = None
        for j in reversed(swing_lows):
            if j + PIVOT_R >= i:
                continue
            ssl = ks[j]["l"]
            if b["l"] <= ssl * (1 - SWEEP_PCT) and b["c"] > ssl:
                swept = j
                break
        if swept is None:
            continue
        # response: next completed bar closes above sweep high (bullish)
        rsp = i + 1
        if rsp >= len(ks) or not (ks[rsp]["c"] > b["h"]):
            continue
        # trend up (HH/HL over lookback)
        win = ks[i - LOOKBACK + 1:i + 1]
        if not (win[-1]["h"] > win[0]["h"] and win[-1]["l"] > win[0]["l"]):
            continue
        # POI: first bearish bar after response
        ob_idx = None
        for k in range(rsp + 1, min(len(ks), rsp + 5)):
            if ks[k]["c"] < ks[k]["o"]:
                ob_idx = k
                break
        if ob_idx is None:
            continue
        ob = ks[ob_idx]
        zl = min(ob["o"], ob["c"], ob["l"])
        zh = min(max(ob["o"], ob["c"]), zl + (ob["h"] - zl) * 0.5)
        # discount check via swing range
        lo_i, hi_i = min(swept, i), max(swept, i)
        swing_low = min(ks[k]["l"] for k in range(lo_i, hi_i + 1))
        swing_high = max(ks[k]["h"] for k in range(lo_i, hi_i + 1))
        if zh > swing_low + (swing_high - swing_low) * 0.79:
            continue
        # touch + reclaim within max_wait, entry = next open
        touched = False
        t_idx = None
        entry = None
        for k in range(ob_idx + 1, min(len(ks) - 1, ob_idx + MAX_WAIT + 1)):
            bb = ks[k]
            if bb["l"] <= zl and bb["c"] <= zh:
                if touched:
                    break
                touched, t_idx = True, k
                continue
            if bb["c"] < zl:
                if touched:
                    break
                touched, t_idx = True, k
                continue
            if bb["l"] <= zh and bb["h"] >= zl:
                touched = True
                t_idx = t_idx if t_idx is not None else k
            if touched and k != t_idx and bb["c"] > zh:
                entry_idx = k + 1
                if entry_idx < len(ks):
                    entry = (entry_idx, k)
                break
        if entry is None:
            continue
        entry_idx, reclaim_idx = entry
        # target: pre-entry confirmed swing high (R2)
        tgt = None
        for j in range(entry_idx - PIVOT_R - 1, PIVOT_L - 1, -1):
            if is_swing_high(ks, j) and ks[j]["h"] > max(b["h"], zh):
                tgt = (j, ks[j]["h"])
                break
        if tgt is None:
            continue
        seeds.append({
            "symbol": symbol,
            "identity": f"{symbol}|{ks[entry_idx]['t']}|{ks[i]['t']}",
            "event_date": ks[i]["t"], "sweep_date": ks[swept]["t"],
            "zone_date": ks[ob_idx]["t"], "entry_date": ks[entry_idx]["t"],
            "event_idx": i, "entry_idx": entry_idx, "reclaim_idx": reclaim_idx,
            "sweep_idx": swept, "ob_idx": ob_idx, "touch_idx": t_idx,
            "zone_low": round(zl, 6), "zone_high": round(zh, 6),
            "entry_price": round(ks[entry_idx]["o"], 6),
            "target_swing_idx": tgt[0], "target_swing_date": ks[tgt[0]]["t"],
            "target": round(tgt[1], 6),
        })
    return seeds


def margin_confirm(conn, scode, entry_date):
    """PIT margin confirmation: use D-1 (last margin date < entry_date).
    Confirm if RCHANGE5DCP>0 (5-day financing balance change) OR RZJME5D>0 (5-day net buy).
    Returns (ok, info) or (None, None) if no margin row available (not a margin target)."""
    cur = conn.cursor()
    cur.execute("SELECT date,rchange5dcp,rzjme5d,rzye FROM margin_daily WHERE scode=? AND date<? ORDER BY date DESC LIMIT 1",
                (scode, entry_date))
    row = cur.fetchone()
    if not row:
        return None, None
    d, c5, j5, rzye = row
    ok = (c5 is not None and c5 > 0) or (j5 is not None and j5 > 0)
    return ok, {"margin_date": d, "rchange5dcp": c5, "rzjme5d": j5, "rzye": rzye}


def main():
    conn = sqlite3.connect(MARGIN_DB)
    m0_seeds, m1_seeds = [], []
    n_files = 0
    for p in sorted(os.listdir(KLINE)):
        if not p.endswith("_daily_750.json"):
            continue
        n_files += 1
        ks = bars_for(os.path.join(KLINE, p))
        if len(ks) < 200:
            continue
        sym = p.replace("_daily_750.json", "").replace("_", ".", 1)
        scode = sym.split(".")[0]
        for sd in build_smc_seeds(sym, ks):
            m0_seeds.append(sd)
            ok, info = margin_confirm(conn, scode, sd["entry_date"])
            if ok:
                m1_seeds.append({**sd, "margin": info})
        if n_files % 1000 == 0:
            print(f"  {n_files} files, M0 seeds {len(m0_seeds)}, M1 seeds {len(m1_seeds)}", flush=True)
    print(f"DONE: files={n_files} M0_seeds={len(m0_seeds)} M1_seeds={len(m1_seeds)}")
    with open(os.path.join(OUT, "M0_seeds.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(m0_seeds[0].keys()) if m0_seeds else ["symbol"])
        w.writeheader()
        for s in m0_seeds:
            w.writerow(s)
    with open(os.path.join(OUT, "M1_seeds.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(m1_seeds[0].keys()) if m1_seeds else ["symbol"])
        w.writeheader()
        for s in m1_seeds:
            w.writerow(s)
    conn.close()
    print("seeds written to", OUT)


if __name__ == "__main__":
    main()
