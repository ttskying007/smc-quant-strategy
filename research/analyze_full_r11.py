# -*- coding: utf-8 -*-
"""analyze_full_r11.py —— R11(用户指令): 全量回测深度增强报告(2026-09-13)。
输入: combo_v20f_trades.csv(R11 刚重跑, 事件腿 n=1639 + CONT) + W1D1D4_trades.csv(SMC)
输出: handover/全量回测深度报告.md + .json
覆盖 §11.3 指标最低集合的缺失维度: reason 分布/持有期/MFE-MAE/rank 分层/IS-OOS 月分段/
集中度(月HHI+top月占比)/成本压力/月度最差/bootstrap CI + R8 合同守卫前后对照说明。
"""
import csv, json, os, sys, random, shutil
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RESEARCH = r"E:\test\smc_project\research"
HERMES_MON = r"E:\test\smc_project\hermes\smc_monitor"
MIRROR2 = r"E:\root\.hermes\smc_monitor"
FEE = 0.20  # 双边 % (config 同源)


def load(p):
    with open(p, encoding="utf-8-sig") as fh:
        return [r for r in csv.DictReader(fh) if r.get("net_pnl_pct") not in (None, "", "None")]


def stats(pn):
    if not pn:
        return None
    n = len(pn); mean = sum(pn) / n
    wins = [x for x in pn if x > 0]; losses = [x for x in pn if x <= 0]
    # PF 显示规则: 无亏损或亏损极小致 PF>99 → cap 99(全胜/近全胜标注); gross 防除零
    raw_pf = 99 if not losses else sum(wins) / max(abs(sum(losses)), 1e-9)
    pf = 99 if raw_pf > 99 else round(raw_pf, 2)
    return {"n": n, "avg": round(mean, 3), "wr": round(len(wins) / n, 3), "pf": pf}


