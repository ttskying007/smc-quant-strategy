# -*- coding: utf-8 -*-
"""reject_forward_eval.py —— 第七轮审计 §9.2 被拒候选前向收益评估器（R5, 2026-09-13）。

输入: reject_ledger.json(R5 起每日选股链持久化的拒绝记录) + paper_ledger.json(通过组对照)。
对每个 (code, signal_date) 评估:
  - signal 日收盘为基准的 +5/+10/+20 交易日前瞻收益(通过组同一口径 —— 可控对照, 剔除成交偏差)
  - 窗口内 MFE/MAE(相对基准)
  - 生产口径结构带(structural_sltp, None→固定比例回退带)下的 TP1/SL 触发
判定纪律(预注册): 某拒绝层 n>=20 且被拒样本长期明显优于通过样本, 才考虑放宽该层;
仅前向上涨不足以证明可交易, 还需重放真实成交/滑点/组合容量。

用法: python reject_forward_eval.py [--min-n 20] [--horizon 20]
输出: handover/reject_forward_report.json + 控制台分层摘要。纯研究工具, 不改生产链。"""
import io, json, os, sys, time
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paper_sim  # bars_of / structural_sltp / stage_and_deep / load_ledger

ROOT = paper_sim.ROOT
OUT = os.path.join(HERE, "handover", "reject_forward_report.json")

FWD_DAYS = (5, 10, 20)


def eval_one(bars, d8, tp1=None, sl1=None, ref_mode="signal_close"):
    """纯函数: 单候选前瞻评估。bars 为 paper_sim 日线 bar 列表(dict t/o/h/l/c/v)。
    返回 None(基准日不在K线内/不可评估) 或 dict。tp1/sl1 为 None 时用固定比例回退带
    (与生产"结构不足"回退一致: +3%/-4%)。MFE/MAE 相对基准=signal日收盘。"""
    dates = [b["t"] for b in bars]
    d8 = str(d8)
    if d8 not in dates:
        return None
    i = dates.index(d8)
    ref = bars[i]["c"]
    if not ref or ref <= 0:
        return None
    if tp1 is None:
        tp1 = round(ref * 1.03, 3)
    if sl1 is None:
        sl1 = round(ref * 0.96, 3)
    win = bars[i + 1: i + 1 + max(FWD_DAYS)]
    if not win:
        return None
    out = {"ref": ref, "band": (tp1, sl1), "n_days": len(win)}
    # 前瞻收益(可得窗口, 不满窗口标记 partial)
    for h in FWD_DAYS:
        if len(win) >= h:
            out[f"fwd{h}"] = round(win[h - 1]["c"] / ref - 1, 4)
        else:
            out[f"fwd{h}"] = None
    out["fwd_full_window"] = len(win) >= max(FWD_DAYS)
    # MFE/MAE(窗口 high/low 相对基准)
    out["mfe"] = round(max(b["h"] for b in win) / ref - 1, 4)
    out["mae"] = round(min(b["l"] for b in win) / ref - 1, 4)
    # TP1/SL 触发(同K双触 → SL 优先, 与执行合同一致)
    tp_day = sl_day = None
    for j, b in enumerate(win):
        if tp_day is None and b["h"] >= tp1:
            tp_day = j
        if sl_day is None and b["l"] <= sl1:
            sl_day = j
    out["tp1_hit"] = tp_day is not None
    out["sl_hit"] = sl_day is not None
    out["sl_first"] = sl_day is not None and (tp_day is None or sl_day <= tp_day)
    return out


def _band_for(bars, i, code, d8):
    """生产口径结构带; 失败回退 None(调用方走固定带)。"""
    try:
        st, _deep = paper_sim.stage_and_deep(bars, i)
        adx_v = paper_sim.adx14_of(bars, i) or 0
        tp1, _tp2, _tp3, _tp4, sl1, _sl2, note = paper_sim.structural_sltp(code, d8, src="EVENT", stage=st, adx=adx_v)
        if not tp1 or not sl1:
            return None, None
        return tp1, sl1
    except Exception:
        return None, None


