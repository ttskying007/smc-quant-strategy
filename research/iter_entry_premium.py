# -*- coding: utf-8 -*-
"""入场价格合理性：T+1 开盘 vs 披露日收盘的溢价/折价分布
验证买入价格是否合理（高开程度 + 回踩空间）"""
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
premiums = []
for date, code, title in cur.fetchall():
    if not is_strong(title):
        continue
    d = str(date)[:10].replace("-", "")
    bs = bars_of(code)
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    if d not in dates:
        continue
    i = dates.index(d)
    if i + 2 >= len(bs):
        continue
    disc_close = bs[i]["c"]
    t1_open = bs[i + 1]["o"]
    t1_low = bs[i + 1]["l"]
    if disc_close <= 0 or t1_open <= 0:
        continue
    premiums.append((t1_open / disc_close - 1) * 100)  # open premium vs close
conn.close()

premiums_s = sorted(premiums)
n = len(premiums_s)
print(f"事件样本: {n} 笔\n")
print("=== T+1 开盘 vs 披露日收盘 溢价分布 ===")
print(f"  P5: {premiums_s[int(n*0.05)]:+.2f}%")
print(f"  P25: {premiums_s[n//4]:+.2f}%")
print(f"  P50: {premiums_s[n//2]:+.2f}%")
print(f"  P75: {premiums_s[3*n//4]:+.2f}%")
print(f"  P95: {premiums_s[int(n*0.95)]:+.2f}%")
print(f"  平均: {sum(premiums_s)/n:+.2f}%")
# low vs close (回踩空间)
print(f"\n  高开(>0%): {sum(1 for x in premiums_s if x>0)/n:.0%} | 低开(<0%): {sum(1 for x in premiums_s if x<0)/n:.0%}")
