# -*- coding: utf-8 -*-
"""gen_jev_full_leg_report.py — R68: 逐腿全景报告
合成: v22 legs(引擎信号链/突破/回踩/子信号/组合) × Jev v2 五问判断
输出:
  research/jev_full_legs.csv                  — 逐腿平铺(全部字段, 可Excel过滤)
  research/handover/R68_jev_full_report.md    — 逐年概览 + 逐月表 + 逐腿明细
"""
import csv, json, os
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
LEGS = os.path.join(ROOT, "combo_v22_trades.csv")
JEV = os.path.join(ROOT, "jev_audit_cache_v2.jsonl")
OUT_CSV = os.path.join(ROOT, "jev_full_legs.csv")
OUT_MD = os.path.join(ROOT, "handover", "R68_jev_full_report.md")


def load():
    legs = {f"{r['symbol']}|{r['entry_date']}|{i}": r
            for i, r in enumerate(csv.DictReader(open(LEGS, encoding="utf-8-sig")))}
    jev = {}
    for ln in open(JEV, encoding="utf-8"):
        j = json.loads(ln)
        jev[j["leg_id"]] = j
    rows = []
    for lid, r in legs.items():
        j = jev.get(lid) or {}
        try:
            chain = json.loads(r.get("chain_json") or "{}")
        except Exception:
            chain = {}
        rows.append({
            "symbol": r["symbol"], "entry_date": r["entry_date"], "src": r["src"],
            "year": r["entry_date"][:4], "month": r["entry_date"][:6],
            # 组合与排序
            "combo": r.get("signal_chain") or "", "sub_signals": (r.get("sub_signals") or "").replace("\n", " "),
            "rank": r.get("rank"), "board": r.get("board"),
            # 价格行为
            "buy_date": r.get("buy_date"), "buy_price": r.get("buy_price"),
            "sell_date": r.get("sell_date"), "sell_price": r.get("sell_price"),
            "net_pnl_pct": r.get("net_pnl_pct"), "hold_bars": r.get("hold_bars"),
            "reason": r.get("reason"),
            "tp": r.get("tp"), "sl": r.get("sl"), "risk_pct": r.get("risk_pct"),
            "mfe_pct": r.get("mfe_pct"), "mae_pct": r.get("mae_pct"), "rr_exit": r.get("rr_exit"),
            # SMC 引擎信号
            "trend_state": r.get("trend_state"),
            "breakout_date": r.get("breakout_date"), "breakout_price": r.get("breakout_price"),
            "breakout_kind": r.get("breakout_kind"),
            "retrace_price": r.get("retrace_price"), "retrace_state": r.get("retrace_state"),
            "retrace_signal": r.get("retrace_signal"),
            "stage_span": r.get("stage_span"), "adx_span": r.get("adx_span"),
            "last_event_kind": r.get("last_event_kind"), "last_event_date": r.get("last_event_date"),
            "events_tail": json.dumps((chain.get("events_tail") or [])[-3:], ensure_ascii=False),
            # Jev v2 判断(无前视)
            "j_p_valid": j.get("p_valid"), "j_trend": j.get("trend"),
            "j_trend_conf": j.get("trend_conf"),
            "j_timing": j.get("timing"), "j_timing_conf": j.get("timing_conf"),
            "j_tpsl": j.get("tpsl"), "j_tpsl_conf": j.get("tpsl_conf"),
            "j_direction": j.get("direction"), "j_direction_conf": j.get("direction_conf"),
        })
    rows.sort(key=lambda x: (x["year"], x["month"], x["entry_date"], x["symbol"]))
    return rows


def f(x, n=2):
    try:
        return f"{float(x):.{n}f}"
    except (TypeError, ValueError):
        return str(x if x is not None else "-")


def stat(rows):
    n = len(rows)
    if not n:
        return 0, 0, 0, 0
    pnl = [float(r["net_pnl_pct"] or 0) for r in rows]
    avg = sum(pnl) / n
    wr = sum(1 for v in pnl if v > 0) / n * 100
    pos = sum(v for v in pnl if v > 0)
    neg = -sum(v for v in pnl if v < 0)
    return n, round(avg, 2), round(wr, 1), round(pos / neg, 2) if neg else float("inf")


def main():
    rows = load()
    cols = list(rows[0].keys())
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    md = ["# R68 — 逐腿全景报告(v22 冻结 1858 腿 × Jev v2 无前视判断)\n"]
    md.append("| 每腿含 | 引擎信号链顺序/组合/子信号 + 趋势 + 突破(日期/价/型) + 回踩(价/状态/触发) + TP/SL/risk + mfe/mae | Jev五问(信号真伪p/趋势/时机/TP-SL判型/方向) |")
    md.append("|---|---|\n")

    for y in sorted({r['year'] for r in rows}):
        yr = [r for r in rows if r["year"] == y]
        n, av, wr, pf = stat(yr)
        md.append(f"\n# {y} — n={n} avg={av}% WR={wr}% PF={pf}\n")
        by_m = defaultdict(list)
        for r in yr:
            by_m[r["month"]].append(r)
        for m in sorted(by_m):
            mr = by_m[m]
            n2, av2, wr2, pf2 = stat(mr)
            md.append(f"\n## {m}(n={n2} avg={av2}% WR={wr2}% PF={pf2})\n")
            md.append("|腿|日期|代码|src|组合|趋势|突破(日/价/型)|回踩(价/状态)|买入→卖出|pnl%|持有|出场|Jev: 信号p/趋势/时机/tpsl/方向|")
            md.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
            for r in mr:
                jv = (f"p={f(r['j_p_valid'])} trend={r['j_trend'] or '-'}({f(r['j_trend_conf'])}) "
                      f"timing={f(r['j_timing'])} tpsl={r['j_tpsl'] or '-'} "
                      f"dir={r['j_direction'] or '-'}({f(r['j_direction_conf'])})")
                md.append(
                    f"|{m}/{r['symbol']}|{r['entry_date']}|{r['symbol']}|{r['src']}"
                    f"|{(r['combo'] or '')[:40]}|{r['trend_state']}"
                    f"|{r['breakout_date'] or '-'}/{f(r['breakout_price'])}/{r['breakout_kind'] or '-'}"
                    f"|{f(r['retrace_price'])}/{r['retrace_state'] or '-'}"
                    f"|{r['buy_date']} {f(r['buy_price'])}→{r['sell_date']} {f(r['sell_price'])}"
                    f"|{f(r['net_pnl_pct'])}|{r['hold_bars']}|{r['reason'] or '-'}"
                    f"|{jv}|")
            md.append("")
    md.append("\n---\n生成: gen_jev_full_leg_report.py | 数据源: combo_v22_trades.csv × jev_audit_cache_v2.jsonl\n")

    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md))
    print(f"CSV {len(rows)}条 → {OUT_CSV}")
    sz = os.path.getsize(OUT_MD)
    print(f"MD → {OUT_MD} ({sz//1024}KB)")


if __name__ == "__main__":
    main()
