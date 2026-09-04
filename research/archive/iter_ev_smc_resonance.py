# -*- coding: utf-8 -*-
"""事件 + SMC 反转共振：事件披露后 20 日内出现 SSL sweep 信号（内部人+结构双确认）"""
import io, json, os, sqlite3, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\wdh")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
import wdh_engine as we
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
cur.execute("SELECT stock_code, date FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
ev_map = defaultdict(list)
for code, d in cur.fetchall():
    ev_map[code].append(str(d)[:10].replace("-", ""))
conn.close()


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
n = 0
for p in sorted(os.listdir(KT)):
    if not p.endswith("_daily_800.json"):
        continue
    n += 1
    daily = bars(os.path.join(KT, p))
    if len(daily) < 400:
        continue
    sym = p.replace("_daily_800.json", "").replace("_", ".", 1)
    code = sym.split(".")[0]
    evs = sorted(ev_map.get(code, []))
    if not evs:
        continue
    dates = [b["t"] for b in daily]
    for sd in we.build_seeds(sym, daily):
        r20 = sd.get("r20")
        if r20 == "" or r20 is None or not (0 <= float(r20) < 0.15):
            continue
        entry_idx = int(sd["entry_idx"])
        if entry_idx < 61:
            continue
        st = stage_detailed(daily, entry_idx)
        if st not in ("UPTREND", "MARKUP"):
            continue
        # event within 20 days before entry
        entry_d = daily[entry_idx]["t"]
        has_ev = any(0 <= int(entry_d) - int(e) <= 20 for e in evs)
        tr = we.replay_tp2(sd, daily)
        if not tr:
            continue
        all_rows.append({"entry_date": tr["entry_date"], "has_ev": has_ev,
                         "net_pnl_pct": tr["net_pnl_pct"], "t1_violation": "False"})
    if n % 1500 == 0:
        print(f"  {n} files, rows {len(all_rows)}", flush=True)
print("SMC 反转信号（事件股内）:", len(all_rows))


def report(label, rs):
    if len(rs) < 50:
        print(f"{label}: n={len(rs)} (过小)")
        return
    for t in rs:
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


print("\n=== 事件 + SMC 反转共振 ===")
report("SMC 反转基线（事件股内全部）", all_rows)
report("+事件后20日（共振）", [r for r in all_rows if r["has_ev"]])
report("无事件共振", [r for r in all_rows if not r["has_ev"]])
