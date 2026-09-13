# -*- coding: utf-8 -*-
"""reject_fill_replay.py —— R8: ADX_LT20 拒绝层 fill-level 成交重放(2026-09-13)。

动机(R6 预注册纪律的执行): R6 发现 ADX_LT20 是唯一值得重放验证的候选层
(E[path]=+1.03%, TP1 率 64%), 但那是 **order-level**(信号日收盘基准)估计。
审计 §9.2 判定纪律明文: "只看被拒候选后续上涨不足以证明可以交易; 还要重放
真实成交、滑点和组合容量"。本模块把该纪律做成可执行代码。

回放语义(与生产 daily_selection 完全一致, 零另写规则):
  1. 候选来源 = reject_ledger_backfill.json 的 ADX_LT20 记录(R6 研究级重放产物,
     逻辑与生产同源, provenance 已分账)
  2. 每条候选按生产路径构造订单: structural_sltp(EVENT, stage, adx) 结构带
     (回退固定 +3%/+6%/+10%/+15% / −4%/−10%) + entry_mode=limit_or_open
     (limit=披露日收盘×0.99, 触价优先, 否则 valid_from 日 open 兜底)
  3. 成交重放(try_fill 语义按日线 bar 等价实现, 不重复核心规则):
       valid_from 日(=signal 次交易日): low<=limit → 以 limit×(1+slippage) 成交;
       否则 open 兜底 → open×(1+slippage); 一字涨停(entry_ok SKIP_LIMIT_UP)跳过;
       3 个交易日未成交 → TTL EXPIRED(与生产 PENDING_EXPIRE_DAYS=3 一致)
  4. 退出重放 = core.execution.simulate(逐 bar, SL_GAP/SL/BE/TP 分批/追踪/TIME,
     net 含 FEE) —— 与回测/纸面同一内核, 零平行实现
  5. 报告层间对比: fill_rate / 未成交原因分布 / exit_reason 分布 / avg net /
     PF / SL 率 / TP1 率 / MFE/MAE / 与 order-level(信号日收盘)期望的偏差
  6. **纯研究输出**: 不改任何生产过滤器; ADX 门仍在; 输出仅作为
     "放宽决策"的预注册证据(且需生产账本 n>=20 独立确认后才可能动门)。

用法: python reject_fill_replay.py [--stages ADX_LT20] [--min-n 20]
"""
import io, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 教训#7(R10): stdout wrap 只在 __main__ —— 本模块被 reject_stress_gate import,
# 模块级 wrap 会双包(调用方已 wrap), GC 关闭首个 wrapper → "I/O operation on closed file"

import paper_sim
from core.execution import simulate, entry_ok
from core.trading_calendar import next_td

HERE = os.path.dirname(os.path.abspath(__file__))
BACKFILL_FILE = os.path.join(paper_sim.ROOT, "reject_ledger_backfill.json")
FEE = paper_sim.CFG.FEE_PCT
SLIP = paper_sim.CFG.SLIPPAGE


def replay_one(code, d8, bars, stage, adx, ttl_td=3, max_hold=None):
    """单候选 fill-level 回放(纯函数, bars 注入; 返回 dict 或 None=不可回放)。
    语义对齐生产: structural_sltp 结构带(回退固定比例) + limit_or_open + TTL。"""
    dates = [b["t"] for b in bars]
    if d8 not in dates:
        return None
    i = dates.index(d8)
    close_px = bars[i]["c"]
    tp1, tp2, tp3, tp4, sl1, sl2, note = paper_sim.structural_sltp(code, d8, src='EVENT', stage=stage, adx=(adx or 0))
    if tp1 is None or sl1 is None or tp4 is None or tp4 <= close_px or sl2 is None:
        tp1, tp2, tp3, tp4 = (round(close_px * 1.03, 3), round(close_px * 1.06, 3),
                              round(close_px * 1.10, 3), round(close_px * 1.15, 3))
        sl1, sl2 = round(close_px * 0.96, 3), round(close_px * 0.90, 3)
        note = "回退:固定比例(结构不足)"
    limit_px = round(close_px * 0.99, 3)
    vf = next_td(d8)
    if vf is None or vf not in dates:
        return None  # valid_from 无K线(数据缺失/未来) → 不可回放
    vi = dates.index(vf)
    # fill 窗口: vf 起 ttl_td 个交易日内撮合
    fill_px, fill_rule, why_not = None, "", ""
    for k in range(vi, min(len(bars), vi + ttl_td)):
        b = bars[k]
        # 一字涨停开盘买不到(生产 entry_ok 同语义)
        ok, skip = entry_ok(bars, k, limit_px, sl1, prev_close=(bars[k-1]["c"] if k >= 1 else None), code=code)
        if not ok:
            why_not = skip
            break
        if b["l"] <= limit_px:
            fill_px = round(limit_px * (1 + SLIP), 3)
            fill_rule = "LIMIT_OR_OPEN: low<=ref"
            break
        if k == vi and b["o"] > 0:  # 仅 valid_from 日有 open 兜底
            fill_px = round(b["o"] * (1 + SLIP), 3)
            fill_rule = "LIMIT_OR_OPEN: open_fallback"
            break
    if fill_px is None:
        return {"code": code, "date": d8, "stage": stage, "filled": False,
                "why": why_not or "TTL_EXPIRED", "anchor": note}
    r = simulate(bars, vi, fill_px, sl1, tp1=tp1, tp2=tp4, tp3=None, code=code,
                 partial_tp1=0.3, stop_to_be=True, max_hold=max_hold or 15)
    return {"code": code, "date": d8, "stage": stage, "filled": True,
            "fill_rule": fill_rule, "fill_price": fill_px, "anchor": note,
            "limit": limit_px, "tp1": tp1, "tp4": tp4, "sl1": sl1,
            "reason": r["reason"], "net_pnl_pct": r["net_pnl_pct"],
            "hold_bars": r["hold_bars"], "mfe_pct": r["mfe_pct"], "mae_pct": r["mae_pct"],
            "skipped": r.get("skipped", False)}


