# -*- coding: utf-8 -*-
"""调试同花顺 historical 返回结构"""
import io, json, sys, time, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

API_KEY = "sk-fuyao-OD-fAIzhM7_ir7qWoGUqT18HR_0bQz9S"
BASE = "https://fuyao.aicubes.cn"
end_ms = int(time.time() * 1000)
start_ms = end_ms - 60 * 86400 * 1000
url = f"{BASE}/api/a-share/prices/historical?thscode=600519.SH&interval=1d&start={start_ms}&end={end_ms}"
req = urllib.request.Request(url, headers={"X-api-key": API_KEY, "User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=20) as r:
    raw = r.read().decode("utf-8", errors="replace")
d = json.loads(raw)
print("code:", d.get("code"), "| message:", d.get("message"))
data = d.get("data") or {}
print("data keys:", list(data.keys()))
item = data.get("item")
print("item type:", type(item).__name__)
if isinstance(item, dict):
    print("item keys:", list(item.keys())[:10])
    for k in list(item.keys())[:2]:
        v = item[k]
        print(f"  {k}: {str(v)[:200]}")
elif isinstance(item, list) and item:
    print("first item:", str(item[0])[:300])
