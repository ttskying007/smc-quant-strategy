# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\uzi")
from uzi_llm import llm_chat

r = llm_chat([{"role": "user", "content": "你好，一句话"}], max_tokens=100)
print(f"回复: [{r}] len={len(r) if r else 0}")