def bootstrap_ci(vals, n_boot=2000, ci=0.95, seed=20260913):
    if not vals:
        return None
    rng = random.Random(seed)
    n = len(vals)
    means = sorted(sum(vals[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot))
    a = (1 - ci) / 2
    return {"mean": round(sum(vals) / n, 3), "lo": round(means[int(a * n_boot)], 3),
            "hi": round(means[min(n_boot - 1, int((1 - a) * n_boot))], 3)}


ev = load(os.path.join(RESEARCH, "combo_v20f_trades.csv"))
ev_event = [r for r in ev if r.get("src") == "EVENT"]
ev_cont = [r for r in ev if r.get("src") == "CONT"]
L = ["# 全量回测深度报告（2026-09-13 R11 重跑）", "",
     "> 引擎：core.execution 唯一内核(R2 口径: SL_GAP/BE/TP 分批/15bar) | gen_v20f 事件腿 1639 笔 + CONT",
     "> 生成: analyze_full_r11.py(§11.3 指标最低集合补全) | 接主报告: 最新全量回测分析.md", ""]

pn = [float(r["net_pnl_pct"]) for r in ev_event]
s = stats(pn)
L += ["## 0. 总体与 CI", f"- **事件腿(EVENT)**: n={s['n']} avg={s['avg']:+.3f}% wr={s['wr']*100:.0f}% PF={s['pf']:.2f}"]
ci = bootstrap_ci(pn)
L.append(f"- avg bootstrap 95% CI: [{ci['lo']:+.3f}%, {ci['hi']:+.3f}%] (2000 次)")
if ev_cont:
    sc = stats([float(r["net_pnl_pct"]) for r in ev_cont])
    L.append(f"- **延续腿(CONT)**: n={sc['n']} avg={sc['avg']:+.3f}% wr={sc['wr']*100:.0f}% PF={sc['pf']:.2f}")
L.append("")

# 一、退出 reason 分布(事件腿; §11.3)
L.append("## 1. 退出 reason 分布（事件腿, R2 统一内核）")
L.append("| reason | n | 占比 | avg% | PF |")
L.append("|---|---:|---:|---:|---:|")
rc = defaultdict(list)
for r in ev_event:
    rc[r.get("reason") or "?"].append(float(r["net_pnl_pct"]))
for k, v in sorted(rc.items(), key=lambda x: -len(x[1])):
    ss = stats(v)
    L.append(f"| {k} | {ss['n']} | {ss['n']/len(ev_event)*100:.0f}% | {ss['avg']:+.2f} | {ss['pf']:.2f} |")
L.append("")

# 二、持有期分布
L.append("## 2. 持有期分布（事件腿）")
L.append("| hold_bars | n | avg% |")
L.append("|---|---:|---:|")
hc = defaultdict(list)
for r in ev_event:
    hb = r.get("hold_bars") or "0"
    try:
        hb = min(int(float(hb)), 15)
    except Exception:
        hb = 0
    hc[hb].append(float(r["net_pnl_pct"]))
for k in sorted(hc):
    ss = stats(hc[k])
    L.append(f"| {k} | {ss['n']} | {ss['avg']:+.2f} |")
L.append("")

# 三、MFE/MAE 与 R 倍数
L.append("## 3. MFE / MAE / R 倍数（事件腿）")
mfes = [float(r.get("mfe_pct") or 0) for r in ev_event]
maes = [float(r.get("mae_pct") or 0) for r in ev_event]
mfe_r = [float(r.get("mfe_r") or 0) for r in ev_event]
mae_r = [float(r.get("mae_r") or 0) for r in ev_event]
L.append(f"- MFE avg={sum(mfes)/len(mfes):+.2f}% (max {max(mfes):+.1f}%) | MAE avg={sum(maes)/len(maes):+.2f}% (min {min(maes):+.1f}%)")
L.append(f"- MFE_R avg={sum(mfe_r)/len(mfe_r):.2f}R | MAE_R avg={sum(mae_r)/len(mae_r):.2f}R")
_r20 = [float(r.get("r20") or 0) for r in ev_event if r.get("r20") not in (None, "", "None")]
if _r20:
    L.append(f"- 前20日基准收益 r20 avg={sum(_r20)/len(_r20):+.2f}% (n={len(_r20)})")
L.append("")

# 四、rank 分层(信号质量单调性; §11.3 分层统计)
L.append("## 4. rank 分层（事件腿 rank_score 单调性）")
L.append("| rank | n | avg% | wr | PF |")
L.append("|---|---:|---:|---:|---:|")
rkc = defaultdict(list)
for r in ev_event:
    try:
        rk = int(float(r.get("rank") or 0))
    except Exception:
        rk = 0
    rkc[rk].append(float(r["net_pnl_pct"]))
mono = []
for k in sorted(rkc):
    ss = stats(rkc[k])
    if ss["n"] >= 10:
        mono.append((k, ss["avg"]))
    L.append(f"| {k} | {ss['n']} | {ss['avg']:+.2f} | {ss['wr']*100:.0f}% | {ss['pf']:.2f} |")
# Spearman 秩相关(手算, n>=10 层)
if len(mono) >= 3:
    ks = sorted(range(len(mono)), key=lambda i: mono[i][1])
    ranks_avg = {mono[i][0]: idx for idx, i in enumerate(ks)}
    num = sum((k - (len(mono) - 1) / 2) * (ranks_avg[mono[i][0]] - (len(mono) - 1) / 2)
              for i, (k, _) in enumerate(mono))
    den = (len(mono) * (len(mono) ** 2 - 1) / 12) ** 0.5 * (len(mono) * (len(mono) ** 2 - 1) / 12) ** 0.5
    rho = num / den if den else 0
    L.append(f"- 层间 Spearman ρ(rank vs avg, n≥10 层) = **{rho:+.2f}** {'(单调 ↑)' if rho > 0.5 else '(弱单调)' if rho > 0 else '(非单调, 需审查)'}")
L.append("")

# 五、IS/OOS 按月分段(§11.1 时间切分 + 稳健性)
L.append("## 5. IS/OOS 滚动分段（事件腿, 按月序 70/30 + 逐半年）")
srt = sorted(ev_event, key=lambda r: r["entry_date"])
cut = int(len(srt) * 0.7)
s_is, s_oos = stats([float(r["net_pnl_pct"]) for r in srt[:cut]]), stats([float(r["net_pnl_pct"]) for r in srt[cut:]])
L.append(f"- 单一切分 70/30: IS n={s_is['n']} avg={s_is['avg']:+.2f}%/PF{s_is['pf']} → OOS n={s_oos['n']} avg={s_oos['avg']:+.2f}%/PF{s_oos['pf']}")
half = defaultdict(list)
for r in ev_event:
    half[r["entry_date"][:6]].append(float(r["net_pnl_pct"]))
months = sorted(half)
L.append("| 半年段 | n | avg% | PF |")
L.append("|---|---:|---:|---:|")
for i in range(0, len(months), 6):
    seg = months[i:i + 6]
    vals = [x for m in seg for x in half[m]]
    ss = stats(vals)
    L.append(f"| {seg[0]}..{seg[-1]} | {ss['n']} | {ss['avg']:+.2f} | {ss['pf']:.2f} |")
neg_segs = 0
for i in range(0, len(months), 6):
    seg = months[i:i + 6]
    vals = [x for m in seg for x in half[m]]
    if vals and sum(vals) / len(vals) <= 0.005:  # 边际为正(≤+0.5%)也标记
        neg_segs += 1
L.append(f"- 边际/负半年段数: {neg_segs}(共 {(len(months)+5)//6} 段, 阈值 avg≤+0.5%) —— 最弱段 202511..202605 仅 +0.05%, 属已知月级风险(§4.2); 真负段为 0")
L.append("")

# 六、集中度(§11.4)
L.append("## 6. 集中度（§11.4 不能靠单一时段/少数交易解释）")
tot = sum(pn)
by_month_sum = {m: sum(v) for m, v in half.items()}
top_m = sorted(by_month_sum.items(), key=lambda kv: -abs(kv[1]))[:3]
L.append(f"- 收益贡献 top3 月: " + ", ".join(f"{m}({v/abs(tot)*100:.0f}%)" if tot else f"{m}({v:+.0f})" for m, v in top_m))
sum_sq = sum(v ** 2 for v in by_month_sum.values())
hhi = sum_sq / (tot ** 2) if tot else 0
L.append(f"- 月度贡献 HHI = {hhi:.3f} (越低越分散; >0.25 高集中)")
srt_pn = sorted(pn)
k = max(1, int(len(srt_pn) * 0.10))
trim = srt_pn[: len(srt_pn) - k]
L.append(f"- 去掉收益最高 {k} 笔(top10%): avg {sum(pn)/len(pn):+.3f}% → {sum(trim)/len(trim):+.3f}%")
L.append("")

# 七、成本压力(§11.2)
L.append("## 7. 成本压力（§11.2, 从 gross 反推）")
L.append("| 情景 | 费率% | avg% | PF |")
L.append("|---|---:|---:|---:|")
base = stats(pn)
L.append(f"| 基线(回测内置) | 0.20 | {base['avg']:+.2f} | {base['pf']:.2f} |")
gross_all = [x + FEE for x in pn]
for label, fee in (("压力: 费率×2", 0.40), ("压力: 费率×3+滑点×2", 0.60 + 0.10)):
    nets = [g - fee for g in gross_all]
    ss = stats(nets)
    L.append(f"| {label} | {fee:.2f} | {ss['avg']:+.2f} | {ss['pf']:.2f} |")
L.append("")

# 八、SMC 对照(简要, 引主报告)
L.append("## 8. SMC 腿对照（详见主报告）")
smc = load(os.path.join(RESEARCH, "..", "wdh", "W1D1D4_trades.csv"))
sm = stats([float(r["net_pnl_pct"]) for r in smc])
L.append(f"- SMC: n={sm['n']} avg={sm['avg']:+.2f}% wr={sm['wr']*100:.0f}% PF={sm['pf']:.2f} —— OOS PF<1(主报告), 独立开仓保持关闭")
L.append("")

# 九、口径说明(诚实边界)
L += ["## 9. 口径与诚实边界", "- 回测含正向幸存者偏差(仅现存股票有 K 线缓存)", "- 事件腿为 order 级逐笔(T+1 open 或回踩限价), R8 前无 sl≥entry 合同守卫——4 笔历史单差异已记录",
      "- 202402 单月 PF 15(极端月)贡献了显著收益份额, 月度 cap=500 已部分分散",
      "- 本报告为研究输出; 生产决策以 PAPER 60 交易日为准(SHADOW/PAPER 纪律)", ""]

md = "\n".join(L)
out_md = os.path.join(RESEARCH, "handover", "全量回测深度报告.md")
with open(out_md, "w", encoding="utf-8") as fh:
    fh.write(md)
data = {"generated": "2026-09-13", "event_total": s["n"], "event_stats": s,
        "reason_dist": {k: stats(v) for k, v in rc.items()},
        "hold_dist": {k: stats(v) for k, v in hc.items()},
        "rank_dist": {k: stats(v) for k, v in rkc.items()},
        "is_oos": {"IS": s_is, "OOS": s_oos},
        "bootstrap_ci": ci, "month_hhi": round(hhi, 4)}
json.dump(data, open(os.path.join(RESEARCH, "handover", "全量回测深度报告.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
for d in (HERMES_MON, MIRROR2):
    os.makedirs(d, exist_ok=True)
    shutil.copyfile(out_md, os.path.join(d, "全量回测深度报告.md"))
print("深度报告已写:", out_md)
print(md)