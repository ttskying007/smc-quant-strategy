# -*- coding: utf-8 -*-
"""测试同花顺 API（fuyao.aicubes.cn）—— X-api-key 认证"""
import io, json, sys, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

API_KEY = "sk-fuyao-OD-fAIzhM7_ir7qWoGUqT18HR_0bQz9S"
BASE = "https://fuyao.aicubes.cn"

def call(path, params=""):
    url = f"{BASE}{path}?{params}" if params else f"{BASE}{path}"
    req = urllib.request.Request(url, headers={"X-api-key": API_KEY, "User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            b = r.read().decode("utf-8", errors="replace")
            print(f"  ✅ {path}: {len(b)} 字节 | {b[:300]}")
            return b
    except Exception as e:
        print(f"  ❌ {path}: {e}")
        return None

print("=== 同花顺 API 测试 ===\n")
call("/api/a-share/prices/snapshot", "thscodes=600519.SH,000001.SZ")
call("/api/a-share/calendar")
