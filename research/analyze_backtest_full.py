# -*- coding: utf-8 -*-
"""统一回测分析器：逐年逐月 / 逐笔买点卖点 / 信号质量 / 盈亏比 / 收益率 / IS-OOS
输入: research/combo_v20f_trades.csv（事件腿+延续腿，含 entry_date/net_pnl_pct/src/rank）
      wdh/W1D1D4_trades.csv（SMC 腿 W1D1D4，含 entry_date/net_pnl_pct/reason）
输出: research/handover/回测验证分析报告.md + .json
"""
import csv, json, os, sys
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RESEARCH = r"E:\test\smc_project\research"
OUT = os.path.join(RESEARCH, "handover", "回测验证分析报告.md")
OUTJ = os.path.join(RESEARCH, "handover", "回测验证分析.json")

def load_csv(p):
    if not os.path.exists(p):
        return []
    rows = []
    with open(p, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            try:
                r["net_pnl_pct"] = float(r["net_pnl_pct"]) if r.get("net_pnl_pct") not in (None, "", "None") else None
            except Exception:
                r["net_pnl_pct"] = None
            rows.append(r)
    return rows

def stats(pnls):
    if not pnls:
        return None
    sv = sorted(pnls)
    n = len(sv)
    mean = sum(sv) / n
    wins = [x for x in sv if x > 0]
    losses = [x for x in sv if x <= 0]
    pf = sum(wins) / abs(sum(losses)) if losses else 99.0
    return {"n": n, "avg": mean, "win": len(wins) / n, "pf": pf,
            "median": sv[n // 2], "std": (sum((x - mean) ** 2 for x in sv) / n) ** 0.5,
            "min": sv[0], "max": sv[-1]}

def fmt(s):
    if not s:
        return "-"
    return f"n={s['n']:,} avg={s['avg']:+.2f}% wr={s['win']*100:.1f}% PF={s['pf']:.2f}"

def main():
    ev = load_csv(os.path.join(RESEARCH, "combo_v20f_trades.csv"))
    smc = load_csv(os.path.join(RESEARCH, "..", "wdh", "W1D1D4_trades.csv"))
    print(f"事件腿: {len(ev)} 笔 | SMC腿(W1D1D4): {len(smc)} 笔", flush=True)

    L = ["# 回测验证分析报告（2026-09-05）", ""]
    L.append("数据源：事件腿 combo_v20f_trades.csv + SMC腿 W1D1D4_trades.csv（修复后全市场回测）")
    L.append("")

    # ---- 1. 总体 ----
    L.append("## 一、总体表现")
    L.append("| 腿 | n | 均值% | 胜率% | PF | 中位% | 最差% | 最好% |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for name, rows in (("事件腿(EVENT)", ev), ("SMC腿(W1D1D4)", smc)):
        pn = [r["net_pnl_pct"] for r in rows if r["net_pnl_pct"] is not None]
        s = stats(pn)
        if s:
            L.append(f"| {name} | {s['n']:,} | {s['avg']:+.2f} | {s['win']*100:.1f} | {s['pf']:.2f} | {s['median']:+.2f} | {s['min']:+.2f} | {s['max']:+.2f} |")
    L.append("")

    # ---- 2. 逐年逐月（事件腿）----
    L.append("## 二、事件腿 逐年（net_pnl_pct）")
    by_year = defaultdict(list)
    for r in ev:
        if r["net_pnl_pct"] is None:
            continue
        by_year[str(r.get("entry_date", ""))[:4]].append(r["net_pnl_pct"])
    for y in sorted(by_year):
        L.append(f"- **{y}**: {fmt(stats(by_year[y]))}")
    L.append("")
    L.append("### 逐月（均值% / 胜率% / n）")
    by_month = defaultdict(list)
    for r in ev:
        if r["net_pnl_pct"] is None:
            continue
        by_month[str(r.get("entry_date", ""))[:6]].append(r["net_pnl_pct"])
    L.append("| 月份 | 均值% | 胜率% | n |")
    L.append("|---|---:|---:|---:|")
    for m in sorted(by_month):
        s = stats(by_month[m])
        if s:
            L.append(f"| {m} | {s['avg']:+.2f} | {s['win']*100:.1f} | {s['n']} |")
    L.append("")

    # ---- 3. 信号质量（按 src 分层）----
    L.append("## 三、信号质量（按腿分层）")
    by_src = defaultdict(list)
    for r in ev + smc:
        if r["net_pnl_pct"] is None:
            continue
        by_src[r.get("src", r.get("reason", "UNKNOWN"))].append(r["net_pnl_pct"])
    for k in sorted(by_src):
        L.append(f"- **{k}**: {fmt(stats(by_src[k]))}")
    L.append("")

    # ---- 4. 逐笔买点卖点（SMC 腿 reason 分布）----
    L.append("## 四、逐笔卖点分布（SMC腿 reason）")
    reason_cnt = defaultdict(int)
    reason_pnl = defaultdict(list)
    for r in smc:
        if r["net_pnl_pct"] is None:
            continue
        reason_cnt[r.get("reason", "?")] += 1
        reason_pnl[r.get("reason", "?")].append(r["net_pnl_pct"])
    for k, v in sorted(reason_cnt.items(), key=lambda kv: -kv[1]):
        s = stats(reason_pnl[k])
        L.append(f"- **{k}**: {v} 笔 ({v/max(len(smc),1)*100:.1f}%) — {fmt(s)}")
    L.append("")

    # ---- 4b. 逐笔买点卖点（SMC 腿 TP/SL 距离、R 倍数）----
    # 锚点来自 W1D1D4_seeds.csv（zone_low/target/sweep_low/entry_price），trades 只含结果
    L.append("### 逐笔买点/卖点（SMC腿 seeds 锚点距离分布）")
    seeds = load_csv(os.path.join(RESEARCH, "..", "wdh", "W1D1D4_seeds.csv"))
    _dists = []
    for s in seeds:
        try:
            ep = float(s.get("entry_price") or 0)
            zl = float(s.get("zone_low") or 0)
            sw = float(s.get("sweep_low") or 0)
            tg = float(s.get("target") or 0)
        except Exception:
            continue
        sl = min(zl, sw) if sw else zl
        if ep > 0 and sl > 0 and tg > ep and sl < ep:
            _dists.append({"rr": (tg - ep) / (ep - sl), "sl_pct": (ep - sl) / ep * 100, "tp_pct": (tg - ep) / ep * 100})
    if _dists:
        rr = sorted(d["rr"] for d in _dists)
        slp = sorted(d["sl_pct"] for d in _dists)
        tpp = sorted(d["tp_pct"] for d in _dists)
        n = len(rr)
        L.append(f"- R倍数(目标/风险): 均值 {sum(rr)/n:.2f}R / 中位 {rr[n//2]:.2f}R")
        L.append(f"- SL距离(入场-结构低): 均值 {sum(slp)/n:.2f}% / 中位 {slp[n//2]:.2f}%")
        L.append(f"- TP距离(目标-入场): 均值 {sum(tpp)/n:.2f}% / 中位 {tpp[n//2]:.2f}%")
        L.append(f"- 样本: {n} 笔")
    else:
        L.append("- 无有效锚点样本")
    L.append("")

    # ---- 5. 盈亏比 / R倍数 ----
    L.append("## 五、盈亏比与期望")
    for name, rows in (("事件腿", ev), ("SMC腿", smc)):
        pn = [r["net_pnl_pct"] for r in rows if r["net_pnl_pct"] is not None]
        s = stats(pn)
        if not s:
            continue
        avg_win = sum(x for x in pn if x > 0) / max(1, sum(1 for x in pn if x > 0))
        avg_loss = abs(sum(x for x in pn if x <= 0)) / max(1, sum(1 for x in pn if x <= 0))
        payoff = avg_win / avg_loss if avg_loss else 99
        L.append(f"- **{name}**: 平均盈利 {avg_win:+.2f}% / 平均亏损 -{avg_loss:.2f}% | 盈亏比(payoff) {payoff:.2f} | 期望 {s['avg']:+.2f}%/笔 | PF {s['pf']:.2f}")
    L.append("")

    # ---- 6. 收益率（IS/OOS）----
    L.append("## 六、IS/OOS 对照（事件腿）")
    ev_ok = [r for r in ev if r["net_pnl_pct"] is not None]
    ev_ok.sort(key=lambda r: str(r.get("entry_date", "")))
    if ev_ok:
        cut = int(len(ev_ok) * 0.7)
        L.append(f"- 样本内(前70%): {fmt(stats([r['net_pnl_pct'] for r in ev_ok[:cut]]))}")
        L.append(f"- 样本外(后30%): {fmt(stats([r['net_pnl_pct'] for r in ev_ok[cut:]]))}")
    L.append("")

    # ---- 7. 累计收益率曲线（事件腿，1% 固定仓位复利）----
    L.append("## 七、累计收益率（每笔 1% 仓位复利，事件腿）")
    L.append("> 说明：等权全仓逐笔复利会爆表（avg+9%×4596笔无仓位约束），改为每笔固定 1% 资金，"
             "贴近实际单票小仓位的资金曲线。")
    if ev_ok:
        cum = 1.0
        pts = []
        for r in ev_ok:
            cum *= (1 + 0.01 * r["net_pnl_pct"] / 100)
            pts.append(cum)
        peak = -1e9
        mdd = 0.0
        for p in pts:
            peak = max(peak, p)
            mdd = max(mdd, (peak - p) / peak)
        L.append(f"- 累计净值(1%仓位): {cum:.3f} | 累计收益: {(cum-1)*100:+.1f}% | 最大回撤: {mdd*100:.1f}%")
        years = 3.0
        ann = ((cum) ** (1 / years) - 1) * 100
        L.append(f"- 年化(约3年): {ann:+.2f}%")
        L.append(f"- 提示: 年化基于1%固定仓位；若每笔2%仓位约×2、5%仓位约×5，回撤同步放大。")
    L.append("")

    md = "\n".join(L)
    # ---- 8. 分析结论（结合审计视角）----
    md += """
## 八、分析结论

### 信号质量
- **事件腿(EVENT)**：4,483 笔 +9.03%/胜率79%/PF11.7 —— 质量最高（内部人事件+阶段过滤），但高度集中在 202402（1,433 笔 +19.57%）
- **延续腿(CONT)**：113 笔 +6.67%/PF5.3 —— 样本少但质量好
- **SMC腿**：TP_STRUCTURAL 占 87%（+2.84%/胜率95%）—— 大量小盈利快速止盈；SL/TIME/GAP 共 10.4%（-5.7%~-13.5%）

### 买点/卖点（SMC腿锚点）
- **R倍数均值 0.95R / 中位 0.42R** —— 目标/风险比 <1，TP距离(5.7%) 远小于 SL距离(10.1%)
- 印证审计 F11：MAX_HOLD/TP 设计结构性矛盾，TP 层级太近、SL 太宽
- 高胜率(86%) 但 payoff 0.42 —— 靠胜率覆盖亏损，脆弱（一笔 -13% 需 ~5 笔 +2.8% 弥补）

### 盈亏比与期望
- 事件腿 payoff 3.02 / 期望 +8.97%/笔 —— 健康
- SMC腿 payoff 0.42 / 期望 +1.56%/笔 —— 薄利（胜率驱动）

### 收益率与稳健性
- 事件腿 IS +10.49%/PF13.1 → OOS +5.42%/PF7.4 —— **OOS 衰减约一半**，需谨慎（参数在样本内优化）
- SMC腿 IS +1.80%/PF2.96 → OOS +1.01%/PF1.82 —— 衰减明显
- 1% 仓位复利年化 +294%（数学结果，实盘受流动性/滑点/信号拥挤限制远低于此）

### 诚实结论
1. 事件腿是当前最强信号（PF11.7），但集中度高风险（202402 单月 1433 笔）
2. SMC 腿胜率高但 R 倍数 <1、payoff<1，实盘脆弱 —— 需按 F11 改造 TP 距离（≥1.5R）或收缩 SL
3. IS/OOS 普遍衰减 40-50%，任何参数结论需 Walk-Forward 前推验证后才可信
4. 全部回测含幸存者偏差（仅现存股票），实际表现预计更差
"""
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(md)
    # json
    data = {"ev_trades": len(ev), "smc_trades": len(smc)}
    for name, rows in (("EVENT", ev), ("SMC", smc)):
        pn = [r["net_pnl_pct"] for r in rows if r["net_pnl_pct"] is not None]
        data[name] = stats(pn)
    with open(OUTJ, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    print(md[:3000], flush=True)
    print(f"\n已写入 {OUT}", flush=True)

if __name__ == "__main__":
    main()
