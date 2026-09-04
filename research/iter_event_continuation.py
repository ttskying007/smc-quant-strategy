# -*- coding: utf-8 -*-
"""事件延续腿深化：UPTREND/MARKUP 事件（内部人在趋势中确认）
之前 TP2 测试 +0.41% 弱 → 固定持有（时间确认型）可能提升"""
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


def stage_and_vwap(bs, i):
    if i < 61:
        return None, None
    w60 = bs[i - 60:i]
    w20 = bs[i - 20:i]
    ret60 = w60[-1]["c"] / w60[0]["c"] - 1
    v20 = sum(b["v"] for b in w20) / len(w20)
    v60 = sum(b["v"] for b in w60) / len(w60)
    vt = v20 / v60 if v60 else 1
    if ret60 < -0.15 and vt < 0.9:
        st = "ACCUM"
    elif ret60 > 0.30 and vt > 1.3:
        st = "DISTRIB"
    elif ret60 > 0.20 and vt > 1.1:
        st = "MARKUP"
    elif ret60 > 0:
        st = "UPTREND"
    else:
        st = "DOWNTREND"
    pv = sum(b["c"] * b["v"] for b in w20)
    vol = sum(b["v"] for b in w20)
    vw = pv / vol if vol else 0
    dev = (bs[i]["c"] - vw) / vw if vw else 0
    return st, dev


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
    d8 = d.replace("-", "")
    if d8 not in dates:
        continue
    i = dates.index(d8)
    st, dev = stage_and_vwap(bs, i)
    if st is None:
        continue
    adx = adx14(bs, i)
    if adx is None or i + 21 >= len(bs):
        continue
    ep = bs[i + 1]["o"]
    if ep <= 0:
        continue
    cands.append({"entry_date": bs[i + 1]["t"], "stage": st, "adx": adx, "dev": dev, "i": i + 1, "bs": bs, "ep": ep})
conn.close()
print("events:", len(cands))


def report(label, rs):
    if len(rs) < 100:
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


print("\n=== 事件延续腿（UPTREND/MARKUP 事件）固定持有 ===")
cont_ev = [c for c in cands if c["stage"] in ("UPTREND", "MARKUP")]
print(f"事件延续候选: {len(cont_ev)}")
for h in (10, 15):
    rs = [{"entry_date": c["entry_date"],
           "net_pnl_pct": round((c["bs"][c["i"] + h - 1]["c"] / c["ep"] - 1) * 100 - 0.20, 4)}
          for c in cont_ev if c["i"] + h - 1 < len(c["bs"])]
    report(f"事件延续 固定{h}日", rs)
rs_vwap = [{"entry_date": c["entry_date"],
            "net_pnl_pct": round((c["bs"][c["i"] + 9]["c"] / c["ep"] - 1) * 100 - 0.20, 4)}
           for c in cont_ev if c["dev"] is not None and c["dev"] >= 0.03 and c["i"] + 9 < len(c["bs"])]
report("事件延续 固定10日+VWAP3%", rs_vwap)
rs_adx = [{"entry_date": c["entry_date"],
           "net_pnl_pct": round((c["bs"][c["i"] + 9]["c"] / c["ep"] - 1) * 100 - 0.20, 4)}
          for c in cont_ev if c["adx"] >= 25 and c["i"] + 9 < len(c["bs"])]
report("事件延续 固定10日+ADX25", rs_adx)
