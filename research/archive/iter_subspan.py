# -*- coding: utf-8 -*-
"""子信号时间跨度研究：事件信号组合（披露日→阶段确认→ADX确认→入场）的间隔分布
验证信号组合的时间结构（各子信号间隔多久，周期跨度是否合理）"""
import io, json, os, sqlite3, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

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


# collect sub-signal timing
spans = []
cur.execute("SELECT date, stock_code, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
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
    if d not in dates:
        continue
    i = dates.index(d)
    st = stage_of(bs, i)
    if st not in ("ACCUM", "DOWNTREND"):
        continue
    adx = adx14(bs, i)
    if adx is None or adx < 20:
        continue
    # stage confirmed from bar: find when stage condition was met (within 60 bars)
    # ADX confirmed: find when ADX first >= 20 (within 30 bars before signal)
    stage_start = i
    for j in range(i, max(0, i - 60), -1):
        s2 = stage_of(bs, j)
        if s2 == st:
            stage_start = j
        else:
            break
    adx_start = i
    for j in range(i, max(0, i - 30), -1):
        if (adx14(bs, j) or 0) >= 20:
            adx_start = j
        else:
            break
    entry_idx = i + 1
    if entry_idx >= len(bs):
        continue
    spans.append({
        "stage_span": i - stage_start,      # 阶段已持续天数
        "adx_span": i - adx_start,           # ADX≥20 持续天数
        "entry_gap": 1,                      # 披露→入场 = 1 交易日（T+1）
        "stage": st,
    })
conn.close()

print(f"样本: {len(spans)}\n")
print("=== 子信号时间跨度 ===")
for key, label in (("stage_span", "阶段确认跨度（披露前已处于该阶段天数）"), ("adx_span", "ADX≥20 持续天数")):
    vals = sorted(s["stage_span"] if key == "stage_span" else s["adx_span"] for s in spans)
    n = len(vals)
    print(f"\n{label}:")
    print(f"  P25: {vals[n//4]} | P50: {vals[n//2]} | P75: {vals[3*n//4]} | 平均: {sum(vals)/n:.1f}")
    print(f"  0-5天: {sum(1 for x in vals if x<=5)/n:.0%} | 6-20天: {sum(1 for x in vals if 6<=x<=20)/n:.0%} | >20天: {sum(1 for x in vals if x>20)/n:.0%}")
