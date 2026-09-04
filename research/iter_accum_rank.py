# -*- coding: utf-8 -*-
"""ACCUM 优先排序验证：事件腿精选 Top50%（ACCUM 优先）vs 现排序
ACCUM 阶段事件 +10.17% >> DOWNTREND +5.67% → 测组合提升"""
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


def stage_and_info(bs, i):
    """Return (stage, deep, vol20) for ranking."""
    if i < 91:
        return None, False, 0
    w90 = bs[i - 90:i]
    w60 = bs[i - 60:i]
    w20 = bs[i - 20:i]
    ret90 = w90[-1]["c"] / w90[0]["c"] - 1
    ret60 = w60[-1]["c"] / w60[0]["c"] - 1
    v20 = sum(b["v"] for b in w20) / 20
    v60 = sum(b["v"] for b in w60) / 60
    v90 = sum(b["v"] for b in w90) / 90
    vt60 = v20 / v60 if v60 else 1
    vt90 = v20 / v90 if v90 else 1
    deep = ret90 < -0.20 and vt90 < 0.75
    vol20 = sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20
    if ret60 < -0.15 and vt60 < 0.9:
        return "ACCUM", deep, vol20
    if ret60 > 0.30 and vt60 > 1.3:
        return "DISTRIB", deep, vol20
    if ret60 > 0.20 and vt60 > 1.1:
        return "MARKUP", deep, vol20
    if ret60 > 0:
        return "UPTREND", deep, vol20
    return "DOWNTREND", deep, vol20


cands = []
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
    st, deep, vol20 = stage_and_info(bs, i)
    if st not in ("ACCUM", "DOWNTREND"):
        continue
    adx = adx14(bs, i)
    if adx is None or adx < 20:
        continue
    hold = 15
    if i + 1 + hold >= len(bs):
        continue
    ep = bs[i + 1]["o"]
    if ep <= 0:
        continue
    cands.append({"entry_date": bs[i + 1]["t"], "stage": st, "deep": deep, "vol20": vol20,
                  "net_pnl_pct": round((bs[i + 1 + hold]["c"] / ep - 1) * 100 - 0.20, 4)})
conn.close()
print("事件(ACCUM/DOWNTREND):", len(cands))


def report(label, rs):
    if len(rs) < 300:
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


# ranking: ACCUM-first (ACCUM > DOWNTREND), then DEEP, then high vol
ranked = sorted(cands, key=lambda t: (t["stage"] == "ACCUM", t["deep"], t["vol20"] > 0.041), reverse=True)
print("\n=== 事件腿排序对比 ===")
report("全量(ACCUM+DOWNTREND)", cands)
n = len(ranked)
report("Top50% ACCUM优先", [dict(t) for t in ranked[:n // 2]])
report("Top50% 现排序(DEEP+高波)", [dict(t) for t in sorted(cands, key=lambda t: (t["deep"], t["vol20"] > 0.041), reverse=True)[:n // 2]])
