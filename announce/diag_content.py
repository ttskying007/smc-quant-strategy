# -*- coding: utf-8 -*-
import io, json, sys, time, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://data.eastmoney.com/notices/"}

# test 3 known arts with delay
arts = ["AN202307131592249976", "AN202307131592248511", "AN202307131592246150"]
for art in arts:
    url = f"https://np-cnotice-stock.eastmoney.com/api/content/ann?art_code={art}&client_source=web&page_index=1"
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read())
        txt = str((d.get("data") or {}).get("notice_content") or "")
        print(art, "content len:", len(txt), "| has 扭亏:", "扭亏" in txt, "| sample:", txt[:50].replace(chr(10), " "))
    except Exception as e:
        print(art, "FAIL:", e)
    time.sleep(2)
