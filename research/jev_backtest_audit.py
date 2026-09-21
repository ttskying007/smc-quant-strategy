# -*- coding: utf-8 -*-
"""jev_backtest_audit.py — R65: 用 Jev 对 v22 冻结基线做全量逐笔审计

设计(不可绕过):
- 每笔腿 1 次请求 × 5 问 = 1858 请求; 结果逐行落盘 jev_audit_cache.jsonl —— 断点续跑
- 每问独立校验: 信号真伪 / 趋势判断 / 入场时机 / TP/SL 布局 / 未来超额方向
- Jev 的答案永远只作为"判断数据"写入 — 绝不反向修改基线
- 配额/限流: 0.6s 延时, 429/5xx 指数退避; 失败腿不重试留断点

用法:
  python jev_backtest_audit.py --smoke 20      # 试跑 20 笔 (去年+今年各档)
  python jev_backtest_audit.py                # 全量
"""
import argparse, csv, json, os, sys, time, urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from core.jev_client import judge  # noqa: E402

SRC = os.path.join(ROOT, "combo_v22_trades.csv")
OUT = os.path.join(ROOT, "jev_audit_cache_v2.jsonl")  # R65b: 无前视版本(净state)
QSET = "v2_nopnl"

# 5问契约 — 预注册, 不可改(R65b: state 已去除一切事后字段)
QUESTIONS = {
    "signal_valid": {"type": "noul",
                     "instructions": "该买入信号按(事件+SMC结构+吸筹位)判断, 是否属于真实的吸筹/结构入场机会?"},  # noqa: E501
    "trend_verdict": {"type": "choice",
                      "instructions": "以入场当时状态看, 该标的实际处于哪种主导趋势?",
                      "criteria": {"strong_up": "明确上涨趋势(HH/HL, ADX强)",
                                   "mild_up": "弱上涨/震荡偏多",
                                   "neutral": "横盘",
                                   "mild_down": "弱下跌/震荡偏空",
                                   "strong_down": "明确下跌趋势(LH/LL, ADX强)"}},
    "entry_timing": {"type": "score",
                     "instructions": "该入场的时机质量?(锚点是否好)",
                     "criteria": ["差:迟入场/追高/情绪顶", "一般:信号已运行数日", "好:信号刚确认/回踩贴着",
                                  "很好:刚破回踩, 多好位叠加"]},
    "tpsl_design": {"type": "choice",
                    "instructions": "按此笔的 TP/SL 布局与后续实际走势比较, TP/SL 属于哪种?",
                    "criteria": {"tp_sys_too_low": "TP1-4 太低, 提前止盈丢了大头",
                                 "tp_sys_ok": "TP/SL 大致合理",
                                 "sl_too_tight": "SL 太紧, 波动本可拿",
                                 "tp_too_high_sl_hit": "TP 太高没遇到但 SL 常触, 参数错位"}},
    "excess_direction": {"type": "choice",
                         "instructions": "入场后2周内, 相对市场的方向?",
                         "criteria": {"up": "明显涨", "flat": "震荡", "down": "明显跌", "unknown": "不明"}},
}


def _load_legs():
    rows = [r for r in csv.DictReader(open(SRC, encoding="utf-8-sig"))]
    legs = []
    for i, r in enumerate(rows):
        legs.append({"_leg_id": f"{r['symbol']}|{r['entry_date']}|{i}", **r})
    return legs


def _leg_state(r):
    """R65b: 严禁事后字段 — 只允许入场当时可知的信息。
    剔除: net_pnl_pct/sell_price/reason/hold_bars/mfe/mae/rr/exit 一切。"""
    try:
        chain = json.loads(r["chain_json"]) if r.get("chain_json") else {}
    except Exception:
        chain = {}
    return {
        "symbol": r["symbol"], "entry_date": r["entry_date"], "src": r["src"],
        "buy_price": r["buy_price"],
        "rank": r.get("rank"),
        "trend_state": r.get("trend_state"), "signal_chain": r.get("signal_chain"),
        "sub_signals": r.get("sub_signals"),
        "breakout": {"date": r.get("breakout_date"), "price": r.get("breakout_price"), "kind": r.get("breakout_kind")},
        "retrace": {"price": r.get("retrace_price"), "state": r.get("retrace_state"), "signal": r.get("retrace_signal")},
        "stage_span": r.get("stage_span"), "adx_span": r.get("adx_span"),
        "chain_trend": chain.get("trend_state"),
        "events_tail": (chain.get("events_tail") or [])[-3:],
    }


