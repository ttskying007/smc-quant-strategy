# -*- coding: utf-8 -*-
"""Deep-probe: announcement content, margin history depth, fund-flow history depth."""
import io, json, sys, urllib.request, urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Referer": "https://data.eastmoney.com/"}


def get(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except Exception as e:
        return None, str(e)[:200]


def post(url, data, timeout=15):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, headers={"User-Agent": UA["User-Agent"], "Content-Type": "application/x-www-form-urlencoded", "Referer": "http://www.cninfo.com.cn/"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except Exception as e:
        return None, str(e)[:200]


# 1. Announcement detail: try fetching the announcement content URL
print("### 1. 东财公告正文获取测试")
st, body = get("https://np-cnotice-stock.eastmoney.com/api/content/ann?art_code=AN202608141827994407&client_source=web&page_index=1")
if st == 200:
    try:
        d = json.loads(body)
        print("  announcement content keys:", list(d.keys())[:10] if isinstance(d, dict) else type(d))
        txt = json.dumps(d, ensure_ascii=False)[:400]
        print("  ", txt)
    except Exception as e:
        print("  parse err:", e, body[:200])
else:
    print("  FAIL:", body)

# 2. Margin financing history depth (RZRQ)
print("\n### 2. 融资融券历史深度")
st, body = get("https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPTA_WEB_RZRQ_GGMX&columns=ALL&filter=(scode%3D%22600519%22)&pageNumber=1&pageSize=10&sortTypes=-1&sortColumns=date")
if st == 200:
    try:
        d = json.loads(body)
        res = d.get("result") or {}
        print("  pages:", res.get("pages"), "| count:", res.get("count"))
        rows = (res.get("data") or [])[:2]
        if rows:
            r = rows[0]
            print("  sample fields:", {k: r.get(k) for k in ("DATE", "RZYE", "RQYL", "RZMRE", "RZCHE", "RZJME")})
    except Exception as e:
        print("  err", e)

# 3. Per-stock fund flow history depth
print("\n### 3. 个股主力资金流历史")
st, body = get("https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?lmt=0&klt=101&secid=1.600519&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56")
if st == 200:
    try:
        d = json.loads(body)
        data = d.get("data") or {}
        kl = data.get("klines") or []
        print("  klines count:", len(kl))
        if kl:
            print("  first:", kl[0])
            print("  last:", kl[-1])
    except Exception as e:
        print("  err", e, body[:200])
else:
    print("  FAIL:", body)

# 4. cninfo proper announcement query (try szse)
print("\n### 4. 巨潮公告（修正参数）")
st, body = post("http://www.cninfo.com.cn/new/hisAnnouncement/query",
                {"pageNum": 1, "pageSize": 5, "column": "szse", "tabName": "fulltext",
                 "plate": "", "stock": "600519,gssz0600519", "searchkey": "", "secid": "",
                 "category": "", "trade": "", "seDate": "2026-08-01~2026-08-17",
                 "sortName": "", "sortType": "", "isHLtitle": "true"})
if st == 200:
    t = body.decode("utf-8", "replace")
    print("  ", t[:400])
else:
    print("  FAIL:", body)
