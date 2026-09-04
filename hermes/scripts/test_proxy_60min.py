#!/usr/bin/env python3
"""Download 60min via akshare with proxy"""
import os, sys, json, time
from pathlib import Path

# Set proxy for requests library
os.environ['HTTP_PROXY'] = 'http://127.0.0.1:7890'
os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7890'

import akshare as ak
import requests as req

# Test 1: Direct connection to eastmoney
try:
    r = req.get('https://push2his.eastmoney.com/api/qt/stock/kline/get',
                params={'secid':'1.000001','fields1':'f1,f2,f3','fields2':'f51,f52,f53,f54,f55,f56,f57',
                        'klt':'60','fqt':'1','end':'20500000','lmt':'10'},
                timeout=10)
    print(f"Direct: {r.status_code} {len(r.text)} bytes")
except Exception as e:
    print(f"Direct FAIL: {e}")

# Test 2: Via proxy
session = req.Session()
session.proxies = {'http':'http://127.0.0.1:7890','https':'http://127.0.0.1:7890'}
try:
    r2 = session.get('https://push2his.eastmoney.com/api/qt/stock/kline/get',
                     params={'secid':'1.000001','fields1':'f1,f2,f3','fields2':'f51,f52,f53,f54,f55,f56,f57',
                             'klt':'60','fqt':'1','end':'20500000','lmt':'10'},
                     timeout=10, verify=False)
    print(f"Proxy: {r2.status_code} {len(r2.text)} bytes")
    if r2.status_code == 200:
        data = r2.json()
        print(f"Data: {json.dumps(data, ensure_ascii=False)[:200]}")
except Exception as e:
    print(f"Proxy FAIL: {e}")

# Test 3: akshare with proxy
try:
    df = ak.stock_zh_a_hist_min_em(symbol="000001", period="60",
                                    start_date="20260501", end_date="20260508", adjust="")
    print(f"akshare: {len(df)} rows")
except Exception as e:
    print(f"akshare FAIL: {e}")
