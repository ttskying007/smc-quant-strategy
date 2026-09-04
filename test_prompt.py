# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\uzi")
from uzi_llm import llm_chat

prompt = "分析 600519 贵州茅台：rank=6 阶段=ACCUM 量比=2.5 盈亏比=1.8。以巴菲特、索罗斯、彼得·林奇的口吻各给 1 句评审，然后总评（买入/关注/观察+理由）。"
r = llm_chat([
    {"role": "system", "content": "你是 UZI-Skill 评审分析师，输出简洁专业。"},
    {"role": "user", "content": prompt},
], temperature=0.8, max_tokens=500)
print(f"len={len(r) if r else 0}")
print(r[:400] if r else "EMPTY")
