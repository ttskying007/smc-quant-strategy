# -*- coding: utf-8 -*-
"""Generate full backtest reports (yearly/monthly/stock/trade-log) for V88/V519/V699,
aligned with the system's SMC_BACKTEST_PERIOD_REPORT_V1 field format.
Output: E:\test\smc_project\smc_backtest_report\
"""
import os, csv, json, collections, datetime

HERMES = r"E:\test\smc_project\hermes"
AUD = os.path.join(HERMES, "smc_audit")
OUT = r"E:\test\smc_project\smc_backtest_report"
os.makedirs(OUT, exist_ok=True)

def empty_stats():
    return {"trade_count": 0, "symbol_count": 0, "win_count": 0, "loss_count": 0,
            "flat_count": 0, "gross_wr_pct": 0.0, "avg_net_pnl_pct": 0.0,
            "total_net_pnl_pct": 0.0, "avg_win_pct": 0.0, "avg_loss_pct": 0.0,
            "payoff_rr": 0.0, "profit_factor": 0.0, "avg_hold_bars": 0.0,
            "t1_violation_count": 0, "exit_counts": {}}

def agg_stats(rows, nkey="net_pnl_pct", exitkey="reason", holdkey="hold_bars", win_ge=0.0):
    s = empty_stats()
    n = len(rows)
    if n == 0:
        return s
    wins = [r for r in rows if float(r[nkey] or 0) > win_ge]
    losses = [r for r in rows if float(r[nkey] or 0) <= win_ge]
    s["trade_count"] = n
    s["symbol_count"] = len({r["symbol"] for r in rows})
    s["win_count"] = len(wins)
    s["loss_count"] = len(losses)
    s["gross_wr_pct"] = round(100.0 * len(wins) / n, 4)
    total = sum(float(r[nkey] or 0) for r in rows)
    s["total_net_pnl_pct"] = round(total, 4)
    s["avg_net_pnl_pct"] = round(total / n, 4)
    aw = sum(float(r[nkey] or 0) for r in wins) / len(wins) if wins else 0.0
    al = sum(float(r[nkey] or 0) for r in losses) / len(losses) if losses else 0.0
    s["avg_win_pct"] = round(aw, 4)
    s["avg_loss_pct"] = round(al, 4)
    s["payoff_rr"] = round(abs(aw / al), 4) if al else 0.0
    gp = sum(max(float(r[nkey] or 0), 0) for r in rows)
    gl = abs(sum(min(float(r[nkey] or 0), 0) for r in rows))
    s["profit_factor"] = round(gp / gl, 4) if gl else 0.0
    s["avg_hold_bars"] = round(sum(float(r[holdkey] or 0) for r in rows) / n, 4)
    s["exit_counts"] = dict(collections.Counter(str(r.get(exitkey) or "?") for r in rows))
    return s

def year_month(rows, nkey="net_pnl_pct", exitkey="reason", holdkey="hold_bars", datekey="entry_date"):
    yearly, monthly = {}, {}
    for r in rows:
        d = str(r.get(datekey) or "")
        if len(d) >= 8:
            y, m = d[:4], d[:6]
        else:
            y, m = "?", "?"
        yearly.setdefault(y, []).append(r)
        monthly.setdefault(m, []).append(r)
    y_out = []
    for y in sorted(yearly):
        s = agg_stats(yearly[y], nkey, exitkey, holdkey)
        s["entry_year"] = y
        y_out.append(s)
    m_out = []
    for m in sorted(monthly):
        s = agg_stats(monthly[m], nkey, exitkey, holdkey)
        s["entry_month"] = m
        m_out.append(s)
    return y_out, m_out

def stock_summary(rows, nkey="net_pnl_pct"):
    by = collections.defaultdict(list)
    for r in rows:
        by[r["symbol"]].append(r)
    out = []
    for sym, rs in by.items():
        st = agg_stats(rs, nkey)
        out.append({"symbol": sym, "n": st["trade_count"], "win_count": st["win_count"],
                    "wr_pct": st["gross_wr_pct"], "total_pnl_pct": st["total_net_pnl_pct"],
                    "avg_pnl_pct": st["avg_net_pnl_pct"], "payoff_rr": st["payoff_rr"]})
    out.sort(key=lambda x: (-x["total_pnl_pct"], -x["n"]))
    return out

