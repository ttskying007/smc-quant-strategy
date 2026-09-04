# -*- coding: utf-8 -*-
import io, json, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
try:
    import requests
except ImportError:
    print("requests 未装，用 urllib 重试带 ssl 上下文")
    import urllib.request, ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    KEY = "sk-49ve9w04t6rfptiuyukt0hgzwo8flzfx"
    body = json.dumps({"model": "deepseek-v4-flash", "messages": [{"role": "user", "content": "用一句话点评A股"}]}).encode()
    req = urllib.request.Request("https://api.b.ai/v1/chat/completions", data=body, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
            d = json.loads(r.read().decode("utf-8"))
        print(f"✅ urllib+ssl: {d['choices'][0]['message']['content'][:80]}")
    except Exception as e:
        print(f"❌ urllib+ssl: {e}")
    sys.exit()

KEY = "sk-49ve9w04t6rfptiuyukt0hgzwo8flzfx"
try:
    r = requests.post("https://api.b.ai/v1/chat/completions",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"},
        json={"model": "deepseek-v4-flash", "messages": [{"role": "user", "content": "用一句话点评A股"}]},
        timeout=60)
    print("status:", r.status_code)
    if r.status_code == 200:
        print(f"✅ requests: {r.json()['choices'][0]['message']['content'][:80]}")
    else:
        print("body:", r.text[:200])
except Exception as e:
    print(f"❌ requests: {e}")
