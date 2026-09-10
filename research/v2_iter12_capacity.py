# -*- coding: utf-8 -*-
"""ITER12 容量研究(诚实重设计 v3)
v2 教训(诚实记录): 复利+无并发上限+80%胜率 → 绝对收益天文数字, 组合引擎重放对容量
问题答非所问。容量的正确问题是【成交可行性】而非组合复利:
  给定单笔仓位(风险预算, 非复利) 与当日成交量, 参与率 5/10/20% 下:
    binding 率 = 需要股数 > 量×参与率 的订单比例
    期望可投入单笔资金 = min(风险仓位需求, 量×参与率×价)
  → 输出: 三档资金(100万/500万/1000万)下"策略能实际部署的资金比例"与 binding 分布。
判定(预注册):
  binding 率 <5% → 该参与率下该档资金可完整部署;
  5~20% → 部分截断(侵蚀但可行);
  >20% → 严重容量约束。
"""
import csv, io, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
rows = [r for r in csv.DictReader(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                    "combo_v20f_trades.csv"), encoding="utf-8-sig"))
        if r.get("src") == "EVENT"]

kl = {}
def daily_of(code):
    if code in kl:
        return kl[code]
    fp = None
    for suf in ("_SZ", "_SH", "_BJ"):
        p = os.path.join(KL, f"{code}{suf}_daily_800.json")
        if os.path.exists(p):
            fp = p
            break
    out = None
    if fp:
        raw = json.load(open(fp, encoding="utf-8"))
        out = [{"t": str(b.get("t"))[:8], "o": float(b["o"]), "h": float(b["h"]),
                "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v") or 0)} for b in raw]
    kl[code] = out
    return out

stats = {}
deploy_pct = {}
for cash in (1_000_000, 5_000_000, 10_000_000):
    for pr in (0.05, 0.10, 0.20):
        n = binding = 0
        cap_sum = need_sum = 0.0
        for r in rows:
            c = r["symbol"].split(".")[0]
            dd = daily_of(c)
            if not dd:
                continue
            i = next((k for k, b in enumerate(dd) if b["t"] == r["buy_date"]), None)
            if i is None or i == 0:
                continue
            limit_px = round(dd[i - 1]["c"] * 0.99, 3)
            try:
                sl = float(r.get("sl") or 0) or round(limit_px * 0.94, 3)
            except (TypeError, ValueError):
                sl = round(limit_px * 0.94, 3)
            risk = max((limit_px - sl) / limit_px, 0.02)
            pos_pct = min(0.25, max(0.02, 0.01 / risk))
            need_shares = int(cash * pos_pct / limit_px)
            vol_shares = (dd[i].get("v") or 0) * 100 * pr
            n += 1
            need_sum += need_shares * limit_px
            cap_sum += min(need_shares, vol_shares) * limit_px
            if need_shares > vol_shares:
                binding += 1
        br = round(binding / n * 100, 2) if n else None
        dp = round(cap_sum / need_sum * 100, 2) if need_sum else None
        stats[f"{cash/1e6:.0f}M@{pr:.0%}"] = {"n": n, "binding_n": binding,
                                              "binding_pct": br, "deployable_pct": dp}
        print(f"  {cash/1e6:.0f}M@{pr:.0%}: n={n} binding={binding}({br}%) 可部署资金比例={dp}%")

verdict = {}
for cash in (1_000_000, 5_000_000, 10_000_000):
    b5 = stats[f"{cash/1e6:.0f}M@5%"]["binding_pct"]
    b10 = stats[f"{cash/1e6:.0f}M@10%"]["binding_pct"]
    b20 = stats[f"{cash/1e6:.0f}M@20%"]["binding_pct"]
    verdict[f"{cash/1e6:.0f}M"] = {
        "conclusion": ("完整部署" if b5 < 5 else ("部分截断(可行)" if b20 < 20 else "严重容量约束")),
        "binding_5/10/20": [b5, b10, b20]}
out = {"method": "固定名义仓位成交可行性(非组合复利); v2复利口径天文数字教训已记录",
       "stats": stats, "verdict": verdict,
       "conclusion": verdict["10M"]["conclusion"]}
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "handover", "ITER12_容量模拟.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2, default=str)
print("\n判定:", json.dumps(verdict, ensure_ascii=False, indent=1))
print("已写 handover/ITER12_容量模拟.json")