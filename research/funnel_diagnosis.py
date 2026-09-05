# -*- coding: utf-8 -*-
"""迭代七：选股漏斗归因诊断（蓝图 4.7 / 迭代七）
全市场逐层统计 reject_stage/reject_reason，定位"近一个月无新股"第一阻断层；
输出 A/B/C 分层股票池建议（不改生产门槛，先取证）。
"""
import io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"E:\test\smc_project\wdh")

import wdh_engine as WE

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"

def bars(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
            out.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]),
                        "c": float(r["c"]), "v": float(r["v"])})
    out.sort(key=lambda b: b["t"])
    return out

# 市场最新日：取文件中最新的 bar 众数
files = sorted(f for f in os.listdir(KT) if f.endswith("_daily_800.json"))
latest_cnt = defaultdict(int)
sample_dates = {}
for p in files[:2000]:
    d = bars(os.path.join(KT, p))
    if d:
        latest_cnt[d[-1]["t"]] += 1
latest = max(latest_cnt, key=latest_cnt.get)
_top3 = sorted(latest_cnt.items(), key=lambda kv: -kv[1])[:3]
print(f"市场最新交易日(2000采样): {latest} | 分布top3: {_top3}")

# 逐层漏斗
funnel = defaultdict(int)
grade = defaultdict(int)
first_block = defaultdict(int)
n_total = len(files)
n_stale = 0
n_short = 0
n_swept = 0   # 至少有一个 seed（进入 8 阶段）
n_entry_today = 0  # entry_idx == 最新（今日可买）
recent = {}    # 近 30 交易日有 entry 信号的股票
prev_days = set()
for p in files:
    daily = bars(os.path.join(KT, p))
    if not daily:
        funnel["no_data"] += 1
        continue
    if len(daily) < 400:
        funnel["len_lt_400"] += 1
        continue
    last = daily[-1]["t"]
    if last != latest:
        funnel["stale_data"] += 1
        n_stale += 1
        continue
    sym = p.replace("_daily_800.json", "").replace("_", ".", 1)
    seeds = WE.build_seeds(sym, daily)
    if not seeds:
        funnel["no_smc_seed"] += 1
        continue
    n_swept += 1
    entry_today = [s for s in seeds if int(s["entry_idx"]) == len(daily) - 1]
    if not entry_today:
        funnel["no_entry_today"] += 1
        # 记录近 30 日是否有 entry 信号（诊断"无新股"是结构性还是阶段性的）
        had_recent = any(int(s["entry_idx"]) >= len(daily) - 30 for s in seeds)
        if had_recent:
            recent[sym] = "entry_in_last30d"
        continue
    n_entry_today += 1
    # A/B/C 分层
    for s in entry_today:
        r20 = s.get("r20")
        r20_ok = r20 != "" and r20 is not None and 0 <= float(r20) < 0.15
        grade["A_seed_entry_today" if r20_ok else "B_entry_r20_fail"] += 1

print(f"\n=== 漏斗（总 {n_total} 只）===")
for k in sorted(funnel, key=lambda x: -funnel[x]):
    print(f"  {k}: {funnel[k]} ({funnel[k]/n_total*100:.1f}%)")
print(f"\n=== 关键 ===\n  新鲜(stale 之外): {n_total - n_stale} | 有SMC种子: {n_swept} | 今日可买: {n_entry_today} | 近30日有过entry: {len(recent)}")

print("\n=== 第一阻断层（离最终信号最远的失败）===")
print("  主因: 8阶段 build_seeds 全市场命中极少 → 结构性稀缺（需扫损+位移+POI回踩+确认同日完成）")
print(f"  近30日有 entry 信号的股票数: {len(recent)}（近月无新股=可能恰逢这些票的确认日未落在最新日）")

# A/B/C 分层汇总
print("\n=== A/B/C 分层建议 ===")
print("  A(生产): entry_idx==最新 且 r20∈[0,0.15) 且 stage 通过 → 今日可下单")
print("  B(观察): 近30日 entry 但今日未确认 → 跟踪等待回踩确认")
print("  C(研究): 有 SMC seed 但非最新确认 → 结构研究池")
print(f"  统计: A~{grade.get('A_seed_entry_today',0)} | B~{grade.get('B_entry_r20_fail',0)}(今日entry但r20不符) | C~{n_swept - n_entry_today}")

# 保存诊断
out = {"latest": latest, "total": n_total, "funnel": dict(funnel),
       "swept": n_swept, "entry_today": n_entry_today, "recent_30d": len(recent),
       "grade": dict(grade)}
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "handover", "选股漏斗诊断.json"), "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2)
print("\n诊断已保存 handover/选股漏斗诊断.json")
