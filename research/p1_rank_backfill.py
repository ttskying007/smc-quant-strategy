# -*- coding: utf-8 -*-
"""P1-4: 持仓 rank_score 落库 —— 回填缺失的 rank_score（96.7%→0）
用无泄漏 rank 特征（T 日量/T-1 量 + 7 特征）回填"""
import io, json, sys
sys.path.insert(0, r"E:\test\smc_project\research")
import paper_sim as ps
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

led = ps.load_ledger()
n_missing = sum(1 for t in led if t.get("rank_score") is None)
print(f"缺失 rank_score: {n_missing}/{len(led)}")

filled = 0
for t in led:
    if t.get("rank_score") is not None:
        continue
    code = t.get("code")
    sig = str(t.get("signal_date", "") or t.get("disclose_date", ""))
    sig8 = sig.replace("-", "")
    bs = ps.bars_of(code)
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    if sig8 not in dates:
        continue
    i = dates.index(sig8)
    if i < 130:
        t["rank_score"] = 2  # 数据不足降级
        t["note"] = (t.get("note", "") + " | rank=2(历史不足降级)").strip()
        filled += 1
        continue
    st, _ = ps.stage_and_deep(bs, i)
    adx = ps.adx14_of(bs, i) or 0
    avg_v = sum(bs[k]["v"] for k in range(i - 19, i + 1)) / 20 if i >= 19 else 0
    v_ratio = bs[i]["v"] / avg_v if avg_v > 0 else 1.0
    v2_ratio = bs[i - 1]["v"] / avg_v if (avg_v > 0 and i >= 1) else 0
    stage_span = 0
    for j in range(i, max(0, i - 60), -1):
        if ps.stage_and_deep(bs, j)[0] == st:
            stage_span += 1
        else:
            break
    adx_span = 0
    for j in range(i, max(0, i - 40), -1):
        if (ps.adx14_of(bs, j) or 0) >= 20:
            adx_span += 1
        else:
            break
    wt = ps.weekly_trend_of(bs, i)
    rs = (2 if st == "ACCUM" else 1)
    rs += (1 if v_ratio > 1.2 else 0) + (1 if v_ratio >= 2.0 else 0)
    rs += (1 if 6 <= stage_span <= 15 else 0) + (1 if adx_span > 15 else 0)
    rs += 1 if wt == "down" else 0
    rs += 1 if (v_ratio >= 1.5 and v2_ratio >= 1.5) else 0
    t["rank_score"] = rs
    t["v_ratio"] = round(v_ratio, 2)
    t["stage_span"] = stage_span
    t["adx_span"] = adx_span
    t["weekly_trend"] = wt
    filled += 1

ps.save_ledger(led)
print(f"回填 {filled} 笔")
from collections import Counter
led2 = ps.load_ledger()
missing2 = sum(1 for t in led2 if t.get("rank_score") is None)
print(f"缺失率: {missing2}/{len(led2)} ({100*missing2/len(led2):.0f}%)")
print("rank 分布:", dict(Counter(t.get("rank_score") for t in led2)))
