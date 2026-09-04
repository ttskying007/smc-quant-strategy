# -*- coding: utf-8 -*-
"""Force-refresh one stock via Tencent with full headers, check latest date."""
import io, json, sys, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36",
      "Referer": "https://gu.qq.com/", "Accept": "*/*"}
url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh600519,day,,,800,qfq"
req = urllib.request.Request(url, headers=UA)
try:
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read())
    data = d.get("data", {}).get("sh600519", {})
    kl = data.get("qfqday") or data.get("day") or []
    print("bars:", len(kl))
    if kl:
        print("latest:", kl[-1][0], "close:", kl[-1][2])
        print("prev:", kl[-2][0])
except Exception as e:
    print("FAIL:", e)
