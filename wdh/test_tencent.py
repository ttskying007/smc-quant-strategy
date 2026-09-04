# -*- coding: utf-8 -*-
"""Test Tencent daily-kline API for full-history pull (2023-2026) and rate limits."""
import io, json, sys, time, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except Exception as e:
        return None, str(e)[:120]


# Tencent daily kline, request long history (count=800)
for cnt in (800, 1500):
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh600519,day,,,{cnt},qfq"
    st, b = get(url)
    if st == 200:
        d = json.loads(b)
        data = d.get("data", {}).get("sh600519", {})
        kl = data.get("qfqday") or data.get("day") or []
        print(f"count={cnt} -> bars:", len(kl))
        if kl:
            print("  first:", kl[0], "| last:", kl[-1])
    else:
        print(f"count={cnt} FAIL:", b)
    time.sleep(2)

# test rate: 3 rapid requests
print("\n限流测试（3 连发）:")
for i in range(3):
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh600519,day,,,10,qfq"
    st, b = get(url)
    ok = st == 200 and json.loads(b).get("code") == 0
    print(f"  req{i+1}: {'OK' if ok else 'FAIL ' + str(b)[:60]}")