def fmt_stats(s):
    return (f"n={s['trade_count']} sym={s['symbol_count']} W={s['win_count']}/L={s['loss_count']} "
            f"WR={s['gross_wr_pct']}% avg={s['avg_net_pnl_pct']}% total={s['total_net_pnl_pct']}% "
            f"avgWin={s['avg_win_pct']}% avgLoss={s['avg_loss_pct']}% payoff={s['payoff_rr']} "
            f"PF={s['profit_factor']} hold={s['avg_hold_bars']} T1viol={s['t1_violation_count']}")

# ============ 1. V88 production contract ============
print("== V88 ==")
v88 = json.load(open(os.path.join(HERMES, "smc_opt_v88_production_contract", "v88_trades.json"), encoding="utf-8"))
# normalize v88 rows to a common shape
def v88_row(t):
    return {"symbol": t.get("symbol"), "entry_date": str(t.get("entry_date") or ""),
            "exit_date": str(t.get("exit_date") or ""), "net_pnl_pct": float(t.get("pnl_pct") or 0),
            "reason": t.get("exit_reason") or "?", "hold_bars": float(t.get("hold_bars") or 0),
            "entry_price": t.get("entry_price"), "exit_price": t.get("exit_price"),
            "sl_price": t.get("sl_price"), "tp1_price": t.get("tp1_price"),
            "rr_realized": t.get("rr_realized"), "mfe_r": t.get("mfe_r"), "mae_r": t.get("mae_r"),
            "event_date": t.get("event_date"), "zone_date": t.get("zone_date"),
            "event_type": t.get("event_type"), "poi_type": t.get("poi_type"),
            "story": t.get("story"), "market_state": t.get("market_state"),
            "trend_regime": t.get("trend_regime"), "trend_reason": t.get("trend_reason"),
            "signal_type": t.get("signal_type"), "v88_combo": t.get("v88_combo"),
            "v83_takeover_type": t.get("v83_takeover_type"), "v85_reason": t.get("v85_reason"),
            "v85_path": t.get("v85_path"), "mtf_score": t.get("mtf_score"),
            "weekly_state": t.get("weekly_state"), "daily_state": t.get("daily_state"),
            "m60_state": t.get("m60_state"), "risk_pct": t.get("risk_pct"),
            "entry_semantic": t.get("entry_semantic"), "sample_class": t.get("sample_class"),
            "t1_violation": t.get("t1_violation")}
v88rows = [v88_row(t) for t in v88]
v88_overall = agg_stats(v88rows)
v88_yearly, v88_monthly = year_month(v88rows)
v88_stocks = stock_summary(v88rows)
print("overall:", fmt_stats(v88_overall))
print("yearly:", [(y["entry_year"], y["trade_count"], y["gross_wr_pct"], y["avg_net_pnl_pct"]) for y in v88_yearly])

# ============ 2. V519 frozen replay ============
print("\n== V519 ==")
# FIX: use the trades path referenced by v519_latest.json (20260803 full run, 3268 rows),
# NOT the first sorted directory (which was the stale 20260716 387-row run).
_v519_latest = json.load(open(os.path.join(AUD, "v519_daily_effort_result_absorption_frozen_t1_replay_latest.json"), encoding="utf-8"))
_v519_trades_path = _v519_latest.get("artifacts", {}).get("trades", "")
if _v519_trades_path:
    _v519_trades_path = _v519_trades_path.replace("/root/.hermes", HERMES)
