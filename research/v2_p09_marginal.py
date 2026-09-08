# -*- coding: utf-8 -*-
"""V2 P0-9: SMC 相对 EVENT 的边际贡献实验(蓝图 §12/§68)
问题: 组合盈利是否只是 EVENT 带来? SMC 结构(扫损+收回+位移+BOS)有无独立边际?
设计(决策时点无前视):
  A臂 = 纯 EVENT(基线): 事件腿 1640 笔纯净交易
  B臂 = EVENT∩SMC: 事件披露前 T 窗口内该股出现过 SMC W1D1D4 种子(结构确认)
      → 比较 B vs A 的 IS/OOS。若 B 不优于 A → SMC 无边际(结构确认冗余)
      若 B 优于 A → SMC 结构筛选有真实边际 → 值得继续 Structure Engine 投资
  C臂(参照) = SMC ONLY(无事件): 已知 OOS 负(逐门消融), 列作对照
数据: combo_v20f_trades.csv(EVENT 1640) + wdh/W1D1D4_seeds.csv(结构种子)
"""
import csv, io, json, os, sys
from collections import defaultdict
from datetime import date as _d
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

OOS = "20250701"
SEEDS = r"E:\test\smc_project\wdh\W1D1D4_seeds.csv"
CSV = r"E:\test\smc_project\research\combo_v20f_trades.csv"

# SMC 种子按股票索引: {code: [entry_date...]}(种子=结构确认完成日)
seeds = list(csv.DictReader(open(SEEDS, encoding="utf-8-sig")))
smc_by_code = defaultdict(list)
for s in seeds:
    c = str(s["symbol"]).split(".")[0]
    smc_by_code[c].append(str(s.get("entry_date") or ""))
for c in smc_by_code:
    smc_by_code[c].sort()

rows = [r for r in csv.DictReader(open(CSV, encoding="utf-8-sig"))
        if r.get("src") == "EVENT" and r.get("net_pnl_pct") not in (None, "", "None")]
for r in rows:
    r["net"] = float(r["net_pnl_pct"])

def has_smc_before(code, d8, window_days=45):
    """事件披露日前 window 天内该股有 SMC 结构种子(种子entry=结构确认完成日, 早于事件)。"""
    e = _d(int(d8[:4]), int(d8[4:6]), int(d8[6:8]))
    for sd in smc_by_code.get(code, []):
        if not sd:
            continue
        dd = _d(int(sd[:4]), int(sd[4:6]), int(sd[6:8]))
        gap = (e - dd).days
        if 0 <= gap <= window_days:
            return True
        if gap < 0:
            break  # 升序: 后面的更晚
    return False

def stats(ts, oos=False):
    sel = [t for t in ts if (t["entry_date"] >= OOS) == oos]
    if not sel:
        return {"n": 0}
    pn = [t["net"] for t in sel]
    w = [x for x in pn if x > 0]
    return {"n": len(pn), "avg": round(sum(pn)/len(pn), 3), "wr": round(len(w)/len(pn), 3),
            "pf": round(sum(w)/abs(sum(x for x in pn if x <= 0)), 2) if any(x <= 0 for x in pn) and sum(x for x in pn if x <= 0) != 0 else 99}

out = {"asof": __import__("time").strftime("%Y-%m-%d %H:%M:%S")}
print(f"EVENT 交易: {len(rows)} | SMC 种子股票: {len(smc_by_code)}")
for win in (30, 45, 90):
    a_arm = rows                                        # 纯EVENT
    b_arm = [r for r in rows if has_smc_before(r["symbol"].split(".")[0], r["entry_date"], win)]
    res = {
        "A_EVENT_only": {"all": stats(a_arm), "OOS": stats(a_arm, True)},
        "B_EVENT_with_SMC": {"n": len(b_arm), "all": stats(b_arm), "OOS": stats(b_arm, True)},
    }
    out[f"window_{win}d"] = res
    print(f"\n== 窗口 {win} 天 ==")
    print(f"  A 纯EVENT:  all={res['A_EVENT_only']['all']}")
    print(f"              OOS={res['A_EVENT_only']['OOS']}")
    print(f"  B EVENT+SMC({len(b_arm)}笔): all={res['B_EVENT_with_SMC']['all']}")
    print(f"              OOS={res['B_EVENT_with_SMC']['OOS']}")

# 预注册判定(45天窗口, 需B样本>=100且OOS>=50)
b45 = out["window_45d"]["B_EVENT_with_SMC"]
a_oos = out["window_45d"]["A_EVENT_only"]["OOS"]
verdict = {
    "B_sample_ok": b45["all"]["n"] >= 100 and b45["OOS"]["n"] >= 50,
    "B_beats_A_OOS_avg": b45["OOS"]["avg"] > a_oos["avg"],
    "B_beats_A_OOS_pf": b45["OOS"]["pf"] > a_oos["pf"],
}
verdict["SMC_has_marginal_contribution"] = all(verdict.values())
out["verdict_45d"] = verdict
print("\n== 预注册判定(45天窗) ==")
print(f"  B样本充足: {verdict['B_sample_ok']} (n={b45['all']['n']}/OOS={b45['OOS']['n']})")
print(f"  B优于A(OOS avg): {verdict['B_beats_A_OOS_avg']} ({b45['OOS']['avg']}% vs {a_oos['avg']}%)")
print(f"  B优于A(OOS PF): {verdict['B_beats_A_OOS_pf']} ({b45['OOS']['pf']} vs {a_oos['pf']})")
print(f"  → SMC 有边际贡献: {verdict['SMC_has_marginal_contribution']}")

with open(r"E:\test\smc_project\research\handover\P09_SMC边际贡献实验.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2, default=str)
print("\n已写 handover/P09_SMC边际贡献实验.json")