def evaluate(records, bars_of=None, band_for=None, min_n=20):
    """records: [{code,name,date,stage,title,...}] — 按(code,date)取最新 stage 去重。
    bars_of/band_for 可注入(测试)。返回 {"per_stage": {...}, "total_n": int, "unavailable": int}。"""
    bars_of = bars_of or paper_sim.bars_of
    band_for = band_for or _band_for
    # (code,date) → 最新记录(ts 降序取后写的)
    latest = {}
    for r in records:
        key = (r.get("code"), str(r.get("date", "")).replace("-", ""))
        if key[1] and key[0]:
            if key not in latest or str(r.get("ts", "")) >= str(latest[key].get("ts", "")):
                latest[key] = r
    per_stage = defaultdict(lambda: {"n": 0, "avail": 0, "fwd": defaultdict(list),
                                     "mfe": [], "mae": [], "tp1": 0, "sl": 0, "sl_first": 0, "full": 0})
    unavailable = 0
    for (code, d8), r in latest.items():
        stage = r.get("stage", "?")
        s = per_stage[stage]
        s["n"] += 1
        if stage == "DUP_EXISTING":
            continue  # 主账本已跟踪, 不重复评估
        bs = bars_of(code)
        ev = None
        if bs:
            tp1 = sl1 = None
            dates = [b["t"] for b in bs]
            if d8 in dates:
                ii = dates.index(d8)
                tp1, sl1 = band_for(bs, ii, code, d8)
            ev = eval_one(bs, d8, tp1, sl1)
        if ev is None:
            unavailable += 1
            continue
        s["avail"] += 1
        s["full"] += 1 if ev["fwd_full_window"] else 0
        for h in FWD_DAYS:
            v = ev[f"fwd{h}"]
            if v is not None:
                s["fwd"][h].append(v)
        s["mfe"].append(ev["mfe"])
        s["mae"].append(ev["mae"])
        s["tp1"] += 1 if ev["tp1_hit"] else 0
        s["sl"] += 1 if ev["sl_hit"] else 0
        s["sl_first"] += 1 if ev["sl_first"] else 0
    # 汇总
    agg = {}
    for stage, s in per_stage.items():
        agg[stage] = {
            "n": s["n"], "evaluable": s["avail"], "full_window": s["full"],
            "fwd_avg": {f"h{h}": (round(sum(v) / len(v), 4) if v else None) for h, v in s["fwd"].items()},
            "fwd_n": {f"h{h}": len(v) for h, v in s["fwd"].items()},
            "mfe_avg": round(sum(s["mfe"]) / len(s["mfe"]), 4) if s["mfe"] else None,
            "mae_avg": round(sum(s["mae"]) / len(s["mae"]), 4) if s["mae"] else None,
            "tp1_hit_rate": round(s["tp1"] / s["avail"], 3) if s["avail"] else None,
            "sl_hit_rate": round(s["sl"] / s["avail"], 3) if s["avail"] else None,
            "sl_first_rate": round(s["sl_first"] / s["avail"], 3) if s["avail"] else None,
        }
    return {"per_stage": agg, "total_n": len(latest), "unavailable": unavailable}


def passed_cohort_forward(ledger, bars_of=None):
    """通过组(挂单过的候选)同一口径前瞻收益 —— 可控对照(非实际成交口径)。"""
    bars_of = bars_of or paper_sim.bars_of
    recs = []
    for t in ledger:
        sd = str(t.get("signal_date", "")).replace("-", "")
        if sd and t.get("code"):
            recs.append({"code": t["code"], "date": sd, "stage": "PASSED_ORDER", "ts": ""})
    return evaluate(recs, bars_of=bars_of)


def _avg_vs_pass(rej_h, pass_h):
    """预注册方向判定: 被拒层均值 vs 通过组均值。"""
    if rej_h is None or pass_h is None:
        return "insufficient_data"
    d = round(rej_h - pass_h, 4)
    if d > 0.02:
        return f"rejected_better(+{d:.4f})"
    if d < -0.02:
        return f"rejected_worse({d:.4f})"
    return "comparable"