def enrich_passed(passed, bars_of=None, stage_and_deep=None, adx14_of=None):
    """通过层记录补 stage/adx(生产在 daily_selection 同点位计算, 此处同语义重建)。"""
    bars_of = bars_of or paper_sim.bars_of
    stage_and_deep = stage_and_deep or paper_sim.stage_and_deep
    adx14_of = adx14_of or paper_sim.adx14_of
    _cache = {}
    out = []
    for p in passed:
        code, d8 = p["code"], p["date"]
        bs = _cache.get(code)
        if bs is None:
            bs = bars_of(code)
            if bs:
                _cache[code] = bs
        if not bs:
            continue
        dates = [b["t"] for b in bs]
        if d8 not in dates:
            continue
        i = dates.index(d8)
        st, _ = stage_and_deep(bs, i)
        out.append({"code": code, "name": p.get("name", ""), "date": d8,
                    "stage": "STAGE_PASS_" + st, "adx": adx14_of(bs, i),
                    "title": p.get("title", "")})
    return out


def run_layer(records, bars_of=None, ttl_td=3, min_n=20):
    """对一个拒绝层的全部记录做 fill-level 回放; 返回聚合 + 逐笔。"""
    bars_of = bars_of or paper_sim.bars_of
    trades, not_f, unavail = [], [], []
    _cache = {}
    for rec in records:
        code, d8 = rec["code"], rec["date"]
        bs = _cache.get(code)
        if bs is None:
            bs = bars_of(code)
            if bs:
                _cache[code] = bs
        if not bs:
            unavail.append(rec)
            continue
        r = replay_one(code, d8, bs, rec.get("stage"), rec.get("adx"), ttl_td=ttl_td)
        if r is None:
            unavail.append(rec)
        elif r["filled"]:
            trades.append(r)
        else:
            not_f.append(r)
    agg = aggregate(trades, not_f, len(unavail), min_n)
    return {"trades": trades, "not_filled": not_f, "unavailable": unavail, "agg": agg}


def aggregate(trades, not_filled, n_unavail, min_n=20):
    ok = [t for t in trades if not t.get("skipped")]
    wins = [t for t in ok if t["net_pnl_pct"] > 0]
    gp = sum(t["net_pnl_pct"] for t in ok if t["net_pnl_pct"] > 0)
    gl = -sum(t["net_pnl_pct"] for t in ok if t["net_pnl_pct"] <= 0)
    sl = [t for t in ok if t["reason"].startswith(("SL", "BE"))]
    tp1h = [t for t in ok if t["reason"] in ("TP1", "TP2_RUNNER", "TP3_RUNNER", "TP_STRUCTURAL")]
    ts = [t for t in ok if t["reason"] == "TIME_STOP"]
    return {
        "n_candidates": len(trades) + len(not_filled) + n_unavail,
        "n_evaluable": len(trades) + len(not_filled),
        "n_filled": len(trades), "n_not_filled": len(not_filled), "n_unavailable": n_unavail,
        "fill_rate": round(len(trades) / max(1, len(trades) + len(not_filled)), 4),
        "not_filled_why": _count(not_filled, "why"),
        "exit_reasons": _count(ok, "reason"),
        "skip_reasons": _count([t for t in trades if t.get("skipped")], "reason"),
        "avg_net_pct": round(sum(t["net_pnl_pct"] for t in ok) / len(ok), 4) if ok else None,
        "win_rate": round(len(wins) / len(ok), 4) if ok else None,
        "pf": round(gp / gl, 3) if gl > 0 else None,
        "sl_rate": round(len(sl) / len(ok), 4) if ok else None,
        "tp_rate": round(len(tp1h) / len(ok), 4) if ok else None,
        "time_rate": round(len(ts) / len(ok), 4) if ok else None,
        "avg_mfe": round(sum(t["mfe_pct"] for t in ok) / len(ok), 3) if ok else None,
        "avg_mae": round(sum(t["mae_pct"] for t in ok) / len(ok), 3) if ok else None,
        "min_n_gate": len(ok) >= min_n,
    }


def _count(items, key):
    from collections import Counter
    return dict(Counter(i.get(key) for i in items))


