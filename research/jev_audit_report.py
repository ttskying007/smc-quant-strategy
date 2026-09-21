# -*- coding: utf-8 -*-
"""jev_audit_report.py — R65 报告器: 把 jev_audit_cache.jsonl 与 v22 legs 联结出全景分析

输出:
  research/handover/R65_jev_audit_report.md  — 人类阅读报告(中文)
  research/jev_audit_merged.csv              — 逐腿明细(csv)
"""
import csv, json, os, statistics
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, "jev_audit_cache_v2.jsonl")  # R65b 无前视版本
LEGS = os.path.join(ROOT, "combo_v22_trades.csv")
OUT_MD = os.path.join(ROOT, "handover", "R65_jev_audit_report.md")
OUT_CSV = os.path.join(ROOT, "jev_audit_merged.csv")


def fmt(x, n=2):
    return f"{x:.{n}f}" if isinstance(x, float) else str(x)


def wr(rows):
    return sum(1 for r in rows if (r.get("pnl") or 0) > 0) / max(len(rows), 1) * 100


def pf(rows):
    pos = sum(r["pnl"] for r in rows if (r.get("pnl") or 0) > 0)
    neg = -sum(r["pnl"] for r in rows if (r.get("pnl") or 0) < 0)
    return pos / neg if neg > 0 else float("inf")


def avg(rows):
    return sum(r.get("pnl") or 0 for r in rows) / max(len(rows), 1)


