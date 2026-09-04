# -*- coding: utf-8 -*-
"""事件腿优化：只保留"首次/方案/计划"（新信息）→ v18+延续组合测试
发现：进展/完成旧信息弱（+2.4%）vs 首次/方案强（+9.64%）"""
import io, json, os, sqlite3, sys
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


def is_new_info(title):
    """首次/方案/计划（新信息）—— 排除进展/完成/进度/前十名"""
    t = str(title or "")
    if "进展" in t or "完成" in t or "进度" in t or "前十名" in t or "结果" in t:
        return False
    return ("回购" in t or "增持" in t)


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


def stage_and_deep(bs, i):
    if i < 91:
        return None, False
    w90 = bs[i - 90:i]
    w60 = bs[i - 60:i]
    w20 = bs[i - 20:i]
    ret90 = w90[-1]["c"] / w90[0]["c"] - 1
    ret60 = w60[-1]["c"] / w60[0]["c"] - 1
    v20 = sum(b["v"] for b in w20) / len(w20)
    v60 = sum(b["v"] for b in w60) / len(w60)
    v90 = sum(b["v"] for b in w90) / len(w90)
    vt60 = v20 / v60 if v60 else 1
    vt90 = v20 / v90 if v90 else 1
    deep = ret90 < -0.20 and vt90 < 0.75
    if ret60 < -0.15 and vt60 < 0.9:
        return "ACCUM", deep
    if ret60 > 0.30 and vt60 > 1.3:
        return "DISTRIB", deep
    if ret60 > 0.20 and vt60 > 1.1:
        return "MARKUP", deep
    if ret60 > 0:
        return "UPTREND", deep
    return "DOWNTREND", deep


def event_leg(mode):
    """mode: 'full' (含进展) or 'new' (只首次/方案)"""
    ev = []
    seen = set()
    cur.execute("SELECT date, stock_code, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
    for date, code, title in cur.fetchall():
        if mode == "new" and not is_new_info(title):
            continue
        if mode == "full" and not (str(title).find("回购") >= 0 or str(title).find("增持") >= 0):
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
        st, deep = stage_and_deep(bs, i)
        if st not in ("ACCUM", "DOWNTREND"):
            continue
        adx = adx14(bs, i)
        if adx is None or adx < 20:
            continue
        hold = 20 if deep else 15
        if i + 1 + hold >= len(bs):
            continue
        ep = bs[i + 1]["o"]
        if ep <= 0:
            continue
        ev.append({"entry_date": bs[i + 1]["t"], "src": "EVENT",
                   "net_pnl_pct": round((bs[i + 1 + hold]["c"] / ep - 1) * 100 - 0.20, 4)})
    return ev


# continuation leg (MARKUP struct + vwap5 + low-vol, fixed 10d) - reuse from v20c trades
cont = []
with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", encoding="utf-8-sig") as fh:
    import csv
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


print("\n=== 事件腿优化（排除进展/完成旧信息）===")
ev_full = event_leg("full")
ev_new = event_leg("new")
print(f"事件全量: {len(ev_full)} | 事件新信息: {len(ev_new)}")

seen_full = set()
c_full = []
for t in cont + ev_full:
    k = (str(t.get("symbol", "")), str(t.get("entry_date", "")))
    if k in seen_full:
        continue
    seen_full.add(k)
    c_full.append(t)

seen_new = set()
c_new = []
for t in cont + ev_new:
    k = (str(t.get("symbol", "")), str(t.get("entry_date", "")))
    if k in seen_new:
        continue
    seen_new.add(k)
    c_new.append(t)

report("v20c（事件全量+延续）", c_full)
report("优化（事件新信息+延续）", c_new)
conn.close()
