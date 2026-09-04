# -*- coding: utf-8 -*-
"""自适应策略研究：不同年份（2024反弹/2025弱市/2026震荡）的最优参数差异
判断是否需要按时期自适应匹配（阶段窗口/持有期/放量阈值）"""
import io, json, os, sqlite3, sys
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


def stage_at(bs, i, win):
    if i < win + 20:
        return None
    w = bs[i - win:i]
    ret = w[-1]["c"] / w[0]["c"] - 1
    v20 = sum(b["v"] for b in bs[i - 20:i]) / 20
    vw = sum(b["v"] for b in bs[i - win:i]) / win
    vt = v20 / vw if vw else 1
    if ret < -0.15 and vt < 0.9:
        return "ACCUM"
    if ret > 0.30 and vt > 1.3:
        return "DISTRIB"
    if ret > 0.20 and vt > 1.1:
        return "MARKUP"
    return "UPTREND" if ret > 0 else "DOWNTREND"


# 收集事件（含不同窗口的阶段 + 各持有期收益 + 放量）
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
    adx = adx14(bs, i)
    if adx is None or adx < 20:
        continue
    entry_idx = i + 1
    if entry_idx + 20 >= len(bs) or entry_idx < 130:
        continue
    if bs[entry_idx]["t"] < "20230901":
        continue
    ep = bs[entry_idx]["o"]
    if ep <= 0:
        continue
    avg_v = sum(bs[k]["v"] for k in range(i - 19, i + 1)) / 20 if i >= 19 else 0
    v_ratio = bs[i]["v"] / avg_v if avg_v > 0 else 1.0
    st60 = stage_at(bs, i, 60)
    if st60 not in ("ACCUM", "DOWNTREND"):
        continue
    # 各持有期收益
    holds = {}
    for h in (5, 10, 15, 20):
        if entry_idx + h < len(bs):
            holds[h] = (bs[entry_idx + h]["c"] / ep - 1) * 100 - 0.20
    events.append({"year": bs[entry_idx]["t"][:4], "entry_date": bs[entry_idx]["t"],
                   "holds": holds, "v_ratio": v_ratio})
conn.close()
print(f"事件: {len(events)}\n")

# 分年：最优持有期 + 放量特征
print("=== 分年最优参数（自适应判断）===")
for y in ("2024", "2025", "2026"):
    ys = [e for e in events if e["year"] == y]
    if len(ys) < 50:
        continue
    # 持有期收益
    print(f"\n{y}: n={len(ys)}")
    for h in (5, 10, 15, 20):
        hs = [e["holds"].get(h) for e in ys if h in e["holds"]]
        if len(hs) >= 30:
            avg = sum(hs) / len(hs)
            print(f"  持有{h}日: {avg:+.2f}% (n={len(hs)})")
    # 放量分组
    for thr in (1.2, 1.5, 2.0):
        vs = [e["holds"].get(15) for e in ys if e["v_ratio"] >= thr and 15 in e["holds"]]
        if len(vs) >= 20:
            print(f"  放量≥{thr}x 15日: {sum(vs)/len(vs):+.2f}% (n={len(vs)})")
