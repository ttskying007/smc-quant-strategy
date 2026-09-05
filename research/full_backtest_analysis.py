# -*- coding: utf-8 -*-
"""全量全面回测分析器（2026-09-05 最终版）
输入：事件腿 combo_v20f_trades.csv（EVENT+CONT，cap500）+ SMC腿 W1D1D4_trades.csv（TP≥1.5R）
输出：总体/逐年逐月/逐笔买点卖点/信号质量/盈亏比R倍数/收益率/IS-OOS/Walk-Forward 综合报告
"""
import csv, json, os, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.metrics import stats_of, fmt, is_oos_split, walk_forward_split

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RESEARCH = r"E:\test\smc_project\research"
OUT = os.path.join(RESEARCH, "handover", "全量全面回测分析报告.md")
OUTJ = os.path.join(RESEARCH, "handover", "全量全面回测分析.json")

def load(p):
    if not os.path.exists(p):
        return []
    rows = []
    with open(p, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            try:
                r["net_pnl_pct"] = float(r["net_pnl_pct"]) if r["net_pnl_pct"] not in (None, "", "None") else None
            except Exception:
                r["net_pnl_pct"] = None
            rows.append(r)
    return rows

ev = load(os.path.join(RESEARCH, "combo_v20f_trades.csv"))
smc = load(os.path.join(RESEARCH, "..", "wdh", "W1D1D4_trades.csv"))
print(f"事件腿: {len(ev)} | SMC腿: {len(smc)}", flush=True)

L = ["# 全量全面回测分析报告（2026-09-05 最终版）", "",
     "数据：事件腿 combo_v20f（cap500）+ SMC腿 W1D1D4（TP≥1.5R），全市场 4905 只",
     "修复后代码：ISO周/OB-FVG/防未来/量能/BOS窗口/涨停跳空/滑点/ATR自适应/分位阶段/金额解析/风险仓位", ""]

# 一、总体
L.append("## 一、总体表现")
L.append("| 腿 | n | 均值% | 胜率% | PF | payoff | 中位% | 最差% | 最好% |")
L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
for name, rows in (("事件腿(EVENT)", [r for r in ev if r.get("src") != "CONT"]),
                   ("延续腿(CONT)", [r for r in ev if r.get("src") == "CONT"]),
                   ("事件腿合计", ev), ("SMC腿", smc)):
    pn = [r["net_pnl_pct"] for r in rows if r["net_pnl_pct"] is not None]
    s = stats_of(pn)
    if s:
        L.append(f"| {name} | {s['n']:,} | {s['avg']:+.2f} | {s['win']*100:.1f} | {s['pf']:.2f} | {s['payoff']:.2f} | {s['median']:+.2f} | {s['min']:+.2f} | {s['max']:+.2f} |")
L.append("")

# 二、逐年
L.append("## 二、逐年（事件腿合计 / SMC腿）")
by = {}
for tag, rows in (("事件腿", ev), ("SMC腿", smc)):
    d = defaultdict(list)
    for r in rows:
        if r["net_pnl_pct"] is None:
            continue
        d[str(r.get("entry_date", ""))[:4]].append(r["net_pnl_pct"])
    by[tag] = d
all_y = sorted(set(by["事件腿"]) | set(by["SMC腿"]))
L.append("| 年份 | 事件腿 n | 事件腿均值% | 事件腿PF | SMC腿 n | SMC腿均值% | SMC腿PF |")
L.append("|---|---:|---:|---:|---:|---:|---:|")
for y in all_y:
    s0, s1 = stats_of(by["事件腿"].get(y, [])), stats_of(by["SMC腿"].get(y, []))
    L.append(f"| {y} | {s0['n'] if s0 else 0} | {s0['avg'] if s0 else 0:+.2f} | {s0['pf'] if s0 else 0:.2f} | {s1['n'] if s1 else 0} | {s1['avg'] if s1 else 0:+.2f} | {s1['pf'] if s1 else 0:.2f} |")
L.append("")

# 三、逐月（事件腿）
L.append("## 三、逐月（事件腿合计）")
by_month = defaultdict(list)
for r in ev:
    if r["net_pnl_pct"] is None:
        continue
    by_month[str(r.get("entry_date", ""))[:6]].append(r["net_pnl_pct"])
L.append("| 月份 | n | 均值% | 胜率% |")
L.append("|---|---:|---:|---:|")
for m in sorted(by_month):
    s = stats_of(by_month[m])
    if s:
        L.append(f"| {m} | {s['n']} | {s['avg']:+.2f} | {s['win']*100:.1f} |")
L.append("")

# 四、信号质量
L.append("## 四、信号质量（按腿/出场分层）")
by_src = defaultdict(list)
for r in ev:
    if r["net_pnl_pct"] is not None:
        by_src["EVENT" if r.get("src") != "CONT" else "CONT"].append(r["net_pnl_pct"])
for r in smc:
    if r["net_pnl_pct"] is not None:
        by_src["SMC_" + r.get("reason", "?")].append(r["net_pnl_pct"])
for k in sorted(by_src):
    L.append(f"- **{k}**: {fmt(stats_of(by_src[k]))}")
L.append("")

# 五、逐笔卖点分布（SMC）
L.append("## 五、逐笔卖点分布（SMC腿）")
reason_cnt = defaultdict(int)
reason_pnl = defaultdict(list)
for r in smc:
    if r["net_pnl_pct"] is None:
        continue
    reason_cnt[r.get("reason", "?")] += 1
    reason_pnl[r.get("reason", "?")].append(r["net_pnl_pct"])
for k, v in sorted(reason_cnt.items(), key=lambda kv: -kv[1]):
    s = stats_of(reason_pnl[k])
    L.append(f"- **{k}**: {v} 笔 ({v/max(len(smc),1)*100:.1f}%) — {fmt(s)}")
L.append("")

# 六、盈亏比与 R 倍数
L.append("## 六、盈亏比与期望")
for name, rows in (("事件腿", ev), ("SMC腿", smc)):
    pn = [r["net_pnl_pct"] for r in rows if r["net_pnl_pct"] is not None]
    s = stats_of(pn)
    if s:
        L.append(f"- **{name}**: avgWin {s['avg_win']:+.2f}% / avgLoss -{s['avg_loss']:.2f}% | payoff {s['payoff']:.2f} | PF {s['pf']:.2f} | 期望 {s['avg']:+.2f}%/笔")
L.append("")
# SMC R倍数（seeds锚点）
seeds = load(os.path.join(RESEARCH, "..", "wdh", "W1D1D4_seeds.csv"))
rr = []
for s in seeds:
    try:
        ep, zl, sw, tg = float(s.get("entry_price") or 0), float(s.get("zone_low") or 0), float(s.get("sweep_low") or 0), float(s.get("target") or 0)
        sl = min(zl, sw) if sw else zl
        if ep > 0 and sl > 0 and tg > ep and sl < ep:
            rr.append((tg - ep) / (ep - sl))
    except Exception:
        continue
if rr:
    L.append(f"- **SMC R倍数**: 均值 {sum(rr)/len(rr):.2f}R / 中位 {sorted(rr)[len(rr)//2]:.2f}R（n={len(rr)}）")
L.append("")

# 七、IS/OOS
L.append("## 七、IS/OOS（70/30）")
for name, rows in (("事件腿", ev), ("SMC腿", smc)):
    is_r, oos_r, cut = is_oos_split([r for r in rows if r["net_pnl_pct"] is not None])
    L.append(f"- **{name}**: IS(前70%) {fmt(stats_of([r['net_pnl_pct'] for r in is_r]))} → OOS(后30%) {fmt(stats_of([r['net_pnl_pct'] for r in oos_r]))}")
L.append("")

# 八、Walk-Forward（事件腿）
L.append("## 八、Walk-Forward（事件腿，IS12月→OOS3月）")
wf = walk_forward_split([r for r in ev if r["net_pnl_pct"] is not None])
oos_all = []
for is_r, oos_r, label in wf:
    si, so = stats_of([r["net_pnl_pct"] for r in is_r]), stats_of([r["net_pnl_pct"] for r in oos_r])
    L.append(f"- {label}: IS {si['avg']:+.2f}% → OOS {so['avg']:+.2f}% (PF {so['pf']:.2f})" if si and so else f"- {label}: 数据不足")
    oos_all.extend(r["net_pnl_pct"] for r in oos_r)
L.append(f"- **全部 OOS 合并**: {fmt(stats_of(oos_all))}")
L.append("")

# 九、收益率（1%仓位复利）
L.append("## 九、累计收益率（每笔 1% 仓位复利）")
for name, rows in (("事件腿", ev), ("SMC腿", smc)):
    ok = [r for r in rows if r["net_pnl_pct"] is not None]
    ok.sort(key=lambda r: str(r.get("entry_date", "")))
    if not ok:
        continue
    cum = 1.0
    peak = -1e9
    mdd = 0.0
    for r in ok:
        cum *= (1 + 0.01 * r["net_pnl_pct"] / 100)
        peak = max(peak, cum)
        mdd = max(mdd, (peak - cum) / peak)
    ann = ((cum) ** (1 / 3) - 1) * 100
    L.append(f"- **{name}**: 累计净值(1%仓) {cum:.2f} | 累计 {(cum-1)*100:+.0f}% | 年化 {ann:+.1f}% | 最大回撤 {mdd*100:.1f}%")
L.append("")

md = "\n".join(L)
with open(OUT, "w", encoding="utf-8") as fh:
    fh.write(md)
# json
data = {"ev_total": len(ev), "smc_total": len(smc)}
for name, rows in (("EVENT", ev), ("SMC", smc)):
    data[name] = stats_of([r["net_pnl_pct"] for r in rows if r["net_pnl_pct"] is not None])
with open(OUTJ, "w", encoding="utf-8") as fh:
    json.dump(data, fh, ensure_ascii=False, indent=1)
print(md[:2500])
print(f"\n已写入 {OUT}")
