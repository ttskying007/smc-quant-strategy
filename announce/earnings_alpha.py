# -*- coding: utf-8 -*-
"""Enhanced earnings-text extraction + event alpha test.
Pull more notice_content, improve regex, test direction event returns vs baseline."""
import io, json, os, re, sqlite3, sys, time, urllib.request
from collections import defaultdict, Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://data.eastmoney.com/notices/"}

code2file = {}
for f in os.listdir(KT):
    if f.endswith("_daily_800.json"):
        code2file[f.split("_")[0]] = os.path.join(KT, f)


def get_content(art):
    url = f"https://np-cnotice-stock.eastmoney.com/api/content/ann?art_code={art}&client_source=web&page_index=1"
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read())
        return str((d.get("data") or {}).get("notice_content") or "")
    except Exception:
        return ""


def parse_direction(text):
    t = re.sub(r"\s+", "", text or "")
    if "扭亏为盈" in t or "扭亏" in t:
        if "预计净利润" in t and re.search(r"为正值|盈利|增加", t):
            return "TURNAROUND"
        return "TURNAROUND"
    if "首亏" in t or "预亏" in t:
        return "LOSS"
    if "预减" in t or "续亏" in t:
        return "DECREASE"
    if "预增" in t or "续盈" in t:
        return "INCREASE"
    if "略增" in t:
        return "SLIGHT_INC"
    if "略减" in t:
        return "SLIGHT_DEC"
    return "UNKNOWN"


def forward_pnl(code, event_date, hold=10):
    p = code2file.get(code)
    if not p:
        return None
    raw = json.load(open(p, encoding="utf-8"))
    dates = [("".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]) for r in raw if r.get("t")]
    closes = [float(r["c"]) for r in raw if r.get("c")]
    opens = [float(r["o"]) for r in raw if r.get("o")]
    if event_date not in dates:
        prev = [d for d in dates if d < event_date]
        if not prev:
            return None
        i = dates.index(prev[-1])
    else:
        i = dates.index(event_date)
    if i + hold >= len(closes):
        return None
    ep = opens[i]
    if ep <= 0:
        return None
    return (closes[i + hold] / ep - 1) * 100 - 0.20


def main():
    conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
    cur = conn.cursor()
    cur.execute("SELECT date, stock_code, title, art_code FROM announce WHERE title LIKE '%业绩预告%' AND art_code IS NOT NULL LIMIT 400")
    rows = cur.fetchall()
    conn.close()
    print(f"announcements: {len(rows)}")

    events = []
    for date, code, title, art in rows:
        txt = get_content(art)
        direction = parse_direction(txt)
        d = str(date)[:10].replace("-", "")
        pnl = forward_pnl(code, d)
        if pnl is not None:
            events.append({"code": code, "date": d, "direction": direction, "pnl": pnl, "year": d[:4]})
        time.sleep(0.2)

    print("events with pnl:", len(events))
    print("direction 分布:", dict(Counter(e["direction"] for e in events)))

    print("\n=== 业绩预告方向 × 10日收益 ===")
    for dr in ("TURNAROUND", "INCREASE", "DECREASE", "LOSS", "UNKNOWN"):
        rs = [e for e in events if e["direction"] == dr]
        if len(rs) < 15:
            print(f"  {dr}: n={len(rs)} (过小)")
            continue
        avg = sum(e["pnl"] for e in rs) / len(rs)
        w = sum(1 for e in rs if e["pnl"] > 0)
        by_y = defaultdict(list)
        for e in rs:
            by_y[e["year"]].append(e["pnl"])
        ys = " ".join(f"{y}:{sum(v)/len(v):+.1f}" for y, v in sorted(by_y.items()) if len(v) >= 10)
        print(f"  {dr}: n={len(rs)} WR={100*w/len(rs):.0f}% avg={avg:+.2f}% | {ys}")

    # baseline: all events
    if events:
        avg = sum(e["pnl"] for e in events) / len(events)
        print(f"\n基线（全部业绩预告）: n={len(events)} avg={avg:+.2f}%")


if __name__ == "__main__":
    main()
