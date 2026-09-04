# -*- coding: utf-8 -*-
"""v18c: event-leg SMC exit tuned for 'slow-confirmation' alpha.
- SL = event-day low (wide invalidation: if price breaks below the event bar low,
  the insider signal is negated) * 0.99
- TP = pre-entry structural high pool (highest swing high in 60d lookback)
- max_hold 30 (time protection, not primary exit)
- No premature 1R/BE. SMC structural logic: event invalidated = exit."""
import glob, io, json, os, sqlite3, sys
from collections import defaultdict, Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
PIVOT = 3
MAX_HOLD = 30
FEE = 0.20

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
            if t and r.get("o") and r.get("h") and r.get("l") and r.get("c"):
                bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"]), "v": float(r.get("v") or 0)})
        bs.sort(key=lambda b: b["t"])
        bar_cache[code] = bs
    return bar_cache[code]


def is_swing_high(bs, j):
    if j < PIVOT or j + PIVOT >= len(bs):
        return False
    return bs[j]["h"] > max(bs[k]["h"] for k in range(j - PIVOT, j)) and bs[j]["h"] >= max(bs[k]["h"] for k in range(j + 1, j + PIVOT + 1))


def replay_invalidation(bs, i, ep):
    """SL = event-day low (signal invalidation), TP = 60d structural high pool."""
    # event-day low (entry bar low as invalidation)
    sl = bs[i]["l"] * 0.99
    if sl >= ep:
        return None
    highs = []
    for j in range(i - 1, max(0, i - 60), -1):
        if is_swing_high(bs, j):
            highs.append(bs[j]["h"])
        if len(highs) >= 3:
            break
    if not highs:
        return None
    tp = max(highs)
    if tp <= ep:
        return None
    exit_price, reason, hold = ep, "TIME_STOP", 0
    for k in range(i + 1, min(len(bs), i + MAX_HOLD + 1)):
        bb = bs[k]
        hold += 1
        hi, lo, cl = bb["h"], bb["l"], bb["c"]
        if lo <= sl:
            exit_price, reason = sl, "EVENT_INVALID"
            break
        if hi >= tp:
            exit_price, reason = tp, "TP_STRUCTURAL"
            break
        exit_price = cl
    if reason == "TIME_STOP":
        exit_price = bs[min(len(bs), i + MAX_HOLD) - 1]["c"]
    return round((exit_price / ep - 1) * 100 - FEE, 4), reason, hold


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


def stage_at(bs, i):
    if i < 61:
        return None
    w60 = bs[i - 60:i]
    w20 = bs[i - 20:i]
    ret = w60[-1]["c"] / w60[0]["c"] - 1
    v20 = sum(b["v"] for b in w20) / len(w20)
    v60 = sum(b["v"] for b in w60) / len(w60)
    vt = v20 / v60 if v60 else 1
    if ret < -0.15 and vt < 0.9:
        return "ACCUM"
    if ret > 0.30 and vt > 1.3:
        return "DISTRIB"
    if ret > 0.20 and vt > 1.1:
        return "MARKUP"
    if ret > 0:
        return "UPTREND"
    return "DOWNTREND"


trades = []
fixed_trades = []
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
    nxt = [x for x in dates if x > d]
    if not nxt:
        continue
    i = dates.index(nxt[0])
    st = stage_at(bs, i)
    if st not in ("ACCUM", "DOWNTREND"):
        continue
    adx = adx14(bs, i)
    if adx is None or adx < 20:
        continue
    ep = bs[i]["o"]
    if ep <= 0 or i + 15 >= len(bs):
        continue
    fixed_trades.append({"entry_date": bs[i]["t"],
                         "net_pnl_pct": round((bs[i + 15]["c"] / ep - 1) * 100 - 0.20, 4), "t1_violation": "False"})
    r = replay_invalidation(bs, i, ep)
    if r:
        pnl, reason, hold = r
        trades.append({"entry_date": bs[i]["t"], "net_pnl_pct": pnl, "reason": reason,
                       "hold": hold, "t1_violation": "False"})
conn.close()
print(f"fixed: {len(fixed_trades)}, invalidation-structure: {len(trades)}")
print("exit dist:", dict(Counter(t["reason"] for t in trades)))


def report(label, rs):
    if len(rs) < 300:
        print(f"{label}: n={len(rs)} (过小)"); return
    for t in rs:
        t["year"] = str(t["entry_date"])[:4]
    gate = check_economic_gate(rs)
    o = gate["overall"]
    print(f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']}")
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if t["year"] == y]
        if ys:
            w = sum(1 for t in ys if t["net_pnl_pct"] > 0)
            print(f"    {y}: n={len(ys)} WR={100*w/len(ys):.0f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%")


print("\n=== v18c：事件失效SL + 结构TP + 持有上限30 ===")
report("固定15日（v17）", fixed_trades)
report("SMC事件失效执行", trades)
