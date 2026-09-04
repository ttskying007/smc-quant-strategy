# -*- coding: utf-8 -*-
"""分层 TP/SL 版组合回测：事件腿（分层出场）+ 延续腿（固定10日）+ SMC → v20c 升级验证
对比固定持有版 v20c"""
import io, json, os, sqlite3, sys, csv
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
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
            if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
                bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"]), "v": float(r["v"])})
        bs.sort(key=lambda b: b["t"])
        bar_cache[code] = bs
    return bar_cache[code]


def is_strong(title):
    t = str(title or "")
    if "回购" in t:
        if "完成" in t or "进度" in t or "进展" in t or "结果" in t or "前十名" in t:
            return False
        return True
    if "增持" in t:
        return True
    return False


def adx14(bs, i):
    if i < 30:
        return None
    plus_dm = minus_dm = tr_sum = 0.0
    for k in range(i - 14, i):
        h, l, pc = bs[k]["h"], bs[k]["l"], bs[k - 1]["c"]
        up = h - bs[k - 1]["h"]
        dn = bs[k - 1]["l"] - l
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
    return 100 * abs(pdi - mdi) / (pdi + mdi)


def stage_of(bs, i):
    if i < 91:
        return None
    w60 = bs[i - 60:i]
    ret60 = w60[-1]["c"] / w60[0]["c"] - 1
    v20 = sum(b["v"] for b in bs[i - 20:i]) / 20
    v60 = sum(b["v"] for b in bs[i - 60:i]) / 60
    vt = v20 / v60 if v60 else 1
    if ret60 < -0.15 and vt < 0.9:
        return "ACCUM"
    if ret60 > 0.30 and vt > 1.3:
        return "DISTRIB"
    if ret60 > 0.20 and vt > 1.1:
        return "MARKUP"
    return "UPTREND" if ret60 > 0 else "DOWNTREND"


# event leg with tiered exit
ev_tiered = []
seen = set()
cur.execute("SELECT date, stock_code, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
for date, code, title in cur.fetchall():
    if not is_strong(title):
        continue
    d = str(date)[:10].replace("-", "")
    if (code, d) in seen:
        continue
    seen.add((code, d))
    bs = bars_of(code)
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    if d not in dates:
        continue
    i = dates.index(d)
    st = stage_of(bs, i)
    if st not in ("ACCUM", "DOWNTREND"):
        continue
    adx = adx14(bs, i)
    if adx is None or adx < 20:
        continue
    entry_idx = i + 1
    if entry_idx + 16 >= len(bs):
        continue
    ep = bs[entry_idx]["o"]
    if ep <= 0:
        continue
    highs = []
    lows = []
    for j in range(i - 1, max(0, i - 60), -1):
        if j < 3 or j + 3 >= i:
            continue
        if len(highs) < 3 and bs[j]["h"] > max(bs[k]["h"] for k in range(j - 3, j)) and bs[j]["h"] >= max(bs[k]["h"] for k in range(j + 1, j + 4)):
            highs.append(bs[j]["h"])
        if len(lows) < 2 and bs[j]["l"] < min(bs[k]["l"] for k in range(j - 3, j)) and bs[j]["l"] <= min(bs[k]["l"] for k in range(j + 1, j + 4)):
            lows.append(bs[j]["l"])
        if len(highs) >= 3 and len(lows) >= 2:
            break
    if not highs or not lows:
        continue
    highs.sort()
    tp1, tp2, tp3 = highs[0], (highs[1] if len(highs) > 1 else highs[0] * 1.05), highs[-1]
    sl1 = lows[0] * 0.99
    # tiered exit
    remaining = 1.0
    pnl = 0.0
    be = False
    for k in range(entry_idx + 1, min(len(bs), entry_idx + 16)):
        bb = bs[k]
        stop = ep if be else sl1
        if bb["l"] <= stop:
            pnl += remaining * (stop / ep - 1) * 100
            remaining = 0
            break
        if not be and bb["h"] >= tp1:
            pnl += 0.3 * (tp1 / ep - 1) * 100  # TP1 close 30%
            remaining = 0.7
            be = True
        elif be and bb["h"] >= tp2:
            pnl += remaining * (tp2 / ep - 1) * 100
            remaining = 0
            break
        elif be and bb["h"] >= tp3:
            pnl += remaining * (tp3 / ep - 1) * 100
            remaining = 0
            break
    if remaining > 0:
        last = bs[min(len(bs), entry_idx + 15) - 1]["c"]
        pnl += remaining * (last / ep - 1) * 100
    ev_tiered.append({"symbol": code, "entry_date": bs[entry_idx]["t"], "src": "EVENT",
                      "net_pnl_pct": round(pnl - 0.20, 4)})
conn.close()
print("事件(分层):", len(ev_tiered))

# continuation from v20c (fixed 10-day)
cont = []
with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        if r.get("src") == "CONT":
            r["net_pnl_pct"] = float(r["net_pnl_pct"])
            cont.append(r)


def report(label, rs):
    if len(rs) < 300:
        print(f"{label}: n={len(rs)} (过小)")
        return
    for t in rs:
        t.setdefault("t1_violation", "False")
        t["t1_violation"] = str(t.get("t1_violation", "")).lower() in ("true", "1", "yes")
        t["year"] = str(t["entry_date"])[:4]
    gate = check_economic_gate(rs)
    o = gate["overall"]
    line = f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']}"
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if t["year"] == y]
        if ys:
            line += f" | {y}:{sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%"
    print(line)


# combo = event tiered + cont
combo_tiered = ev_tiered + cont
seen_c = set()
combo_dedup = []
for t in combo_tiered:
    k = (str(t.get("symbol", "")), str(t.get("entry_date", "")))
    if k in seen_c:
        continue
    seen_c.add(k)
    combo_dedup.append(t)

print("\n=== v20c 升级验证（事件分层 + 延续固定）===")
orig = []
with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        orig.append(r)
report("v20c（固定持有）", orig)
report("v20c升级（事件分层TP/SL）", combo_dedup)
