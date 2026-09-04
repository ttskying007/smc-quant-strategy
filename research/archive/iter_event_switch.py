# -*- coding: utf-8 -*-
"""Event x behavior-switch: insider events at stage transitions (e.g. ACCUM->UPTREND
= major switching to markup) vs steady-state events.
Tests if events at transition points carry more information (sequence timing)."""
import glob, io, json, os, sqlite3, sys
from collections import defaultdict, Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()

code2file = {}
for f in os.listdir(KT):
    if f.endswith("_daily_800.json"):
        code2file[f.split("_")[0]] = os.path.join(KT, f)

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


def stage_at(bs, i, win=60):
    if i < win + 1:
        return None
    w60 = bs[i - win:i]
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


def switch_type(bs, i, lookback=10):
    """Stage at entry vs stage lookback bars ago. Return (type) or None."""
    if i < 71:
        return None
    cur = stage_at(bs, i)
    prev = stage_at(bs, i - lookback)
    if cur is None or prev is None:
        return None
    if cur == prev:
        return "STEADY"
    return f"{prev}->{cur}"


def is_strong(title):
    t = str(title or "")
    if "回购" in t:
        if "完成" in t or "进度" in t or "进展" in t or "结果" in t or "前十名" in t:
            return False
        return True
    if "增持" in t:
        return True
    return False


# events with switch type + stage (ACCUM/DOWNTREND events only, keep v8 event filter)
cur.execute("SELECT date, stock_code, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
trades = []
seen = set()
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
    if i + 10 >= len(bs):
        continue
    st = stage_at(bs, i)
    if st not in ("ACCUM", "DOWNTREND"):
        continue
    sw = switch_type(bs, i)
    if sw is None:
        continue
    ep = bs[i]["o"]
    if ep <= 0:
        continue
    trades.append({"symbol": code, "entry_date": bs[i]["t"], "sw": sw,
                   "net_pnl_pct": round((bs[i + 10]["c"] / ep - 1) * 100 - 0.20, 4),
                   "t1_violation": "False"})
print("event trades:", len(trades))
print("switch 分布:", dict(Counter(t["sw"] for t in trades)))


def report(label, rs):
    if len(rs) < 100:
        print(f"{label}: n={len(rs)} (过小)"); return
    for t in rs:
        t["t1_violation"] = str(t.get("t1_violation", "")).lower() in ("true", "1", "yes")
    gate = check_economic_gate(rs)
    o = gate["overall"]
    print(f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']}")
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if str(t["entry_date"]).startswith(y)]
        if ys:
            wy = sum(1 for t in ys if t["net_pnl_pct"] > 0)
            print(f"    {y}: n={len(ys)} WR={100*wy/len(ys):.0f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%")


print("\n=== 事件 × 行为切换 ===")
report("基线（ACCUM/DOWNTREND 事件）", trades)
report("稳态（无切换）", [t for t in trades if t["sw"] == "STEADY"])
# bullish transitions into accumulation/downtrend from worse
bull_sw = [t for t in trades if t["sw"].startswith("UPTREND") or t["sw"].startswith("MARKUP")]
report("从拉升切出（UPTREND/MARKUP->）", bull_sw)
acc_in = [t for t in trades if "->ACCUM" in t["sw"] or "->DOWNTREND" in t["sw"]]
report("切入吸筹/下跌（->ACCUM/DOWNTREND）", acc_in)
conn.close()
