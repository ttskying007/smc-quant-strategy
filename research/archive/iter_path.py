# -*- coding: utf-8 -*-
"""入场后价格路径：事件腿入场（T+1）后 3 日内路径分布
先跌后涨（回踩机会）vs 直接涨（无回踩）→ 验证回踩买点时机"""
import io, json, os, sqlite3, sys
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


cur.execute("SELECT date, stock_code, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
paths = {"直接涨": 0, "先跌后涨(回踩)": 0, "先涨后跌": 0, "持续跌": 0, "横盘": 0}
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
    entry_idx = i + 1
    if entry_idx + 4 >= len(bs):
        continue
    ep = bs[entry_idx]["o"]
    if ep <= 0:
        continue
    c1 = bs[entry_idx + 1]["c"]
    c3 = bs[entry_idx + 3]["c"]
    low3 = min(bs[entry_idx + 1]["l"], bs[entry_idx + 2]["l"], bs[entry_idx + 3]["l"])
    # classify path
    if c3 > ep and low3 >= ep * 0.995:
        paths["直接涨"] += 1
    elif c3 > ep and low3 < ep * 0.995:
        paths["先跌后涨(回踩)"] += 1
    elif c1 > ep and c3 < ep:
        paths["先涨后跌"] += 1
    elif c3 < ep * 0.995 and c1 < ep:
        paths["持续跌"] += 1
    else:
        paths["横盘"] += 1
conn.close()

total = sum(paths.values())
print(f"样本: {total}\n")
print("=== 入场后 3 日价格路径分布 ===")
for k, v in sorted(paths.items(), key=lambda kv: -kv[1]):
    print(f"  {k}: {v} ({100*v/total:.0f}%)")