def path_aware_expectation(s, sl_ret=-0.04, tp1_ret=0.03):
    """R6(§9.2 纪律落地): 路径感知期望 —— sl_first 先离场者吃不到 h20。
    E[path] = sl_first×SL收益 + tp1_no_sl×TP1收益 + neither×h20均值。
    naive fwd 会把"先止损的样本"按 h20 计收益, 系统性高估被拒层价值;
    该函数把 §9.2"只看上涨不足以证明可交易"变成可计算判据。
    tp1_no_sl = min(max(0, tp1率-sl率), 1-sl_first)(保守夹挤)。"""
    h20 = (s.get("fwd_avg") or {}).get("h20")
    slf, tp1, sl = s.get("sl_first_rate"), s.get("tp1_hit_rate"), s.get("sl_hit_rate")
    if h20 is None or slf is None or tp1 is None or sl is None:
        return None
    tp1_no_sl = min(max(0.0, tp1 - (sl or 0)), 1 - slf)
    neither = max(0.0, 1 - slf - tp1_no_sl)
    e = slf * sl_ret + tp1_no_sl * tp1_ret + neither * h20
    return {"sl_first": slf, "tp1_no_sl": round(tp1_no_sl, 3), "neither": round(neither, 3),
            "e_path": round(e, 4), "naive_h20": h20}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-n", type=int, default=20)
    args = ap.parse_args()
    try:
        records = json.load(open(os.path.join(ROOT, "reject_ledger.json"), encoding="utf-8"))
    except FileNotFoundError:
        print("reject_ledger.json 尚不存在 —— 首日选股链(周一 19:03)后生成。无前向数据可评。")
        return 0
    led = paper_sim.load_ledger()
    rej = evaluate(records)
    pas = passed_cohort_forward(led)
    pas_avg = (pas.get("per_stage", {}).get("PASSED_ORDER", {}) or {}).get("fwd_avg", {})
    verdicts = {}
    for stage, s in rej["per_stage"].items():
        if stage == "DUP_EXISTING" or s["evaluable"] < args.min_n:
            verdicts[stage] = {"n_evaluable": s["evaluable"], "verdict": "below_min_n(不判定)"}
            continue
        verdicts[stage] = {
            "n_evaluable": s["evaluable"],
            "vs_passed": {f"h{h}": _avg_vs_pass(s["fwd_avg"].get(f"h{h}"), pas_avg.get(f"h{h}"))
                          for h in FWD_DAYS},
            "path_aware": path_aware_expectation(s),
            "verdict": "watch(仅观察, 放宽需连续样本+n>=20+通过重放验证)",
        }
    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "min_n": args.min_n,
        "rejected": rej,
        "passed_cohort": pas,
        "verdicts": verdicts,
        "discipline": "被拒层优于通过组仅是放宽必要条件; 还须重放真实成交/滑点/组合容量(§9.2 纪律)",
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(report, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"被拒记录 {rej['total_n']} 条, 可评估 {sum(s['evaluable'] for s in rej['per_stage'].values())}, 不可评估 {rej['unavailable']}")
    for stage, s in sorted(rej["per_stage"].items(), key=lambda kv: -kv[1]["n"]):
        v = verdicts.get(stage, {})
        pa = path_aware_expectation(s)
        pa_txt = f" E[path]={pa['e_path']:+.4f}(slf={pa['sl_first']:.2f},tp1ns={pa['tp1_no_sl']:.2f})" if pa else ""
        print(f"  {stage:16s} n={s['n']:4d} avail={s['evaluable']:4d} h20avg={s['fwd_avg'].get('h20')} "
              f"mfe={s['mfe_avg']} mae={s['mae_avg']} tp1={s['tp1_hit_rate']} sl={s['sl_hit_rate']} "
              f"verdict={v.get('verdict','')}{pa_txt}")
    print(f"通过组对照: n={(pas.get('per_stage',{}).get('PASSED_ORDER',{}) or {}).get('n',0)} "
          f"h20avg={pas_avg.get('h20')}")
    print(f"已写 {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())