v519_csv = _v519_trades_path if os.path.exists(_v519_trades_path) else None
print("v519 trades csv:", v519_csv)
v519rows = []
if v519_csv and os.path.exists(v519_csv):
    with open(v519_csv, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            v519rows.append({"symbol": r["symbol"], "entry_date": r["entry_date"], "exit_date": r["exit_date"],
                             "net_pnl_pct": float(r["net_pnl_pct"] or 0), "reason": r["reason"],
                             "hold_bars": float(r["hold_bars"] or 0), "entry_price": r["entry_price"],
                             "exit_price": r["exit_price"], "stop": r["stop"], "target": r["target"],
                             "mfe_r": r["mfe_r"], "mae_r": r["mae_r"],
                             "swing_date": r["swing_date"], "sweep_date": r["sweep_date"],
                             "response_date": r["response_date"], "causal_trace": r["causal_trace"],
                             "prior20_volume_rank": r["prior20_volume_rank"], "t1_violation": r["same_day_exit_violation"]})
print("rows:", len(v519rows))
v519_overall = agg_stats(v519rows)
v519_yearly, v519_monthly = year_month(v519rows)
v519_stocks = stock_summary(v519rows)
print("overall:", fmt_stats(v519_overall))
print("yearly:", [(y["entry_year"], y["trade_count"], y["gross_wr_pct"], y["avg_net_pnl_pct"]) for y in v519_yearly])

# ============ 3. V699 frozen replay ============
print("\n== V699 ==")
v699_dir = [d for d in os.listdir(AUD) if d.startswith("v699_pure_smc") and os.path.isdir(os.path.join(AUD, d))]
v699_csv = os.path.join(AUD, v699_dir[0], "v699_frozen_t1_trades.csv") if v699_dir else None
v699rows = []
if v699_csv and os.path.exists(v699_csv):
    with open(v699_csv, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            v699rows.append({"symbol": r["symbol"], "entry_date": r["entry_date"], "exit_date": r["exit_date"],
                             "net_pnl_pct": float(r["net_pnl_pct"] or 0), "reason": r["reason"],
                             "hold_bars": float(r["hold_bars"] or 0), "entry_price": r["entry_price"],
                             "exit_price": r["exit_price"], "stop": r["stop"], "target": r["target"],
                             "mfe_r": r["mfe_r"], "mae_r": r["mae_r"],
                             "swing_date": r["swing_date"], "sweep_date": r["sweep_date"],
                             "response_date": r["response_date"], "causal_trace": r["causal_trace"],
                             "prior20_volume_rank": r.get("prior20_volume_rank", ""), "t1_violation": r["same_day_exit_violation"]})
print("rows:", len(v699rows))
v699_overall = agg_stats(v699rows)
v699_yearly, v699_monthly = year_month(v699rows)
v699_stocks = stock_summary(v699rows)
print("overall:", fmt_stats(v699_overall))
print("yearly:", [(y["entry_year"], y["trade_count"], y["gross_wr_pct"], y["avg_net_pnl_pct"]) for y in v699_yearly])

# ============ Write reports ============

def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)

def stat_row(s, label):
    return [label, s["trade_count"], s["symbol_count"], s["win_count"], s["loss_count"],
            f"{s['gross_wr_pct']:.2f}%", f"{s['avg_net_pnl_pct']:.4f}%", f"{s['total_net_pnl_pct']:.2f}%",
            f"{s['avg_win_pct']:.2f}%", f"{s['avg_loss_pct']:.2f}%", f"{s['payoff_rr']:.4f}",
            f"{s['profit_factor']:.4f}", f"{s['avg_hold_bars']:.2f}", s["t1_violation_count"]]

HDR = ["期间", "n", "股票数", "胜", "负", "胜率", "平均净收益%", "累计净收益%", "平均盈利%", "平均亏损%", "盈亏比(payoff)", "PF", "平均持仓K线", "T+1违规"]

def write_version_report(name, overall, yearly, monthly, stocks, rows, log_csv, row_headers, row_fmt):
    lines = [f"# {name} 回测报告", ""]
    lines.append(f"> 数据源：{log_csv}（{overall['trade_count']} 笔已平仓）")
    lines.append("> 口径：SMC_BACKTEST_PERIOD_REPORT_V1；净收益 %；胜率=净收益>0 占比；盈亏比 payoff=平均盈利/|平均亏损|；PF=总盈利/|总亏损|；严格 T+1")
    lines.append("")
    lines.append("## 1. 总体")
    lines.append(md_table(HDR, [stat_row(overall, "总体")]))
    lines.append("")
    lines.append("## 2. 逐年")
    lines.append(md_table(HDR, [stat_row(y, y["entry_year"]) for y in yearly]))
    lines.append("")
    lines.append("## 3. 逐月")
    lines.append(md_table(HDR, [stat_row(m, m["entry_month"]) for m in monthly]))
    lines.append("")
    lines.append("## 4. 股票操作清单（按累计净收益排序）")
    sh = ["股票", "交易次数", "胜", "胜率%", "累计净收益%", "平均净收益%", "盈亏比"]
    lines.append(md_table(sh, [[s["symbol"], s["n"], s["win_count"], f"{s['wr_pct']:.2f}", f"{s['total_pnl_pct']:.2f}", f"{s['avg_pnl_pct']:.4f}", f"{s['payoff_rr']:.4f}"] for s in stocks[:200]]))
    lines.append("")
    lines.append("## 5. 逐笔操作日志")
    lines.append(f"> 全部 {len(rows)} 笔见 `{os.path.basename(log_csv)}`；下表为前 60 笔样例（按入场日期）。")
    lines.append(md_table(row_headers, [row_fmt(r) for r in rows[:60]]))
    lines.append("")
    # write full trade log csv
    with open(os.path.join(OUT, log_csv), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["symbol"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return "\n".join(lines)

# V88
v88_headers = ["股票", "入场日期", "出场日期", "入场价", "出场价", "SL", "TP1", "净收益%", "实际RR", "MFE(R)", "MAE(R)", "持仓K", "出场原因", "结构事件", "事件日期", "POI类型", "POI日期", "故事", "市场状态", "趋势", "触发理由", "组合", "T+1"]
def v88_fmt(r):
    return [r["symbol"], r["entry_date"], r["exit_date"], r["entry_price"], r["exit_price"],
            r["sl_price"], r["tp1_price"], f"{r['net_pnl_pct']:.4f}", r["rr_realized"], r["mfe_r"], r["mae_r"],
            r["hold_bars"], r["reason"], r["event_type"], r["event_date"], r["poi_type"], r["zone_date"],
            r["story"], r["market_state"], r["trend_regime"], r["trend_reason"] + " / " + str(r["v85_path"] or ""),
            r["v88_combo"], r["t1_violation"]]
v88_md = write_version_report("V88 生产契约", v88_overall, v88_yearly, v88_monthly, v88_stocks, v88rows, "V88_trades_log.csv", v88_headers, v88_fmt)
open(os.path.join(OUT, "V88_backtest_report.md"), "w", encoding="utf-8").write(v88_md)
print("V88 report written")

# V519
v519_headers = ["股票", "入场日期", "出场日期", "入场价", "出场价", "SL", "目标", "净收益%", "MFE(R)", "MAE(R)", "持仓K", "出场原因", "swing日期", "sweep日期", "response日期", "量能分位", "因果链", "T+1"]
def v519_fmt(r):
    return [r["symbol"], r["entry_date"], r["exit_date"], r["entry_price"], r["exit_price"],
            r["stop"], r["target"], f"{r['net_pnl_pct']:.4f}", r["mfe_r"], r["mae_r"], r["hold_bars"],
            r["reason"], r["swing_date"], r["sweep_date"], r["response_date"], r["prior20_volume_rank"],
            r["causal_trace"], r["t1_violation"]]
v519_md = write_version_report("V517/V519 量价吸收冻结回放（研究）", v519_overall, v519_yearly, v519_monthly, v519_stocks, v519rows, "V519_trades_log.csv", v519_headers, v519_fmt)
open(os.path.join(OUT, "V519_backtest_report.md"), "w", encoding="utf-8").write(v519_md)
print("V519 report written")

# V699
v699_md = write_version_report("V697/V699 纯SMC SSL-Reclaim冻结回放（研究）", v699_overall, v699_yearly, v699_monthly, v699_stocks, v699rows, "V699_trades_log.csv", v519_headers, v519_fmt)
open(os.path.join(OUT, "V699_backtest_report.md"), "w", encoding="utf-8").write(v699_md)
print("V699 report written")

print("\nALL DONE. Output:", OUT)
