# -*- coding: utf-8 -*-
"""UZI LLM 评审集成（uzi_review.py）—— 批量 + 缓存 LLM 动态评审"""
import io, json, os, sys, time

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\uzi")
from uzi_llm import llm_chat

CACHE_FILE = r"E:\test\smc_project\research\uzi_llm_cache.json"


def load_cache():
    try:
        return json.load(open(CACHE_FILE, encoding="utf-8"))
    except Exception:
        return {}


def save_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False)


def batch_review(stocks, force=False):
    """批量 LLM 评审（5 支/批，带缓存）"""
    if not stocks:
        return []
    cache = load_cache()
    results = []
    batch = []
    for s in stocks:
        k = s["code"]
        if k in cache and not force:
            results.append(cache[k])
            continue
        batch.append(s)
        if len(batch) >= 5:
            results.extend(_do_batch(batch, cache))
            batch = []
    if batch:
        results.extend(_do_batch(batch, cache))
    save_cache(cache)
    return results


def _do_batch(batch, cache):
    """调 LLM 评审一批股票"""
    lines = "\n".join(f"{s['code']} {s['name']}: rank={s['rank_score']} 阶段={s['stage']} 量比={s['v_ratio']} 盈亏比={s['rr']}"
                      for s in batch)
    prompt = f"为以下 {len(batch)} 支股票各生成 3 位评审（巴菲特、索罗斯、彼得·林奇）各 1 句 + 总评（买入/关注/观察）。\n{lines}\n用 JSON 格式：{{code:{{巴菲特:...,索罗斯:...,林奇:...,总评:...}}}}"
    reply = llm_chat([
        {"role": "system", "content": "你是 UZI-Skill 评审分析师。输出 JSON。"},
        {"role": "user", "content": prompt},
    ], temperature=0.7, max_tokens=1000)
    # 解析 JSON
    try:
        import re
        m = re.search(r"\{.*\}", reply, re.S)
        if m:
            data = json.loads(m.group(0))
        else:
            data = {}
    except Exception:
        data = {}
    results = []
    for s in batch:
        k = s["code"]
        item = {"code": k, "name": s["name"], "llm": data.get(k, {}), "verdict": (data.get(k, {}) or {}).get("总评", "")}
        cache[k] = item
        results.append(item)
    return results