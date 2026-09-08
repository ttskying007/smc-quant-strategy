# -*- coding: utf-8 -*-
"""V1 迭代4 / 审计遗留: 事件腿 Walk-Forward 独立核对
滚动窗口: 12个月训练 → 3个月测试 → 前滚3个月; 全样本时间推进。
每个测试窗只做"已锁定规则"的模拟(交易已由统一核心产生, 不重选参);
WF 验证的是:
  ① edge 跨窗口持续性(测试窗 avg/PF 分布)
  ② 唯一活自适应参数——弱市仓位权重 k(2.0) 的 WF 重选不优于固定值 → 无过拟合
     (训练窗内扫描 k∈{1,1.5,2,2.5,3}, 取风险调整收益最优, 在测试窗评估 vs 固定 k=1)
交易样本: combo_v20f_trades.csv 逐笔(2084笔, 含 risk_pct/position 权重字段)
市场代理: 200股采样 20日均值(.mkt_sample.json 固定, 逐信号日可得)
"""
import csv, io, json, os, sys
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

CSV = r"E:\test\smc_project\research\combo_v20f_trades.csv"
KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
OOS_MARK = "20250701"

# ---------- 数据加载 ----------
rows = [r for r in csv.DictReader(open(CSV, encoding="utf-8-sig"))
        if r.get("src") == "EVENT" and r.get("net_pnl_pct") not in (None, "", "None")]
for r in rows:
    r["net"] = float(r["net_pnl_pct"])
    r["risk_pct"] = float(r.get("risk_pct") or 0)
print(f"事件腿交易: {len(rows)}")

# ---------- 市场代理序列(决策时点可得) ----------
snap = json.load(open(os.path.join(KT, ".mkt_sample.json"), encoding="utf-8"))
code2bars = {}
for f in snap:
    try:
        raw = json.load(open(os.path.join(KT, f), encoding="utf-8"))
        b2 = sorted((("".join(c for c in str(x.get("t") or "") if c.isdigit())[:8], float(x["c"]))
                     for x in raw if x.get("c") and x.get("o")),
                    key=lambda x: x[0])
        if len(b2) >= 25:
            code2bars[f] = b2
    except Exception:
        pass
def proxy_on(d8):
    """给定日期的市场代理(该日可得 200 股 20 日均值)。"""
    rets = []
    for f, b2 in code2bars.items():
        ds = [x[0] for x in b2]
        # 找 <= d8 的最近日期(决策时点不得用未来)
        i = None
        for k in range(len(ds) - 1, -1, -1):
            if ds[k] <= d8:
                i = k
                break
        if i is None or i < 20:
            continue
        rets.append(b2[i][1] / b2[i - 20][1] - 1)
    return sum(rets) / len(rets) if rets else None

# 预计算每笔交易的代理值
for r in rows:
    r["proxy"] = proxy_on(r["entry_date"])
n_proxy = sum(1 for r in rows if r["proxy"] is not None)
print(f"含代理的交易: {n_proxy} ({n_proxy/len(rows):.1%})")

# ---------- 窗口机制 ----------
def ym(d8):
    return d8[:6]
def shift_ym(m, n):
    import datetime as dt
    y, mm = int(m[:4]), int(m[4:6])
    t = (y * 12 + mm - 1) + n
    return f"{t//12:04d}{t%12+1:02d}"

trades_by_month = defaultdict(list)
for r in rows:
    trades_by_month[ym(r["entry_date"])].append(r)
months = sorted(trades_by_month)
print(f"月份跨度: {months[0]} ~ {months[-1]} ({len(months)} 个月)")

# ---------- 弱市权重k评估: w = clip(1-k*proxy, 0.3, 2.0), 仓位由 risk_pct 重建 ----------
def riskadj(trs, k):
    """风险调整收益: Σ w_i × net_i × (1/risk_i) 用 risk_pct 权重。"""
    tot = 0.0
    for t in trs:
        if t["proxy"] is None or t["risk_pct"] <= 0:
            continue
        w = max(0.3, min(2.0, 1 - k * t["proxy"]))
        tot += w * t["net"] * (1.0 / t["risk_pct"] / 100)
    return tot

def eq_metrics(trs, k):
    """等权复利与风险调整两个口径。"""
    eq = 1.0
    n = 0
    pos_pnl = []
    for t in sorted(trs, key=lambda x: x["entry_date"]):
        if t["proxy"] is None or t["risk_pct"] <= 0:
            continue
        w = max(0.3, min(2.0, 1 - k * t["proxy"]))
        # 单笔贡献 = w × position_pct × net%  (position≈risk预算/风险)
        pos = min(1.0 / t["risk_pct"] / 100, 0.25) if t["risk_pct"] > 0 else 0.01
        eq *= (1 + w * pos * t["net"] / 100)
        pos_pnl.append(w * pos * t["net"] / 100)
        n += 1
    if not pos_pnl:
        return {"n": 0, "eq": 1.0, "avg_contrib": 0.0}
    wins = [x for x in pos_pnl if x > 0]
    losses = [x for x in pos_pnl if x <= 0]
    return {"n": n, "eq": round(eq, 4),
            "avg_contrib": round(sum(pos_pnl) / len(pos_pnl) * 100, 3),
            "pf": round(sum(wins) / abs(sum(losses)), 2) if losses and sum(losses) != 0 else 99}

