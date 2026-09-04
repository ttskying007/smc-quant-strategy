# -*- coding: utf-8 -*-
"""Direct Tencent API check: does it return newer than 20260818?"""
import io, json, sys, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh600519,day,,,5,qfq"
req = urllib.request.Request(url, headers={
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36",
    "Referer": "https://gu.qq.com/",
    "Accept": "*/*",
})
try:
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read())
    kl = d.get("data", {}).get("sh600519", {}).get("qfqday") or d.get("data", {}).get("sh600519", {}).get("day") or []
    print("API 返回最新 bars:")
    for k in kl:
        print("  ", k[0], "close:", k[2])
except Exception as e:
    print("FAIL:", e)
