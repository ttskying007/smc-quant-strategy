# -*- coding: utf-8 -*-
"""延续腿分层 TP/SL 验证：延续腿用分层出场 vs 固定 10 日
（延续是快速兑现型 —— 分层是否适用？）"""
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
PIVOT = 3


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


def is_swing_low(bs, j):
    if j < PIVOT or j + PIVOT >= len(bs):
        return False
    return bs[j]["l"] < min(bs[k]["l"] for k in range(j - PIVOT, j)) and bs[j]["l"] <= min(bs[k]["l"] for k in range(j + 1, j + PIVOT + 1))


def is_swing_high(bs, j):
    if j < PIVOT or j + PIVOT >= len(bs):
        return False
    return bs[j]["h"] > max(bs[k]["h"] for k in range(j - PIVOT, j)) and bs[j]["h"] >= max(bs[k]["h"] for k in range(j + 1, j + PIVOT + 1))


def stage_of(bs, i):
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
    return "UPTREND" if ret60 > 0 else "DOWNTREND"


def collect_signals():
    sigs = []
    vols = []
    for p in sorted(os.listdir(KT)):
        if not p.endswith("_daily_800.json"):
            continue
        daily = bars(os.path.join(KT, p))
        if len(daily) < 80:
            continue
        w20 = daily[-21:-1] if len(daily) >= 21 else daily
        if len(w20) == 20:
            vols.append(sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20)
        if len(vols) > 3000:
            break
    vols.sort()
    V_MED = vols[len(vols) // 2]
    for p in sorted(os.listdir(KT)):
        if not p.endswith("_daily_800.json"):
            continue
        daily = bars(os.path.join(KT, p))
        if len(daily) < 400:
            continue
        for i in range(80, len(daily) - 11):
            st = stage_of(daily, i)
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
            if entry_idx >= len(daily) or entry_idx < 20:
                continue
            ep = daily[entry_idx]["o"]
            if sl_tmp >= ep:
                continue
            pv = sum(daily[k]["c"] * daily[k]["v"] for k in range(entry_idx - 19, entry_idx + 1))
            vol = sum(daily[k]["v"] for k in range(entry_idx - 19, entry_idx + 1))
            if vol <= 0:
                continue
            vw = pv / vol
            if (daily[entry_idx]["c"] - vw) / vw < 0.10:
                continue
            w20 = daily[entry_idx - 20:entry_idx]
            vol20 = sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20 if len(w20) == 20 else 0
            if vol20 >= V_MED:
                continue
            # structure levels
            highs = []
            for j in range(i - 1, max(0, i - 40), -1):
                if is_swing_high(daily, j):
                    highs.append(daily[j]["h"])
                if len(highs) >= 3:
                    break
            if not highs:
                continue
            highs.sort()
            sigs.append({"daily": daily, "entry_idx": entry_idx, "ep": ep,
                         "tp1": highs[0], "tp2": highs[1] if len(highs) > 1 else highs[0] * 1.03,
                         "tp3": highs[-1], "sl1": sl_tmp * 0.99,
                         "entry_date": daily[entry_idx]["t"]})
    return sigs


sigs = collect_signals()
print("延续信号:", len(sigs))


def fixed_hold(hold=10):
    out = []
    for s in sigs:
        i = s["entry_idx"]
        if i + hold >= len(s["daily"]):
            continue
        out.append({"entry_date": s["entry_date"],
                    "net_pnl_pct": round((s["daily"][i + hold]["c"] / s["ep"] - 1) * 100 - 0.20, 4)})
    return out


def tiered():
    out = []
    for s in sigs:
        ep = s["ep"]
        remaining = 1.0
        pnl = 0.0
        be = False
        for k in range(s["entry_idx"] + 1, min(len(s["daily"]), s["entry_idx"] + 11)):
            bb = s["daily"][k]
            stop = ep if be else s["sl1"]
            if bb["l"] <= stop:
                pnl += remaining * (stop / ep - 1) * 100
                remaining = 0
                break
            if not be and bb["h"] >= s["tp1"]:
                pnl += 0.3 * (s["tp1"] / ep - 1) * 100
                remaining = 0.7
                be = True
            elif be and bb["h"] >= s["tp2"]:
                pnl += remaining * (s["tp2"] / ep - 1) * 100
                remaining = 0
                break
            elif be and bb["h"] >= s["tp3"]:
                pnl += remaining * (s["tp3"] / ep - 1) * 100
                remaining = 0
                break
        if remaining > 0:
            last = s["daily"][min(len(s["daily"]), s["entry_idx"] + 10) - 1]["c"]
            pnl += remaining * (last / ep - 1) * 100
        out.append({"entry_date": s["entry_date"], "net_pnl_pct": round(pnl - 0.20, 4)})
    return out


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
    print(line)


print("\n=== 延续腿分层 vs 固定10日 ===")
report("固定10日（当前）", fixed_hold(10))
report("分层TP/SL", tiered())