# ---------- Walk-Forward 主循环 ----------
TRAIN, TEST, STEP = 12, 3, 3
KS = [1.0, 1.5, 2.0, 2.5, 3.0]
wf_windows = []
m0 = months[0]
test_months_seq = []
# 生成窗口: 训练窗 = [m0, m0+12), 测试 = [m0+12, m0+15), 前滚3
cur = months[0]
while True:
    train_start = cur
    train_end = shift_ym(cur, TRAIN)
    test_start, test_end = train_end, shift_ym(train_end, TEST)
    if test_start > months[-1]:
        break
    tr_tr = [t for m in months if train_start <= m < train_end for t in trades_by_month[m]]
    te_tr = [t for m in months if test_start <= m < test_end for t in trades_by_month[m]]
    if len(tr_tr) >= 30 and len(te_tr) >= 5:
        # 训练窗选 k
        best_k, best_v = None, -1e18
        for k in KS:
            v = riskadj(tr_tr, k)
            if v > best_v:
                best_k, best_v = k, v
        # 测试窗评估: WF选k vs 固定k=1
        wf = eq_metrics(te_tr, best_k)
        fx = eq_metrics(te_tr, 1.0)
        fixed2 = eq_metrics(te_tr, 2.0)
        wf_windows.append({"train": f"{train_start}~{train_end}", "test": f"{test_start}~{test_end}",
                          "n_train": len(tr_tr), "n_test": len(te_tr),
                          "wf_k": best_k, "wf_eq": wf["eq"], "wf_avg_contrib": wf["avg_contrib"], "wf_pf": wf.get("pf"),
                          "fixed1_eq": fx["eq"], "fixed2_eq": fixed2["eq"]})
        test_months_seq.append(te_tr)
    cur = shift_ym(cur, STEP)

print(f"\n== Walk-Forward: {len(wf_windows)} 个测试窗 (训练{TRAIN}月→测试{TEST}月, 步长{STEP}月) ==")
for w in wf_windows:
    print(f"  {w['test']}: n={w['n_test']:3d} WF(k={w['wf_k']}) eq={w['wf_eq']:.4f} vs 固定k1={w['fixed1_eq']:.4f} k2={w['fixed2_eq']:.4f}  (WF/固定1 比值 {w['wf_eq']/max(w['fixed1_eq'],1e-9):.3f})")

# WF 汇总
wf_eqs = [w["wf_eq"] for w in wf_windows]
f1_eqs = [w["fixed1_eq"] for w in wf_windows]
f2_eqs = [w["fixed2_eq"] for w in wf_windows]
prod_wf = 1.0
prod_f1 = 1.0
prod_f2 = 1.0
for a, b, c in zip(wf_eqs, f1_eqs, f2_eqs):
    prod_wf *= a; prod_f1 *= b; prod_f2 *= c
n_wf_win = sum(1 for a, b in zip(wf_eqs, f1_eqs) if a > b)
n_test_loss_windows = sum(1 for a in wf_eqs if a < 1.0)
verdict = {
    "windows": len(wf_windows),
    "prod_wf": round(prod_wf, 3), "prod_fixed1": round(prod_f1, 3), "prod_fixed2": round(prod_f2, 3),
    "wf_beats_fixed1_windows": f"{n_wf_win}/{len(wf_windows)}",
    "loss_windows": n_test_loss_windows,
    "k_selected_hist": {str(k): sum(1 for w in wf_windows if w["wf_k"] == k) for k in KS},
    "edge_persists": prod_wf > 1.0,
    "wf_no_overfit": prod_wf >= prod_f1 * 0.98,  # WF选k不显著差于固定(过拟合则WF差)
}
print("\n== WF 汇总 ==")
for k, v in verdict.items():
    print(f"  {k}: {v}")
print(f"\n判定: {'✅ edge跨窗口持续(WF总净值>1) 且 WF选k无过拟合' if verdict['edge_persists'] and verdict['wf_no_overfit'] else '⚠️ 检查WF结果'}")

# 跨窗口 OOS 一致性(简单统计测试窗交易)
all_test = [t for te in test_months_seq for t in te]
if all_test:
    pn = [t["net"] for t in all_test]
    w = [x for x in pn if x > 0]
    oos_stat = {"n": len(pn), "avg": round(sum(pn)/len(pn), 3),
                "wr": round(len(w)/len(pn), 3),
                "pf": round(sum(w)/abs(sum(x for x in pn if x <= 0)), 2) if any(x <= 0 for x in pn) else 99}
    print(f"  全部测试窗合并: {oos_stat}")
else:
    oos_stat = {}

with open(r"E:\test\smc_project\research\handover\V1迭代4_事件腿WalkForward.json", "w", encoding="utf-8") as fh:
    json.dump({"windows": wf_windows, "summary": verdict, "pooled_test": oos_stat,
               "config": {"train_months": TRAIN, "test_months": TEST, "step": STEP, "k_scan": KS}},
              fh, ensure_ascii=False, indent=2, default=str)
print("已写 handover/V1迭代4_事件腿WalkForward.json")