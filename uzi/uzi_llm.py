# -*- coding: utf-8 -*-
"""B.AI LLM 接入（uzi_llm.py）—— deepseek-v4-flash 动态生成 UZI 评审"""
import io, json, sys

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import requests

# AB11_API_KEY（settings.yaml: ab11 provider）
B_AI_KEY = "sk-49ve9w04t6rfptiuyukt0hgzwo8flzfx"
B_AI_URL = "https://api.b.ai/v1/chat/completions"
MODEL = "deepseek-v4-flash"


def llm_chat(messages, temperature=0.7, max_tokens=800, retries=4):
    """调 B.AI chat completions（requests，deepseek-v4-flash，带重试）"""
    import time
    for attempt in range(retries):
        try:
            r = requests.post(B_AI_URL,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {B_AI_KEY}"},
                json={"model": MODEL, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
                timeout=90)
            if r.status_code == 200:
                content = r.json()["choices"][0]["message"]["content"]
                return content or "(LLM空回复)"
            return f"[LLM错误 {r.status_code}]"
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))  # 2,4,6s 重试
            else:
                return f"[LLM异常 {e}]"


def uzi_analyze_llm(code, name, rank_score, stage, v_ratio, rr, entry, tp, sl, market="8-25"):
    """UZI 动态评审（LLM）：生成评审意见"""
    prompt = (f"分析 {code} {name}：rank={rank_score} 阶段={stage} 量比={v_ratio} 盈亏比={rr}。"
              f"以巴菲特、索罗斯、彼得·林奇的口吻各给 1 句评审，然后总评（买入/关注/观察+理由）。")
    reply = llm_chat([
        {"role": "system", "content": "你是 UZI-Skill 评审分析师，输出简洁专业。"},
        {"role": "user", "content": prompt},
    ], temperature=0.8, max_tokens=500)
    return reply or "(LLM 未返回)"


if __name__ == "__main__":
    r = uzi_analyze_llm("600519", "贵州茅台", 6, "ACCUM", 2.5, 1.8, 1272, 1450, 1200)
    print("UZI LLM 评审:")
    print(r[:600])
