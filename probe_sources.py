# -*- coding: utf-8 -*-
"""Probe free A-share data sources reachable from this host for V633 Lane A-D."""
import io, json, sys, urllib.request, urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Referer": "https://data.eastmoney.com/"}


def get(url, headers=None, timeout=10):
    h = dict(UA)
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(3000)
    except Exception as e:
        return None, str(e)[:200]


def post(url, data, headers=None, timeout=10):
    h = dict(UA)
    if headers:
        h.update(headers)
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(3000)
    except Exception as e:
        return None, str(e)[:200]


probes = [
    ("腾讯日K (Lane C/D 基础)", "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh600519,day,,,5,qfq", get),
    ("新浪日K (基础)", "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData?symbol=sh600519&scale=240&ma=no&datalen=5", get),
    ("东财行情push2 (基础)", "https://push2.eastmoney.com/api/qt/stock/get?secid=1.600519&fields=f43,f57,f58,f60", get),
    ("东财板块资金流 (Lane D)", "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=5&po=1&np=1&fltt=2&invt=2&fid=f62&fs=m:90+t:2&fields=f12,f14,f62", get),
    ("东财个股资金流 (Lane D)", "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get?secid=1.600519&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56&klt=101&lmt=5", get),
    ("东财北向资金历史 (Lane D)", "https://push2his.eastmoney.com/api/qt/kamt.kline/get?fields1=f1,f2,f3,f4&fields2=f51,f52,f53,f54,f55,f56&klt=101&lmt=5", get),
    ("东财融资融券 (Lane D)", "https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPTA_WEB_RZRQ_GGMX&columns=ALL&filter=(scode%3D%22600519%22)&pageNumber=1&pageSize=5&sortTypes=-1&sortColumns=date", get),
    ("东财ETF申赎 (Lane D)", "https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_ETF_FUND_JJCGJLCG&columns=ALL&pageNumber=1&pageSize=5", get),
    ("巨潮公告搜索 (Lane A/B)", "http://www.cninfo.com.cn/new/hisAnnouncement/query", post),
    ("东财公告 (Lane A/B)", "https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size=5&page_index=1&ann_type=A&client_source=web&stock_list=600519", get),
]

for name, url, fn in probes:
    if fn is post:
        st, body = fn(url, {"pageNum": 1, "pageSize": 5, "column": "szse", "tabName": "fulltext", "stock": "600519", "searchkey": "", "secid": "", "category": "", "trade": "", "seDate": "", "sortName": "", "sortType": "", "isHLtitle": "true"}, {"Content-Type": "application/x-www-form-urlencoded", "Referer": "http://www.cninfo.com.cn/"})
    else:
        st, body = fn(url)
    print("=" * 70)
    print(name)
    if st:
        print(f"  HTTP {st}")
        txt = body.decode("utf-8", "replace")
        print("  ", txt[:280].replace("\n", " "))
    else:
        print("  FAIL:", body)
