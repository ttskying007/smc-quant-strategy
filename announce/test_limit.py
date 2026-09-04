# -*- coding: utf-8 -*-
"""Test announcement API rate tolerance: burst of requests with varying delay."""
import io, json, sys, time, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://data.eastmoney.com/notices/"}


def get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except Exception as e:
        return None, str(e)[:80]


url = "https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size=10&page_index=1&ann_type=A&client_source=web&begin_time=2026-08-14&end_time=2026-08-14"
print("测试不同间隔:")
for delay, label in [(0.0, "无延迟"), (0.3, "0.3s"), (1.0, "1.0s"), (2.0, "2.0s")]:
    ok = 0
    for i in range(3):
        st, b = get(url)
        if st == 200:
            try:
                d = json.loads(b)
                if d.get("data") is not None:
                    ok += 1
            except Exception:
                pass
        time.sleep(delay)
    print(f"  {label}: {ok}/3 OK")
