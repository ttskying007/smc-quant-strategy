# -*- coding: utf-8 -*-
import io, json, sys, time, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://data.eastmoney.com/notices/"}


def get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except Exception as e:
        return None, str(e)[:120]


for day in ("2024-05-06", "2025-01-02", "2026-08-14"):
    url = (f"https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size=10&page_index=1"
           f"&ann_type=A&client_source=web&begin_time={day}&end_time={day}")
    ok = False
    for attempt in range(3):
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
            time.sleep(3)
    if not ok:
        print(f"{day}: FAIL after retries")
    time.sleep(4)
