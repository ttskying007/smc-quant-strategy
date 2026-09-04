# -*- coding: utf-8 -*-
"""买点执行优化：回踩挂单（T+1 回落至披露日收盘才成交，否则开盘买）
近似 T+1 最低价（+9.10%）的可执行方案 vs 纯开盘（+6.52%）"""
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


events = []
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
    if i + 17 >= len(bs):
        continue
    disc_close = bs[i]["c"]
    events.append({"bs": bs, "i": i, "disc_close": disc_close, "entry_date": bs[i + 1]["t"]})
conn.close()
print("事件:", len(events))


def open_entry():
    rs = []
    for e in events:
        k = e["i"] + 1
        if k + 15 >= len(e["bs"]):
            continue
        ep = e["bs"][k]["o"]
        rs.append({"entry_date": e["entry_date"], "net_pnl_pct": round((e["bs"][k + 15]["c"] / ep - 1) * 100 - 0.20, 4)})
    return rs


def retrace_entry(discount=1.0):
    """限价单：挂披露日收盘价（×discount），T+1 最低<=挂单价则成交（挂单价），否则开盘买"""
    rs = []
    for e in events:
        k = e["i"] + 1
        if k + 15 >= len(e["bs"]):
            continue
        limit = e["disc_close"] * discount
        low = e["bs"][k]["l"]
        if low <= limit:
            ep = limit  # filled at limit (retraced)
        else:
            ep = e["bs"][k]["o"]  # no retrace → buy at open
        rs.append({"entry_date": e["entry_date"], "net_pnl_pct": round((e["bs"][k + 15]["c"] / ep - 1) * 100 - 0.20, 4)})
    return rs


def low_entry():
    rs = []
    for e in events:
        k = e["i"] + 1
        if k + 15 >= len(e["bs"]):
            continue
        ep = e["bs"][k]["l"]
        rs.append({"entry_date": e["entry_date"], "net_pnl_pct": round((e["bs"][k + 15]["c"] / ep - 1) * 100 - 0.20, 4)})
    return rs


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


print("\n=== 买点执行优化（回踩挂单 vs 开盘）===")
report("T+1开盘（当前）", open_entry())
report("回踩挂单(披露日收盘)", retrace_entry(1.0))
report("回踩挂单(收盘×0.99)", retrace_entry(0.99))
report("T+1最低（理论上限）", low_entry())
