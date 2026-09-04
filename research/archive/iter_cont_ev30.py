# -*- coding: utf-8 -*-
"""事件后30天内延续信号：MARKUP 延续 + 前30日事件 → 是否更强（vs 无事件延续）"""
import csv, io, json, os, sqlite3, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
# event map
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
cur.execute("SELECT stock_code, date FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
ev_map = defaultdict(set)
for code, d in cur.fetchall():
    ev_map[code].add(str(d)[:10].replace("-", ""))
conn.close()

# v20c trades with features: CONT trades + their vol20 (recompute) + event-within-30d
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

cont_rows = []
for t in trades:
    if t.get("src") != "CONT":
        continue
    code = str(t.get("symbol", "")).split(".")[0]
    ed = str(t.get("entry_date", ""))
    bs = bars_of(code)
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    if ed not in dates:
        continue
    i = dates.index(ed)
    if i < 20:
        continue
    w20 = bs[i - 20:i]
    vol20 = sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20 if len(w20) == 20 else 0
    # event within 30 days before entry
    has_ev = any(0 <= int(ed) - int(e) <= 30 for e in ev_map.get(code, set()))
    cont_rows.append({"entry_date": ed, "vol20": vol20, "has_ev": has_ev, "net_pnl_pct": t["net_pnl_pct"]})
print("延续信号:", len(cont_rows))
vols = sorted(r["vol20"] for r in cont_rows)
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


print("\n=== 延续腿 + 事件后30天 ===")
report("延续低波动（基线）", [r for r in cont_rows if r["vol20"] < vmed])
report("+前30日事件", [r for r in cont_rows if r["vol20"] < vmed and r["has_ev"]])
report("无事件", [r for r in cont_rows if r["vol20"] < vmed and not r["has_ev"]])
