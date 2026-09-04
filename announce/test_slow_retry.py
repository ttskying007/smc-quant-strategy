# -*- coding: utf-8 -*-
"""Test: can Eastmoney announcement API be backfilled with very long delays?"""
import io, json, sys, time, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://data.eastmoney.com/notices/", "Accept": "application/json, text/plain, */*", "Accept-Language": "zh-CN,zh;q=0.9"}


def get(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except Exception as e:
        return None, str(e)[:100]


# the exact days that failed before, with long cooldown between
for day in ("2025-05-06", "2026-04-07", "2026-05-06"):
    url = (f"https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size=10&page_index=1"
           f"&ann_type=A&client_source=web&begin_time={day}&end_time={day}")
    ok = False
    for attempt in range(4):
        st, b = get(url)
        if st == 200:
            try:
                d = json.loads(b)
                total = (d.get("data") or {}).get("total_hits")
                print(f"{day}: total={total} (attempt {attempt+1})")
                ok = True
                break
            except Exception as e:
                print(f"{day}: parse err {e}")
        else:
            print(f"{day}: attempt {attempt+1} FAIL {b}")
        time.sleep(10 * (attempt + 1))  # 10s, 20s, 30s backoff
    if not ok:
        print(f"{day}: all attempts failed")
    time.sleep(15)