def run(limit=None, smoke_years=None, shard=0, nshards=1):
    legs = _load_legs()
    seen = set()
    if os.path.exists(OUT):
        for ln in open(OUT, encoding="utf-8"):
            try:
                seen.add(json.loads(ln)["leg_id"])
            except Exception:
                pass
    todo = [L for i, L in enumerate(legs) if L["_leg_id"] not in seen and (i % nshards) == shard]
    if smoke_years:
        # 每年取2笔: 腿的头/尾
        picks = []
        for y in smoke_years:
            grp = [L for L in todo if str(L["entry_date"]).startswith(y)]
            if grp:
                picks.extend(grp[:1] + grp[-1:])
        todo = picks
    if limit:
        todo = todo[:limit]
    print(f"总腿数 {len(legs)}, 已完成 {len(seen)}, 本轮 {len(todo)}")
    fh = open(OUT, "a", encoding="utf-8")
    done = ok = err = 0
    t0 = time.time()
    for lg in todo:
        lgst = None
        for attempt in range(3):
            try:
                ans = judge(_leg_state(lg), QUESTIONS, timeout=60)
                a = ans.get("answers", {})
                rec = {"leg_id": lg["_leg_id"], "qset": QSET, "symbol": lg["symbol"],
                       "entry_date": lg["entry_date"], "src": lg["src"],
                       "p_valid": a.get("signal_valid", {}).get("noul"),
                       "trend": a.get("trend_verdict", {}).get("choice"),
                       "trend_conf": a.get("trend_verdict", {}).get("confidence"),
                       "timing": a.get("entry_timing", {}).get("score"),
                       "timing_conf": a.get("entry_timing", {}).get("confidence"),
                       "tpsl": a.get("tpsl_design", {}).get("choice"),
                       "tpsl_conf": a.get("tpsl_design", {}).get("confidence"),
                       "direction": a.get("excess_direction", {}).get("choice"),
                       "direction_conf": a.get("excess_direction", {}).get("confidence"),
                       "net_pnl_pct": float(lg["net_pnl_pct"]) if lg.get("net_pnl_pct") else None,
                       "model": ans.get("model"), "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                ok += 1
                break
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(2 * (attempt + 1))
                    continue
                if attempt == 2:
                    print(f"!! {lg['_leg_id']} HTTP {e.code}", file=sys.stderr)
                    err += 1
                else:
                    time.sleep(0.5 * (attempt + 1))
            except Exception as e2:
                if attempt == 2:
                    print(f"!! {lg['_leg_id']} {e2}", file=sys.stderr)
                    err += 1
                else:
                    time.sleep(0.5 * (attempt + 1))
        done += 1
        if done % 50 == 0:
            rate = done / max(time.time() - t0, 0.1)
            eta = (len(todo) - done) / rate if rate else 0
            print(f"  ... {done}/{len(todo)} ok={ok} err={err} rate={rate:.1f}/s ETA {eta/60:.1f}min", flush=True)
        time.sleep(0.3)  # 限流: 多进程并发已经不低
    fh.close()
    print(f"DONE shard={shard}: 完成 {done}, 成功 {ok}, 失败 {err}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", type=int, default=0)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--nshards", type=int, default=1)
    args = ap.parse_args()
    if args.smoke:
        run(limit=args.smoke, smoke_years=["2024", "2025", "2026"])
    else:
        run(shard=args.shard, nshards=args.nshards)
