# -*- coding: utf-8 -*-
"""v4_l2_reject_tracker.py —— 层2 被拒事件前向收益追踪器(稀缺根因量化)
问题: 单日 162 公告 → event_filter_soft 拒 115(71%) → 只留 20。
       被拒的 115 个事件后来涨了吗? —— 软过滤是不是在杀机会, 还是正确过滤?
本脚本(离线一次性 + 可日跑): 从 selection_result.json 的被拒记录 + announce DB 的原始事件,
  对每个被拒事件计算 5D/10D 前向收益(K线来自 KT 缓存), 与通过组对照。
判定(预注册):
  被拒组 fwd5 与通过组差异 <0.5pp → 软过滤无信息(中性)
  被拒组 fwd5 显著高于通过组 → 软过滤在杀机会(红旗)
  被拒组显著更低 → 软过滤正确(维持)
注意: 前向收益≠策略收益(未含入场时机/退出), 只回答"被杀候选的事后质量"。"""
import glob, io, json, os, sqlite3, sys, time
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
CFG_RES = r"E:\test\smc_project\research\selection_result.json"

# ---- 读最新 selection_result(被拒清单在 skipped_detail; picks 在 new_orders/days) ----
sel = json.load(open(CFG_RES, encoding="utf-8"))
print("selection_result keys:", list(sel.keys()))
rej = sel.get("skipped_detail") or []
picks = sel.get("new_orders") or []
# days 结构: {date: {orders:[...]}} —— 全部通过订单
days = sel.get("days") or {}
if isinstance(days, list):
    days = {d: {} for d in days}
for d8, dv in days.items():
    if isinstance(dv, dict):
        picks.extend(dv.get("orders") or dv.get("new_orders") or [])
print(f"picks={len(picks)} rejected={len(rej)}")

# ---- K线前向收益 ----
def load_daily(code):
    for suf in ("_SZ", "_SH", "_BJ"):
        p = os.path.join(KT, f"{code}{suf}_daily_800.json")
        if os.path.exists(p):
            try:
                raw = json.load(open(p, encoding="utf-8"))
                return [{"t": str(b.get("t"))[:8], "o": float(b["o"]), "c": float(b["c"])} for b in raw]
            except Exception:
                return None
    return None

def fwd(code, d8, days):
    dd = load_daily(code)
    if not dd:
        return None
    idx = next((k for k, b in enumerate(dd) if b["t"] == d8), None)
    # FIX(2026-09-13): off-by-one —— 旧守卫 idx+1+days>=len 比 T+days 卖点严一格,
    # 09-04 事件 T+5=09-11(idx+5=len-1)已可算却被拒. 正确守卫: 卖点 idx+days 必须存在.
    if idx is None or idx + days >= len(dd):
        return None
    base = dd[idx + 1]["o"]       # 次日开盘(与事件腿入场同语义)
    return round((dd[min(len(dd) - 1, idx + days)]["c"] / base - 1) * 100, 3)

def cohort(items, label):
    r5, r10 = [], []
    for it in items:
        code = str(it.get("code") or it.get("symbol") or "").split(".")[0]
        # FIX(2026-09-13): "2026-09-10"被[:8]截成"2026-09-"—— 与 funnel_reject_detail 同源bug
        d8 = str(it.get("date") or it.get("event_date") or it.get("day") or "")[:10].replace("-", "")
        if len(d8) != 8:
            continue
        a, b = fwd(code, d8, 5), fwd(code, d8, 10)
        if a is not None: r5.append(a)
        if b is not None: r10.append(b)
    st = lambda v: ({"n": len(v), "avg": round(sum(v) / len(v), 3),
                     "wr": round(len([x for x in v if x > 0]) / len(v) * 100, 1)} if v else {"n": 0})
    print(f"{label}: fwd5 {st(r5)} fwd10 {st(r10)}")
    return {"fwd5": st(r5), "fwd10": st(r10)}

out = {}
out["picks"] = cohort(picks, "通过组")
if rej:
    out["rejected_all"] = cohort(rej, "被拒组(全)")
    by_reason = defaultdict(list)
    for it in rej:
        by_reason[it.get("reason") or it.get("why") or "unknown"].append(it)
    out["rejected_by_reason"] = {}
    for why, items in sorted(by_reason.items(), key=lambda kv: -len(kv[1]))[:8]:
        if len(items) >= 3:
            out["rejected_by_reason"][why] = cohort(items, f"被拒[{why}]")

d5 = out.get("rejected_all", {}).get("fwd5", {}).get("avg")
p5 = out["picks"].get("fwd5", {}).get("avg")
if d5 is not None and p5 is not None:
    dd_ = round(d5 - p5, 3)
    out["delta_rej_minus_pick"] = dd_
    out["verdict"] = ("软过滤在杀机会(被拒组更高, 红旗)" if dd_ > 0.5
                      else ("软过滤正确(被拒组更低)" if dd_ < -0.5 else "软过滤中性"))
    print(f"\nΔ(被拒-通过) fwd5 = {dd_}pp → {out['verdict']}")
else:
    out["verdict"] = "样本不足(数据窗口内无可配对事件)"
    print("样本不足 — selection_result 的被拒记录可能不含历史日期/今日事件前向收益未走完")
json.dump(out, open(r"E:\test\smc_project\research\handover\V4_L2_被拒事件追踪.json", "w",
                    encoding="utf-8"), ensure_ascii=False, indent=2)
print("已写 handover/V4_L2_被拒事件追踪.json")