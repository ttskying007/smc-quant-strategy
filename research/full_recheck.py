# -*- coding: utf-8 -*-
"""全量回测深度复检（第七轮P2）：逐年/逐月/逐笔 + 问题清单
数据源: handover/最新回测数据/逐笔交易全明细.json（修复 ep<sl bug 后重生成）
检查面：
  ① 总体/分腿/IS-OOS
  ② 逐年逐月（含 WR/PF/集中度）
  ③ 逐笔异常：T+1 违规 / TP>buy>SL 非法 / 尾部极端 / 字段完整性
  ④ 问题清单输出（供下一轮修复）
"""
import io, json, os, sys
from collections import Counter, defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SRC = r"E:\test\smc_project\research\handover\最新回测数据\逐笔交易全明细.json"
OUT = r"E:\test\smc_project\research\handover\全量回测复检报告.json"
trades = json.load(open(SRC, encoding="utf-8")).get("trades") or []
print(f"总交易: {len(trades)} | 生成于: {json.load(open(SRC, encoding='utf-8')).get('generated_at')}")


def stats(pn):
    pn = [x for x in pn if x is not None]
    if not pn:
        return {"n": 0, "avg": 0, "wr": 0, "pf": 0}
    wins = [x for x in pn if x > 0]
    losses = [x for x in pn if x <= 0]
    return {"n": len(pn), "avg": round(sum(pn) / len(pn), 3),
            "wr": round(len(wins) / len(pn), 3),
            "pf": round(sum(wins) / abs(sum(losses)), 2) if losses and sum(losses) != 0 else 99.0}


OOS = "20250701"
rep = {"asof": __import__("time").strftime("%Y-%m-%d %H:%M:%S"), "oos_from": OOS}

# ① 总体/分腿
print("\n== ① 总体 ==")
rep["overall"] = {}
for leg in ("SMC", "EVENT"):
    ts = [t for t in trades if t.get("leg") == leg]
    pn = [t.get("net_pnl_pct") for t in ts if t.get("net_pnl_pct") is not None]
    s = stats(pn)
    s_is = stats([t.get("net_pnl_pct") for t in ts if t.get("net_pnl_pct") is not None and t["entry_date"] < OOS])
    s_oos = stats([t.get("net_pnl_pct") for t in ts if t.get("net_pnl_pct") is not None and t["entry_date"] >= OOS])
    rep["overall"][leg] = {"all": s, "is": s_is, "oos": s_oos}
    print(f"  {leg}: 全部 {s} | IS {s_is['n']}笔 avg{s_is['avg']}% | OOS {s_oos['n']}笔 avg{s_oos['avg']}% PF{s_oos['pf']}")

# ② 逐年逐月
print("\n== ② 逐年 ==")
rep["yearly"] = {}
for y in sorted({t["entry_date"][:4] for t in trades}):
    row = {}
    for leg in ("SMC", "EVENT"):
        pn = [t.get("net_pnl_pct") for t in trades if t.get("leg") == leg and t["entry_date"][:4] == y
              and t.get("net_pnl_pct") is not None]
        row[leg] = stats(pn)
    rep["yearly"][y] = row
    print(f"  {y}: SMC {row['SMC']['n']}笔 avg{row['SMC']['avg']:+.2f}% | EVENT {row['EVENT']['n']}笔 avg{row['EVENT']['avg']:+.2f}% PF{row['EVENT']['pf']}")

print("\n== ② 逐月（EVENT 腿，最近 18 个月）==")
rep["monthly_event"] = {}
months = sorted({t["entry_date"][:6] for t in trades if t.get("leg") == "EVENT"})
for m in months[-18:]:
    pn = [t.get("net_pnl_pct") for t in trades if t.get("leg") == "EVENT" and t["entry_date"][:6] == m
          and t.get("net_pnl_pct") is not None]
    s = stats(pn)
    rep["monthly_event"][m] = s
    flag = " ⚠负月" if s["avg"] < 0 else ""
    print(f"  {m}: {s['n']}笔 avg{s['avg']:+.2f}% wr{s['wr']*100:.0f}% PF{s['pf']}{flag}")

