# -*- coding: utf-8 -*-
import io, json, sys, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
KEY = "sk-217j86yhudww53j4w1pu5js3ki1zvtqp"

# 尝试不同认证头 + 端点
tests = [
    ("Bearer + chat/completions", "https://api.b.ai/v1/chat/completions", {"Authorization": f"Bearer {KEY}"}),
    ("X-Api-Key + chat", "https://api.b.ai/v1/chat/completions", {"X-Api-Key": KEY}),
    ("api-key + chat", "https://api.b.ai/v1/chat/completions", {"api-key": KEY}),
    ("Bearer + v1/responses", "https://api.b.ai/v1/responses", {"Authorization": f"Bearer {KEY}"}),
]
body = json.dumps({"model": "deepseek-v4-flash", "messages": [{"role": "user", "content": "hi"}]}).encode("utf-8")
for name, url, headers in tests:
    h = {"Content-Type": "application/json", **headers}
    try:
        req = urllib.request.Request(url, data=body, headers=h)
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode("utf-8"))
        print(f"✅ {name}: {str(d)[:120]}")
    except Exception as e:
        print(f"❌ {name}: {e}")
