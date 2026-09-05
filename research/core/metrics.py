# -*- coding: utf-8 -*-
"""core/metrics.py —— 回测指标核心（审计 F14 收敛 / F19）
统一统计 / IS-OOS / Walk-Forward 实现，供回测脚本与报告共用。
"""


def stats_of(pnls):
    if not pnls:
        return None
    n = len(pnls)
    mean = sum(pnls) / n
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x <= 0]
    pf = sum(wins) / abs(sum(losses)) if losses else 99.0
    avg_win = sum(wins) / max(1, len(wins))
    avg_loss = abs(sum(losses)) / max(1, len(losses))
    payoff = avg_win / avg_loss if avg_loss else 99.0
    sv = sorted(pnls)
    return {"n": n, "avg": mean, "win": len(wins) / n, "pf": pf,
            "payoff": payoff, "median": sv[n // 2],
            "std": (sum((x - mean) ** 2 for x in pnls) / n) ** 0.5,
            "min": sv[0], "max": sv[-1],
            "avg_win": avg_win, "avg_loss": avg_loss}


def fmt(s):
    if not s:
        return "n=0"
    return ("n=%d avg=%+.2f%% wr=%.0f%% PF=%.2f payoff=%.2f" %
            (s["n"], s["avg"], s["win"] * 100, s["pf"], s["payoff"]))


def is_oos_split(rows, frac=0.7, date_field="entry_date"):
    """按日期排序后 70/30 切分 IS/OOS，返回 (is_rows, oos_rows, cut_date)。"""
    ok = [r for r in rows if r.get(date_field)]
    ok.sort(key=lambda r: str(r[date_field]))
    cut = int(len(ok) * frac)
    return ok[:cut], ok[cut:], (ok[cut][date_field] if cut < len(ok) else "")


def walk_forward_split(rows, is_months=12, oos_months=3, date_field="entry_date"):
    """滚动前推窗口（IS 12月 → OOS 3月），产出 [(is_rows, oos_rows, label), ...]。"""
    from collections import defaultdict
    by_month = defaultdict(list)
    for r in rows:
        d = str(r.get(date_field, ""))
        if d:
            by_month[d[:6]].append(r)
    months = sorted(by_month.keys())
    out = []
    i = 0
    seg = 0
    while i + is_months + oos_months <= len(months):
        is_m = months[i:i + is_months]
        oos_m = months[i + is_months:i + is_months + oos_months]
        is_rows = [r for m in is_m for r in by_month.get(m, [])]
        oos_rows = [r for m in oos_m for r in by_month.get(m, [])]
        seg += 1
        out.append((is_rows, oos_rows, f"seg{seg}:{is_m[0]}~{is_m[-1]}→{oos_m[0]}~{oos_m[-1]}"))
        i += oos_months
    return out
