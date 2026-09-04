# -*- coding: utf-8 -*-
import io, json, sys, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except Exception as e:
        return None, str(e)[:200]


# Tencent 60min
st, b = get("https://web.ifzq.gtimg.cn/appstock/app/kline/mkline?param=sh600519,m60,,400")
if st == 200:
    d = json.loads(b)
    data = d.get("data", {}).get("sh600519", {})
    mk = data.get("m60") or data.get("qfqm60") or []
    print("腾讯 m60 bars:", len(mk))
    if mk:
        print("  first:", mk[0])
        print("  last:", mk[-1])
else:
    print("腾讯 FAIL:", b)

# Sina 60min with large datalen
st2, b2 = get("https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData?symbol=sh600519&scale=60&ma=no&datalen=2000")
if st2 == 200:
    try:
        d2 = json.loads(b2)
        print("新浪 60min bars:", len(d2))
        if d2:
            print("  first:", d2[0])
            print("  last:", d2[-1])
    except Exception as e:
        print("新浪 parse err:", str(e)[:100], b2[:200])
else:
    print("新浪 FAIL:", b2)
