#!/usr/bin/env python3
"""Try to download ETF/index data from alternative Chinese data sources"""
import json, sys, time, os
from pathlib import Path

CACHE_DIR = Path('/root/.hermes/kline_cache')

# Set proxy
os.environ['HTTP_PROXY'] = 'http://127.0.0.1:7890'
os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7890'

# ETF codes to try - major A-share ETFs
ETF_CODES = [
    # Broad market ETFs
    '510050', '510300', '510500', '510880', '510900', '512100', '512500',
    '512880', '512690', '512760', '515000', '515050', '515790', '515880',
    '516160', '517090', '518880', '159919', '159915', '159949', '159845',
    '159865', '159928', '159949', '159967', '159985',
    # Sector ETFs
    '512010', '512170', '512480', '512660', '512710', '515030', '515700',
    '516010', '516970', '517010', '159766', '159781', '159865',
    # Bond/money market
    '511010', '511880', '511990',
    # Indices
    '000001', '399001', '399006', '399005', '399300', '688001',
]

# Try akshare first
try:
    import akshare as ak
    HAS_AKSHARE = True
except:
    HAS_AKSHARE = False

print(f"akshare available: {HAS_AKSHARE}")
print(f"Testing ETF downloads...")

success = 0
for i, code in enumerate(ETF_CODES[:30]):  # Try first 30
    # Determine exchange suffix
    if code.startswith(('5', '6')):  # SH
        symbol = f"{code}.SH"
    elif code.startswith(('0', '1', '3')):  # SZ
        symbol = f"{code}.SZ"
    else:
        symbol = f"{code}.SH"
    
    fname = f"{code}_{symbol.split('.')[1]}_daily_300.json"
    fpath = CACHE_DIR / fname
    if fpath.exists():
        success += 1
        continue
    
    if HAS_AKSHARE:
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily",
                                    start_date="20240101", end_date="20260508", adjust="qfq")
            if df is not None and len(df) > 50:
                records = []
                for _, row in df.iterrows():
                    records.append({
                        'date': str(row['日期']),
                        'o': float(row['开盘']),
                        'h': float(row['最高']),
                        'l': float(row['最低']),
                        'c': float(row['收盘']),
                        'v': float(row['成交量']),
                    })
                json.dump(records, open(fpath, 'w'))
                success += 1
                print(f"  ✅ {code}: {len(records)} bars")
            else:
                print(f"  ❌ {code}: insufficient data ({len(df) if df is not None else 0})")
        except Exception as e:
            print(f"  ❌ {code}: {str(e)[:50]}")
    else:
        print(f"  ❌ {code}: akshare not available")
    
    if (i+1) % 5 == 0:
        time.sleep(2)  # rate limit

print(f"\nTotal: {success}/{len(ETF_CODES[:30])} ETFs/indices cached")
