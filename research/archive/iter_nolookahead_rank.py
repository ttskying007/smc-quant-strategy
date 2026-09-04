# -*- coding: utf-8 -*-
"""无泄漏皇冠验证：v_ratio 用 T 日量、v2_ratio 用 T-1 量（决策时点可得）
重算 rank_score 单调性 + 皇冠（rank≥6）绩效 + 年度拆分 + Bootstrap"""
import io, json, os, random, sqlite3, sys
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


def weekly_trend_of(bs, i):
    closes = []
    j = i
    while j >= 0 and len(closes) < 20:
        closes.append(bs[j]["c"])
        j -= 5
    closes.reverse()
    if len(closes) < 12:
        return None
    ma10 = sum(closes[-10:]) / 10
    ma_prev = sum(closes[-12:-2]) / 10
    return "up" if ma10 > ma_prev else "down"


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
    entry_idx = i + 1
    if entry_idx + 17 >= len(bs) or entry_idx < 130:
        continue
    if bs[entry_idx]["t"] < "20230901":
        continue
    ep = bs[entry_idx]["o"]
    if ep <= 0:
        continue
    avg_v = sum(bs[k]["v"] for k in range(i - 19, i + 1)) / 20 if i >= 19 else 0
    # 无泄漏：T 日量 / T-1 量（决策时点可得）
    v_ratio = bs[i]["v"] / avg_v if avg_v > 0 else 1.0
    v2_ratio = bs[i - 1]["v"] / avg_v if (avg_v > 0 and i >= 1) else 0
    stage_span = 0
    for j in range(i, max(0, i - 60), -1):
        if stage_of(bs, j) == st:
            stage_span += 1
        else:
            break
    adx_span = 0
    for j in range(i, max(0, i - 40), -1):
        if (adx14(bs, j) or 0) >= 20:
            adx_span += 1
        else:
            break
    wt = weekly_trend_of(bs, i)
    etype = 1 if ("方案" in str(title) or "首次" in str(title) or "计划" in str(title)) else 0
    rs = (2 if st == "ACCUM" else 1)
    rs += (1 if v_ratio > 1.2 else 0) + (1 if v_ratio >= 2.0 else 0)
    rs += (1 if 6 <= stage_span <= 15 else 0) + (1 if adx_span > 15 else 0)
    rs += 1 if wt == "down" else 0
    rs += 1 if (v_ratio >= 1.5 and v2_ratio >= 1.5) else 0
    rs += etype
    events.append({"entry_date": bs[entry_idx]["t"],
                   "net_pnl_pct": round((bs[entry_idx + 15]["c"] / ep - 1) * 100 - 0.20, 4),
                   "rank": rs})
conn.close()
print("事件:", len(events))


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
            line += f" | {y}:{sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%({len(ys)})"
    print(line)


print("\n=== 无泄漏 rank_score 单调性 ===")
for rk in range(2, 9):
    rs = [t for t in events if t["rank"] == rk]
    if len(rs) >= 100:
        report(f"rank={rk}", rs)
    else:
        print(f"rank={rk}: n={len(rs)} (过小)")
report("rank≥6（皇冠）", [t for t in events if t["rank"] >= 6])
report("rank≥5", [t for t in events if t["rank"] >= 5])

# Bootstrap 皇冠
crown = [t for t in events if t["rank"] >= 6]
if len(crown) >= 100:
    pnls = [t["net_pnl_pct"] for t in crown]
    random.seed(42)
    avgs = []
    for _ in range(1000):
        sub = random.sample(pnls, int(len(pnls) * 0.6))
        avgs.append(sum(sub) / len(sub))
    avgs.sort()
    print(f"\n皇冠 Bootstrap 1000 次: 中位 {avgs[500]:+.2f}% | P5 {avgs[50]:+.2f}% | P95 {avgs[950]:+.2f}%")
    print(f"  全部为正: {sum(1 for a in avgs if a > 0)}/1000")
