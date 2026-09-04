# -*- coding: utf-8 -*-
import io, json, sys, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
KEY = "sk-49ve9w04t6rfptiuyukt0hgzwo8flzfx"  # AB11_API_KEY

body = json.dumps({"model": "deepseek-v4-flash", "messages": [{"role": "user", "content": "用一句话点评 A 股。"}]}).encode("utf-8")
req = urllib.request.Request("https://api.b.ai/v1/chat/completions", data=body, headers={
    "Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read().decode("utf-8"))
    print(f"✅ B.AI chat 成功: {d['choices'][0]['message']['content'][:100]}")
    print(f"  model: {d['model']}")
except Exception as e:
    print(f"❌ B.AI chat 失败: {e}")