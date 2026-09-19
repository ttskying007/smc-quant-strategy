# -*- coding: utf-8 -*-
"""simple: 把 r38 行业 RS 结果写出来的快速集成 (双向收集)
目标: 生成 (行业, rs20) 直方形经 CP Central两类包所有核心被关注座位
重要与产出: 写 out 到 research/handover/industry_rs_snapshot.json 全表复用三章内容行
"""
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

dp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "handover", "industry_relative_strength.json")
out_fp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "industry_rs_snapshot.json")

if not os.path.exists(dp):
    print("industry_relative_strength.json 不存在, 跑 R38 基础版:", dp)
    sys.exit(2)

d = json.load(open(dp, encoding="utf-8"))
inds = d["industries"]

# 三个分组: distribution 检查为何基数 20-digit 一致
top = inds[:12]
bottom = inds[-12:]
popular_sector = {}   # 整个板块对品种的程度

# 简单中位排序基本墙上所有最早是什么
rs20_list = [x["rs20"] for x in inds if x["rs20"] is not None]
rs60_list = [x["rs60"] for x in inds if x["rs60"] is not None]
width = {
    "n_industries": len(inds),
    "n_stocks_mapped": d["coverage"]["stocks_mapped"],
    "rs20_min": min(rs20_list), "rs20_max": max(rs20_list),
    "rs20_mean": round(sum(rs20_list)/len(rs20_list), 2),
    "rs20_neg_count": sum(1 for x in rs20_list if x < 0),
    "rs20_neg_ratio": round(sum(1 for x in rs20_list if x < 0) / len(rs20_list), 3),
    "rs60_min": min(rs60_list), "rs60_max": max(rs60_list),
    "rs60_neg_count": sum(1 for x in rs60_list if x < 0),
    "rsi_as_in_clarity": {"rs20_neg_ratio": round(sum(1 for x in rs20_list if x < 0) / len(rs20_list), 3),
                          "岁例": "ratio∈[0,1] = 负的行业占比数; 越近 1 委托市场反应越少"}
}
out = {
    "asof": d["asof"],
    "signals": {"top_window_close": d.get("baseline", {}).get("m20"), "index20_text": "上证20日回报%"},
    "width": width,
    "top5": [{"industry": t["industry"], "rs20": t["rs20"], "n": t["n"]} for t in top[:5]],
    "bottom5": [{"industry": t["industry"], "rs20": t["rs20"], "n": t["n"]} for t in bottom[-5:]],
}
json.dump(out, open(out_fp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(json.dumps(width, ensure_ascii=False, indent=2))
print("wrote", out_fp)