def main():
    import argparse
    import sqlite3
    import reject_backfill as RB
    from core.trading_calendar import td_set
    ap = argparse.ArgumentParser()
    ap.add_argument("--stages", default="ADX_LT20")
    ap.add_argument("--ttl", type=int, default=3)
    ap.add_argument("--min-n", type=int, default=20)
    args = ap.parse_args()
    if not os.path.exists(BACKFILL_FILE):
        print(f"FAIL-FAST: {BACKFILL_FILE} 尚不存在 — 先跑 reject_backfill.py")
        return 1
    records = json.load(open(BACKFILL_FILE, encoding="utf-8"))
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    out = {"generated_at": ts, "provenance": "fill_level_replay(研究级;不改生产过滤器)",
           "ttl_td": args.ttl, "per_stage": {}}
    print(f"候选来源: reject_ledger_backfill.json (n={len(records)}, provenance=backfill_replay)")
    # 对照组: 同窗口通过层, 用完全相同 fill/退出语义回放(生产真实通过单的同窗基线)
    print("重建同窗通过层对照组(与拒绝回放同窗口/同语义)...")
    tds = sorted(td_set())
    asof = tds[-1]
    sig_dates, _ = RB.compute_window(asof, days=60, tds=tds)
    _rej, passed = RB.replay(sig_dates)
    passed_enriched = enrich_passed(passed)
    ctrl = run_layer(passed_enriched, ttl_td=args.ttl, min_n=args.min_n)
    out["control_passed_cohort"] = ctrl["agg"]
    ca = ctrl["agg"]
    print(f"\n== 对照组: 同窗通过层 fill-level (n={ca['n_candidates']}, 可回放={ca['n_evaluable']}) ==")
    print(f"  成交 {ca['n_filled']} ({ca['fill_rate']*100:.1f}%) | 未成交 {ca['n_not_filled']} {ca['not_filled_why']} | 无数据 {ca['n_unavailable']}")
    print(f"  exit: {ca['exit_reasons']}")
    if ca["n_filled"]:
        print(f"  avg_net={ca['avg_net_pct']}% win={ca['win_rate']} PF={ca['pf']} "
              f"SL率={ca['sl_rate']} TP率={ca['tp_rate']} MFE={ca['avg_mfe']}% MAE={ca['avg_mae']}%")
    for st in [s.strip() for s in args.stages.split(",") if s.strip()]:
        sel = [r for r in records if r.get("stage") == st]
        if not sel:
            print(f"\n== {st}: 无记录, 跳过")
            continue
        res = run_layer(sel, ttl_td=args.ttl, min_n=args.min_n)
        a = res["agg"]
        out["per_stage"][st] = a
        print(f"\n== {st} fill-level 回放 (n={a['n_candidates']}, 可回放={a['n_evaluable']}, TTL={args.ttl}td) ==")
        print(f"  成交 {a['n_filled']} ({a['fill_rate']*100:.1f}%) | 未成交 {a['n_not_filled']} {a['not_filled_why']} | 无数据 {a['n_unavailable']}")
        print(f"  exit: {a['exit_reasons']} | skip: {a['skip_reasons']}")
        gate = "PASS" if a["min_n_gate"] else "below_min_n(不判定)"
        if a["n_filled"]:
            print(f"  avg_net={a['avg_net_pct']}% win={a['win_rate']} PF={a['pf']} "
                  f"SL率={a['sl_rate']} TP率={a['tp_rate']} TIME率={a['time_rate']} MFE={a['avg_mfe']}% MAE={a['avg_mae']}% -> {gate}")
        verdict = "fill级亏损→拒绝正确" if (a["avg_net_pct"] is not None and a["avg_net_pct"] <= 0) else \
                  ("fill级为正但需生产账本独立确认" if a["avg_net_pct"] is not None else "不可判定")
        # 预注册对照: 放宽必要条件 = fill级 avg 为正 且 ≥ 通过层同窗 avg − 2pp(预注册带宽)
        if a["avg_net_pct"] is not None and ca["avg_net_pct"] is not None:
            delta = round(a["avg_net_pct"] - ca["avg_net_pct"], 4)
            out["per_stage"][st]["vs_control_pp"] = delta
            if delta < -2:
                verdict = f"显著劣于通过层({delta:+.2f}pp<-2pp)→拒绝正确(放宽无证据)"
            elif a["avg_net_pct"] > 0:
                verdict = f"fill级+{a['avg_net_pct']}% vs 通过层{ca['avg_net_pct']}%({delta:+.2f}pp, 带宽内)→必要条件满足, 待生产账本独立确认"
            out["per_stage"][st]["verdict"] = verdict
        print(f"  判定: {verdict}")
    out["discipline"] = ("预注册纪律: fill-level 为正仅是放宽 ADX_LT20 的必要条件之一; "
                         "还需生产 reject_ledger 前瞻积累 n>=20 独立同向 + 组合容量约束复核; "
                         "在此之前 ADX>=20 门保持不变(frozen)")
    rp = os.path.join(HERE, "handover", "reject_fill_replay_report.json")
    json.dump(out, open(rp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n已写 {rp}")
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.exit(main())