# ③ 逐笔异常检查
print("\n== ③ 逐笔异常 ==")
issues = []
n_t1_violation = n_tp_sl_illegal = n_tail = n_field_missing = 0
n_ev_t1 = n_ev_tpsl = n_ev_hold0 = 0
for t in trades:
    # T+1: sell_date 必须 > buy_date（买入当日不可卖）
    bd, sd = str(t.get("buy_date") or ""), str(t.get("sell_date") or "")
    if bd and sd and sd <= bd and bd != "None":
        n_t1_violation += 1
        if len(issues) < 30:
            issues.append({"type": "T1_VIOLATION", "t": t})
    # TP > buy > SL（SMC 腿有完整字段）
    bp, tp, sl = t.get("buy_price"), t.get("tp"), t.get("sl")
    if isinstance(bp, (int, float)) and isinstance(tp, (int, float)) and isinstance(sl, (int, float)) and bp and tp and sl:
        if not (tp > bp > sl):
            n_tp_sl_illegal += 1
            if len(issues) < 30:
                issues.append({"type": "TP_SL_ILLEGAL", "t": t})
    # 尾部极端（疑似退市/连续跌停）
    if isinstance(t.get("net_pnl_pct"), (int, float)) and t["net_pnl_pct"] is not None and t["net_pnl_pct"] < -50:
        n_tail += 1
        if len(issues) < 30:
            issues.append({"type": "TAIL_EXTREME", "pnl": t["net_pnl_pct"], "t": t})
    # 事件腿字段完整性（P8-2 逐笔重放后）
    if t.get("leg") == "EVENT":
        if not t.get("buy_price") or not t.get("tp") or not t.get("sl"):
            n_field_missing += 1
        if not t.get("sell_date") or not t.get("sell_price"):
            n_ev_t1 += 1  # 未平仓/持有至期末
        elif t["sell_date"] <= t["buy_date"]:
            n_ev_t1 += 1
        if isinstance(t.get("tp"), (int, float)) and isinstance(t.get("sl"), (int, float)) \
                and isinstance(t.get("buy_price"), (int, float)) and t["tp"] and t["sl"] and t["buy_price"]:
            if not (t["tp"] > t["buy_price"] > t["sl"]):
                n_ev_tpsl += 1

print(f"  T+1 违规(sell<=buy): {n_t1_violation}")
print(f"  TP>buy>SL 非法: {n_tp_sl_illegal}")
print(f"  尾部极端(<-50%): {n_tail}")
print(f"  EVENT 腿缺 buy/tp/sl: {n_field_missing} | EVENT 卖出日期违规/未平仓: {n_ev_t1} | EVENT TP>buy>SL非法: {n_ev_tpsl}")

# 事件腿重放口径缺失检查 —— combo_v20f_trades.csv 只有净收益，无逐笔明细
rep["anomalies"] = {"t1_violation": n_t1_violation, "tp_sl_illegal": n_tp_sl_illegal,
                   "tail_extreme": n_tail, "event_missing_prices": n_field_missing,
                   "event_sell_issues": n_ev_t1, "event_tpsl_illegal": n_ev_tpsl,
                   "samples": issues[:30]}

# ④ 集中度（HHI 按月）
print("\n== ④ 集中度 ==")
by_month_n = Counter(t["entry_date"][:6] for t in trades if t.get("leg") == "EVENT")
total_ev = sum(by_month_n.values())
hhi = sum((v / total_ev) ** 2 for v in by_month_n.values()) * 10000
max_m, max_n = by_month_n.most_common(1)[0]
rep["concentration"] = {"hhi": round(hhi, 1), "max_month": max_m, "max_month_n": max_n,
                        "max_month_share": round(max_n / total_ev * 100, 1)}
print(f"  EVENT 月度 HHI: {hhi:.1f}（<100 分散）| 最大月 {max_m}: {max_n}笔 ({max_n/total_ev*100:.1f}%)")

