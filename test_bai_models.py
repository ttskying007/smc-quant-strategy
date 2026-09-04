# -*- coding: utf-8 -*-
import io, json, sys, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
KEY = "sk-217j86yhudww53j4w1pu5js3ki1zvtqp"

def chat(model, prompt="用一句话点评 A 股市场。"):
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
    req = urllib.request.Request("https://api.b.ai/v1/chat/completions", data=body, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode("utf-8"))
        print(f"✅ {model}: {d['choices'][0]['message']['content'][:60]}")
    except Exception as e:
        print(f"❌ {model}: {e}")

chat("gpt-5.4-mini")
chat("minimax-m3")
chat("deepseek-v4-flash")
