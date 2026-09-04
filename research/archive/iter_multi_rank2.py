# -*- coding: utf-8 -*-
"""多维排序 v2：事件（周一+业绩双确认+DEEP）均衡特征 vs 简单排序
之前加放量导致 2024 集中；周一/业绩双确认是每年均衡 → 重新测"""
import csv, io, json, os, sqlite3, sys
from collections import defaultdict
import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
# perf map
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
perf_map = defaultdict(list)
cur.execute("SELECT stock_code, date, title FROM announce WHERE title LIKE '%业绩%'")
for code, d, title in cur.fetchall():
    t = str(title)
    if ("业绩预告" in t or "业绩预增" in t or "业绩预盈" in t or "业绩快报" in t):
        perf_map[code].append(str(d)[:10].replace("-", ""))
conn.close()

trades = []
with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

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


def score_v2(t):
    """V2 score: EVENT monday+perf+deep / CONT lowvol+monday / SMC fvg."""
    code = str(t.get("symbol", "")).split(".")[0]
    ed = str(t.get("entry_date", ""))
    bs = bars_of(code)
    if not bs:
        return 0.0
    dates = [b["t"] for b in bs]
    if ed not in dates:
        prev = [d for d in dates if d < ed]
        if not prev:
            return 0.0
        i = dates.index(prev[-1])
    else:
        i = dates.index(ed)
    if i < 91:
        return 0.0
    src = t.get("src", "")
    s = 0.0
    if src == "EVENT":
        # disclosure date = prev bar (event day before entry)
        disc = dates[i - 1] if i >= 1 else ed
        w90 = bs[i - 90:i]
        w20 = bs[i - 20:i]
        ret90 = w90[-1]["c"] / w90[0]["c"] - 1
        v20 = sum(b["v"] for b in w20) / 20
        v90 = sum(b["v"] for b in w90) / 90
        deep = ret90 < -0.20 and (v20 / v90 if v90 else 1) < 0.75
        vol20 = sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20
        # monday disclosure
        try:
            wd = datetime.date(int(disc[:4]), int(disc[4:6]), int(disc[6:8])).weekday()
            mon = 1 if wd == 0 else 0
        except Exception:
            mon = 0
        # perf within 30d of disclosure
        perfs = perf_map.get(code, [])
        perf = 1 if any(abs(int(disc) - int(p)) <= 30 for p in perfs) else 0
        s = (2 if deep else 0) + (1 if vol20 > 0.041 else 0) + (1 if mon else 0) + (1 if perf else 0)
    elif src == "CONT":
        w20 = bs[i - 20:i]
        vol20 = sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20
        try:
            wd = datetime.date(int(ed[:4]), int(ed[4:6]), int(ed[6:8])).weekday()
            mon = 1 if wd == 0 else 0
        except Exception:
            mon = 0
        s = (2 if vol20 < 0.041 else 0) + (1 if mon else 0)
    else:
        fvg_cnt = sum(1 for k in range(max(3, i - 12), i) if bs[k]["h"] < bs[k - 2]["l"])
        s = fvg_cnt
    return s


scored = sorted([(t, score_v2(t)) for t in trades], key=lambda x: x[1], reverse=True)
print("V2 评分完成:", len(scored))


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


print("\n=== 多维排序 v2（均衡特征）===")
report("全量", [t for t, s in scored])
n = len(scored)
report("Top50% v2", [dict(t) for t, s in scored[:n // 2]])
report("Top40% v2", [dict(t) for t, s in scored[:int(n * 0.4)]])
