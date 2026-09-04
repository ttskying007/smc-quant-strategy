# -*- coding: utf-8 -*-
"""测试同花顺接口可用性（作为数据源冗余）"""
import io, json, sys, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "http://www.10jqka.com.cn/"}

def test(name, url):
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=12) as r:
            b = r.read()
            print(f"  ✅ {name}: {len(b)} 字节 | 前80: {b[:80]}")
            return b
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        return None

print("=== 同花顺接口测试 ===\n")
# 1. K线（d.10jqka.com.cn 日线）
test("日K线 000001", "http://d.10jqka.com.cn/v6/line/hs_000001/01/last.js")
# 2. 实时行情快照（hq）
test("实时行情 000001", "http://d.10jqka.com.cn/v2/realhead/hs_000001/last.js")
# 3. 历史K线
test("历史K线 000001", "http://d.10jqka.com.cn/v6/line/hs_000001/01/all.js")
# 4. 同花顺开放平台
test("开放平台", "https://open.10jqka.com.cn")
