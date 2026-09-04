# -*- coding: utf-8 -*-
"""测试东财大宗交易数据源（大资金直接买入/卖出：折价/溢价信号）"""
import io, json, sys, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://data.eastmoney.com/"}

url = ("https://datacenter-web.eastmoney.com/api/data/v1/get?"
       "sortColumns=TRADE_DATE&sortTypes=-1&pageSize=10&pageNumber=1"
       "&reportName=RPT_DATA_BLOCKTRADE&columns=ALL")
req = urllib.request.Request(url, headers=UA)
try:
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read())
    result = d.get("result") or {}
    data = result.get("data") or []
    print(f"大宗交易: {len(data)} 条")
    if data:
        print("字段:", list(data[0].keys())[:15])
        for row in data[:5]:
            print(f"  {row.get('SECURITY_CODE')} {row.get('SECURITY_NAME_ABBR')} 日期={str(row.get('TRADE_DATE'))[:10]} 价={row.get('TRADE_PRICE')} 折溢价={row.get('DISCOUNT_RATIO')}")
except Exception as e:
    print("FAIL:", e)
