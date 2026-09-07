# -*- coding: utf-8 -*-
"""漏斗监控（审计方向7）：跟踪 selection_funnel.json 历史，±2σ 报警。
每次 daily_selection 后由本脚本追加当日漏斗到 selection_funnel_history.json，
并计算各层触发次数的历史均值±2σ；某层跌出区间 → 报警并区分
"市场结构变化" vs "数据/逻辑 bug"（用数据新鲜度交叉判断）。"""
import io, json, os, sys, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

RESEARCH = os.path.dirname(os.path.abspath(__file__))
HIST = os.path.join(RESEARCH, "selection_funnel_history.json")
CUR = os.path.join(RESEARCH, "selection_funnel.json")


def _load(p, default):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default


def record():
    """追加当日漏斗快照到历史（每日一条，按 generated_at 日期去重）。"""
    cur = _load(CUR, None)
    if not cur:
        print("无 selection_funnel.json，跳过")
        return
    hist = _load(HIST, [])
    day = time.strftime("%Y-%m-%d")
    hist = [h for h in hist if h.get("day") != day]  # 同日覆盖
    snap = {"day": day, "generated_at": cur.get("generated_at"),
            "raw": cur.get("raw_announcements", 0),
            "positive": cur.get("classified_positive", 0),
            "orders": cur.get("orders_created", 0),
            "reject": cur.get("reject_by_reason", {})}
    hist.append(snap)
    hist = hist[-250:]  # 保留一年
    with open(HIST, "w", encoding="utf-8") as fh:
        json.dump(hist, fh, ensure_ascii=False, indent=2)
    print(f"记录 {day}: raw={snap['raw']} positive={snap['positive']} orders={snap['orders']} (历史{len(hist)}条)")


def _mean_sigma(vals):
    if len(vals) < 8:
        return None
    m = sum(vals) / len(vals)
    var = sum((x - m) ** 2 for x in vals) / len(vals)
    sd = var ** 0.5
    return m, sd, (m - 2 * sd, m + 2 * sd)


def check():
    """±2σ 报警检查。返回报警列表并写 selection_funnel_alarm.json。"""
    hist = _load(HIST, [])
    alarms = []
    if len(hist) < 8:
        print(f"历史 {len(hist)} < 8 条，不足以建基线，暂不报警")
        return alarms
    layers = {"raw": [h.get("raw", 0) for h in hist[:-1]],
              "positive": [h.get("positive", 0) for h in hist[:-1]],
              "orders": [h.get("orders", 0) for h in hist[:-1]]}
    latest = hist[-1]
    for name, vals in layers.items():
        ms = _mean_sigma(vals)
        if not ms:
            continue
        m, sd, (lo, hi) = ms
        cur_v = latest.get(name, 0)
        if cur_v < lo or cur_v > hi:
            # 交叉判断：数据层崩塌(positive骤降但raw正常) = bug；整体骤降 = 市场变化
            cause = "未知"
            if name == "positive" and cur_v < lo and latest.get("raw", 0) >= (layers["raw"][-1] or 0) * 0.5:
                cause = "⚠ 疑似逻辑/分类 bug（公告总量正常但正事件骤降）"
            elif name in ("raw", "positive") and cur_v < lo:
                cause = "市场结构变化或数据源失败（公告量骤降）"
            alarms.append({"day": latest.get("day"), "layer": name, "value": cur_v,
                           "baseline_mean": round(m, 1), "sigma": round(sd, 1),
                           "normal_range": [round(lo, 1), round(hi, 1)], "cause_hint": cause})
    out = {"checked_at": time.strftime("%Y-%m-%d %H:%M:%S"), "history_n": len(hist),
           "latest": latest, "alarms": alarms}
    with open(os.path.join(RESEARCH, "selection_funnel_alarm.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    if alarms:
        print(f"⚠ 报警 {len(alarms)} 条:")
        for a in alarms:
            print(f"  [{a['layer']}] 当日={a['value']} 正常区间=[{a['normal_range'][0]},{a['normal_range'][1]}] → {a['cause_hint']}")
    else:
        print(f"✅ 全部层在 ±2σ 区间内（{len(hist)} 天基线）")
    return alarms


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.record:
        record()
    if args.check:
        check()
    if not (args.record or args.check):
        record()
        check()