# -*- coding: utf-8 -*-
"""测试东财龙虎榜数据源（大资金直接痕迹：机构/游资席位）"""
import io, json, sys, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://data.eastmoney.com/"}

# 龙虎榜每日数据
url = "https://datacenter-web.eastmoney.com/api/data/v1/get?sortColumns=SECURITY_CODE&sortTypes=1&pageSize=5&pageNumber=1&reportName=RPT_DAILYBILLBOARD_DETAILSNEW&columns=ALL&filter=(TRADE_DATE%3E%272026-08-10%27)"
req = urllib.request.Request(url, headers=UA)
try:
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read())
    result = d.get("result") or {}
    data = result.get("data") or []
    print(f"龙虎榜数据: {len(data)} 条")
    for row in data[:5]:
        print(f"  {row.get('SECURITY_CODE')} {row.get('SECURITY_NAME_ABBR')} 日期={row.get('TRADE_DATE')} 净买={row.get('BILLBOARD_NET_AMT')}")
except Exception as e:
    print("FAIL:", e)