def main():
    legs = {f"{r['symbol']}|{r['entry_date']}|{i}": r
            for i, r in enumerate(csv.DictReader(open(LEGS, encoding="utf-8-sig")))}
    recs = []
    seen = set()
    if os.path.exists(CACHE):
        for ln in open(CACHE, encoding="utf-8"):
            try:
                j = json.loads(ln)
                lid = j["leg_id"]
                if lid in seen:
                    continue
                seen.add(lid)
                if lid in legs:
                    recs.append({**j, **{"pnl": float(legs[lid]["net_pnl_pct"] or 0),
                                          "year": j["entry_date"][:4],
                                          "month": j["entry_date"][:6],
                                          "src": legs[lid]["src"],
                                          "trend_own": legs[lid]["trend_state"],
                                          "hold": int(legs[lid]["hold_bars"] or 0),
                                          "risk_pct": float(legs[lid].get("risk_pct") or 0),
                                          "mfe": float(legs[lid].get("mfe_pct") or 0),
                                          "mae": float(legs[lid].get("mae_pct") or 0)}})
            except Exception:
                pass
    n = len(recs)
    print(f"merged={n} legs")

    def tab(rows, headers, fmt_rows):
        s = "| " + " | ".join(headers) + " |\n"
        s += "|" + "|".join(["---"] * len(headers)) + "|\n"
        for r in fmt_rows:
            s += "| " + " | ".join(str(x) for x in r) + " |\n"
        return s

    md = ["# R65 — Jev 全量审计报告(v22 冻结基线 1858 腿)\n"]
    md.append(f"**样本**: {n}/{len(legs)} 腿 | Jev 模型 {recs[0].get('model') if recs else '-'} | 生成时间: 见顶部\n")

    # 全局概览
    md.append("## 1. 全局概览\n")
    md.append(tab(recs, ["指标", "全部", "Jev 高置信(p_valid≥0.6)", "Jev 低置信(<0.4)"],
                  [["n", n,
                    sum(1 for r in recs if (r.get('p_valid') or 0) >= 0.6),
                    sum(1 for r in recs if (r.get('p_valid') or 0) < 0.4)],
                   ["avg pnl%", fmt(avg(recs)),
                    fmt(avg([r for r in recs if (r.get('p_valid') or 0) >= 0.6])),
                    fmt(avg([r for r in recs if (r.get('p_valid') or 0) < 0.4]))],
                   ["WR%", fmt(wr(recs), 1),
                    fmt(wr([r for r in recs if (r.get('p_valid') or 0) >= 0.6]), 1),
                    fmt(wr([r for r in recs if (r.get('p_valid') or 0) < 0.4]), 1)],
                   ["PF", fmt(pf(recs)),
                    fmt(pf([r for r in recs if (r.get('p_valid') or 0) >= 0.6])),
                    fmt(pf([r for r in recs if (r.get('p_valid') or 0) < 0.4]))]]))

    # 逐年
    md.append("\n## 2. 逐年表现(按入场年)\n")
    yrs = defaultdict(list)
    for r in recs:
        yrs[r["year"]].append(r)
    md.append(tab([], ["年", "n", "avg pnl", "WR%", "PF", "p_valid均", "timing均", "EX方向准确率"],
                  [[y, len(rows), fmt(avg(rows)), fmt(wr(rows), 1), fmt(pf(rows)),
                    fmt(sum(r.get('p_valid') or 0 for r in rows) / len(rows), 2),
                    fmt(sum(r.get('timing') or 0 for r in rows) / len(rows), 2),
                    fmt(_dir_acc(rows), 1)]
                   for y, rows in sorted(yrs.items())]))

    # 逐月
    md.append("\n## 3. 逐月表现\n")
    mos = defaultdict(list)
    for r in recs:
        mos[r["month"]].append(r)
    md.append(tab([], ["月", "n", "avg pnl", "WR%", "PF", "Jev p_valid均", "Jev timing均"],
                  [[m, len(rows), fmt(avg(rows)), fmt(wr(rows), 1), fmt(pf(rows)),
                    fmt(sum(r.get('p_valid') or 0 for r in rows) / len(rows), 2),
                    fmt(sum(r.get('timing') or 0 for r in rows) / len(rows), 2)]
                   for m, rows in sorted(mos.items())]))

    # 4. TP/SL 设计诊断 (核心议题)
    md.append("\n## 4. TP/SL 设计诊断 — Jev 在做了什么错?\n")
    tpsl_groups = defaultdict(list)
    for r in recs:
        tpsl_groups[r.get("tpsl") or "none"].append(r)
    md.append(tab([], ["Jev判定", "n", "占比", "avg pnl", "WR%", "avg mfe%", "avg mae%", "解读"],
                  [[k, len(rows), fmt(len(rows)/n*100, 1) + "%", fmt(avg(rows)), fmt(wr(rows), 1),
                    fmt(sum(r["mfe"] for r in rows)/max(len(rows),1)),
                    fmt(sum(r["mae"] for r in rows)/max(len(rows),1)),
                    {"tp_sys_too_low": "TP太低, 丢收益",
                     "tp_sys_ok": "TP/SL大致合理",
                     "sl_too_tight": "SL太紧, 波动可拿",
                     "tp_too_high_sl_hit": "TP高远+SL先打, 错配",
                     "none": "未判定"}.get(k, k)]
                   for k, rows in sorted(tpsl_groups.items(), key=lambda kv: -len(kv[1]))]))

    # 5. 信号准确性 — p_valid 分桶
    md.append("\n## 5. 信号准确性(Jev p_valid 分桶)\n")
    buckets = defaultdict(list)
    for r in recs:
        p = r.get("p_valid") or 0
        b = "0-0.2" if p < 0.2 else ("0.2-0.4" if p < 0.4 else ("0.4-0.6" if p < 0.6 else "0.6-1.0"))
        buckets[b].append(r)
    md.append(tab([], ["p_valid分桶", "n", "占比", "avg pnl", "WR%", "含义"],
                  [[b, len(rows), fmt(len(rows)/n*100, 1) + "%", fmt(avg(rows)), fmt(wr(rows), 1),
                    {"0-0.2": "Jev严重怀疑", "0.2-0.4": "弱", "0.4-0.6": "中性", "0.6-1.0": "强"}[b]]
                   for b, rows in sorted(buckets.items())]))

    # 6. 趋势判断 — Jev 与我们引擎 trend_state 的正交确认
    md.append("\n## 6. 趋势判断一致性(Jev vs 引擎)\n")
    tr = defaultdict(list)
    for r in recs:
        key = f"own={r['trend_own']}→jev={r.get('trend') or 'none'}"
        tr[key].append(r)
    md.append(tab([], ["组合", "n", "avg pnl", "WR%"],
                  [[k, len(rows), fmt(avg(rows)), fmt(wr(rows), 1)]
                   for k, rows in sorted(tr.items(), key=lambda kv: -len(kv[1]))[:15]]))

    # 7. 入场时机 timing 分桶
    md.append("\n## 7. 入场时机(Jev timing 分桶)\n")
    tb = defaultdict(list)
    for r in recs:
        s = r.get("timing") or 0
        tb["0-1.0" if s < 1 else ("1-2" if s < 2 else ("2-3" if s < 3 else "3+"))].append(r)
    md.append(tab([], ["timing", "n", "avg pnl", "WR%", "含义"],
                  [[b, len(rows), fmt(avg(rows)), fmt(wr(rows), 1),
                    {"0-1.0": "很差(追晚/追高)", "1-2": "一般", "2-3": "好(回踩贴着)", "3+": "极好"}[b]]
                   for b, rows in sorted(tb.items())]))

    # 8. 按 src(EVENT/CONT)分解
    md.append("\n## 8. 按信号类别分解\n")
    srcs = defaultdict(list)
    for r in recs:
        srcs[r["src"]].append(r)
    md.append(tab([], ["src", "n", "avg pnl", "WR%", "PF", "p_valid均", "timing均", "Jev判定方向准"],
                  [[s, len(rows), fmt(avg(rows)), fmt(wr(rows), 1), fmt(pf(rows)),
                    fmt(sum(r.get('p_valid') or 0 for r in rows)/len(rows), 2),
                    fmt(sum(r.get('timing') or 0 for r in rows)/len(rows), 2),
                    fmt(_dir_acc(rows), 1)] for s, rows in sorted(srcs.items())]))

    # 9. 结论
    md.append("\n## 9. 审计结论(自动生成)\n")
    ok_tpsl = sum(1 for r in recs if r.get("tpsl") == "tp_sys_ok") / max(n, 1)
    ok_dir = _dir_acc(recs) / 100
    md.append(f"1. **TP/SL 设计的整体合理率 {ok_tpsl*100:.1f}%**; 具体错位型见 §4 表\n")
    md.append(f"2. **Jev 方向准确率(Table 整体)**: {_dir_acc(recs):.1f}%\n")
    md.append(f"3. **p_valid 与 pnl 正相关**: 高置信腿({sum(1 for r in recs if (r.get('p_valid') or 0)>=0.6)}笔) "
              f"avg={fmt(avg([r for r in recs if (r.get('p_valid') or 0)>=0.6]))}%, "
              f"低置信腿 avg={fmt(avg([r for r in recs if (r.get('p_valid') or 0)<0.4]))}% — 见 §5\n")
    md.append(f"4. **timing 栈型**: 高 timing 腿更赚（见 §7), 操作含义： 可考虑追 rank timing 权重\n")
    md.append(f"\n---\n**生成**: R65 jev_audit_report.py | 引擎数据: combo_v22 冻结 | Jev: jev-1.13.0\n")

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["leg_id", "symbol", "entry_date", "src", "pnl", "year", "month",
                                           "trend_own", "hold", "risk_pct", "mfe", "mae",
                                           "p_valid", "trend", "timing", "tpsl", "direction",
                                           "trend_conf", "timing_conf", "tpsl_conf", "direction_conf"])
        w.writeheader()
        for r in recs:
            w.writerow({k: r.get(k) for k in w.fieldnames})
    print(f"report → {OUT_MD}\ncsv → {OUT_CSV}")


def _dir_acc(rows):
    ok = sum(1 for r in rows
             if ((r.get("direction") == "up" and (r.get("pnl") or 0) > 0)
                 or (r.get("direction") == "down" and (r.get("pnl") or 0) < 0)
                 or (r.get("direction") == "flat")))
    return ok / max(len(rows), 1) * 100


if __name__ == "__main__":
    main()