# ⑤ 问题清单
print("\n== ⑤ 问题清单（本轮发现）==")
# P1 门禁复检结果
try:
    gate = json.load(open(r"E:\test\smc_project\research\handover\事件腿P1门禁复检.json", encoding="utf-8"))
    _g = gate.get("gate", {})
    _gs = "✅PASS" if _g.get("PASS") else "❌FAIL"
    print(f"\n  [P1门禁复检] {_gs}: 全样本avg{gate['full']['avg']}% PF{gate['full']['pf']} | "
          f"bootstrap[{(gate['bootstrap10x80']['avg_min']*100):.2f},{(gate['bootstrap10x80']['avg_max']*100):.2f}]% | "
          f"OOS avg{gate['oos']['avg']}% PF{gate['oos']['pf']} | 去重后 avg{gate['dedup5d']['avg']}% PF{gate['dedup5d']['pf']}")
except Exception as _e:
    print(f"\n  [P1门禁复检] 无法读取: {_e}")

problems = [
    {"id": "P8-1", "severity": "CRITICAL",
     "title": "旧事件腿回测含 ep<sl1 机械获利 bug（已修复，历史基准全部下修）",
     "detail": "旧 gen_v20f 内联退出循环对 entry_price < sl（区间几何非法）的交易在首根K线以高于入场价的 stop 获利退出 —— 无论行情必赢。2024 年 1478/2846=52% 笔为此类。修复后 EVENT 真实基准: avg+1.01%/WR31%/PF1.96（原虚高 avg+10%/PF14）。",
     "impact": "事件腿 P1 门禁的历史数字(PF7.9/avg+7.07/bootstrap CI[7.13,8.76])基于带bug数据 —— 已用修正后数据重跑门禁。",
     "fix_status": "已修复(simulate BAD_ENTRY)；门禁已复检见下"},
    {"id": "P8-2", "severity": "HIGH",
     "title": "事件腿逐笔回测缺 buy/sell/hold 明细",
     "detail": "combo_v20f_trades.csv 只存净收益；gen_full_backtest_data 的 EVENT 腿没有逐笔重放K线（无 buy_price/sell_date/hold_bars/MFE/MAE）。",
     "impact": "逐笔审计/字段级验证(verify_ledger_fields)对 EVENT 腿无法执行；TP/SL 触发时间不可追溯。",
     "fix_status": "待办: gen_full_backtest_data 事件腿改逐笔重放(simulate)"},
    {"id": "P8-3", "severity": "MEDIUM",
     "title": "过滤口径曾存在两套平行实现（已统一）",
     "detail": "gen_v20f.is_strong 与 core.events.classify_title 语义不同（旧 is_strong 放行 5471 条行政性'回购价格调整/律师公告'标题）。统一后 2024 新口径 avg+11.95%（旧退出）—— 本身也是 ep<sl bug 受益者。",
     "impact": "历史研究报告（v20e/v20f 系列）的过滤口径与生产不一致，数字不可直接对比。",
     "fix_status": "已统一(classify_title)；历史报告标注待办"},
    {"id": "P8-4", "severity": "INFO",
     "title": "A/B 验证结论在修复后依然成立（PROGRESS_WITH_DELTA 维持放开）",
     "detail": "修复语义后重测: 增量 281 笔 OOS +4.58%/WR72.7%/PF5.29，三预注册线再过。放开维持有效。",
     "impact": "无（确认性）", "fix_status": "已复验"},
    {"id": "P8-5", "severity": "MEDIUM",
     "title": "事件家族 5 日内重复率 9.9%（过度交易隐患）",
     "detail": "3183 事件中 314 个与同股 5 日内重复（同一公司连发多公告均触发）。去重后 n=2888 avg+0.92%/PF1.85（vs 原 avg+1.01%/PF1.96）。",
     "impact": "逐笔净收益被重复事件轻微高估；单股仓位集中风险。",
     "fix_status": "待办: daily_selection 考虑同股N日冷却/合并（需A/B验证）"},
]
rep["problems"] = problems
for p in problems:
    print(f"  [{p['severity']}] {p['id']}: {p['title']}")
    print(f"      影响: {p['impact'][:88]}")
    print(f"      状态: {p['fix_status']}")

with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(rep, fh, ensure_ascii=False, indent=2)
print(f"\n已写 {OUT}")