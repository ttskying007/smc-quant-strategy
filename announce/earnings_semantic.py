# -*- coding: utf-8 -*-
"""Earnings-preannouncement TEXT semantic extraction (per v628 history, now local).
Pull notice_content for 业绩预告 announcements, extract numeric signals:
  - direction: 预增/预减/扭亏/首亏/略增/略减/续盈/续亏
  - magnitude: 变动幅度% (e.g. 增长50%-70%), 预计净利润
Then test: does numeric-magnitude event alpha vary by direction/strength?"""
import io, json, os, re, sqlite3, sys, time, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://data.eastmoney.com/notices/"}


def get_content(art):
    url = f"https://np-cnotice-stock.eastmoney.com/api/content/ann?art_code={art}&client_source=web&page_index=1"
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read())
        data = d.get("data") or {}
        return str(data.get("notice_content") or "")
    except Exception:
        return ""


def parse_direction(text):
    """Extract direction + magnitude from earnings preannouncement text."""
    t = re.sub(r"\s+", "", text or "")
    mag = None
    # magnitude pattern: 增长50%-70% / 下降20%-30% / 增长50%以上
    m = re.search(r"(增长|上升|下降|减少|增加)(\d+(?:\.\d+)?)%[至到]?(\d+(?:\.\d+)?)?%?以上?", t)
    if m:
        verb = m.group(1)
        lo = float(m.group(2))
        hi = float(m.group(3)) if m.group(3) else lo
        mag = (lo + hi) / 2
        if verb in ("下降", "减少"):
            mag = -mag
    # direction by title words
    if "扭亏" in t:
        return "TURNAROUND", mag
    if "首亏" in t or "预亏" in t:
        return "LOSS", mag
    if "预减" in t or "续亏" in t:
        return "DECREASE", mag
    if "预增" in t or "续盈" in t:
        return "INCREASE", mag
    if "略增" in t:
        return "SLIGHT_INC", mag
    if "略减" in t:
        return "SLIGHT_DEC", mag
    return "UNKNOWN", mag


def main():
    conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
    cur = conn.cursor()
    cur.execute("SELECT date, stock_code, title, art_code FROM announce WHERE title LIKE '%业绩预告%' AND art_code IS NOT NULL LIMIT 100")
    rows = cur.fetchall()
    conn.close()
    print(f"sample announcements: {len(rows)}")

    out = []
    for date, code, title, art in rows:
        txt = get_content(art)
        direction, mag = parse_direction(txt)
        out.append({"date": date, "code": code, "title": str(title)[:40], "direction": direction, "mag": mag})
        time.sleep(0.3)

    from collections import Counter
    print("\ndirection 分布:", dict(Counter(x["direction"] for x in out)))
    mags = [x["mag"] for x in out if x["mag"] is not None]
    print(f"含变动幅度: {len(mags)}/{len(out)}, 样例: {mags[:10]}")

    with open(r"E:\test\smc_project\announce\earnings_semantic_sample.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print("sample saved")


if __name__ == "__main__":
    main()
