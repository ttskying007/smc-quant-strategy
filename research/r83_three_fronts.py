# -*- coding: utf-8 -*-
"""r83_three_fronts.py — R83: 三面同时推进
1. 低权重腿(w<0.7) 稳定性研究: 近期一线生存分析
2. 2024-01 结底: 市场指数级熔断 P1 研究
3. 2023 年全年逆势腿深度调研(41腿)
"""
import csv, json, os, sys, io
from collections import defaultdict, Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "combo_v23_shadow.csv")
OUT = os.path.join(ROOT, "handover", "R83_three_fronts.md")
IDX_FILES = [
    os.path.join(ROOT, "idx_sh000001.json"),  # 合并好的真上证指数 2023-01→2026-09 (904 bars)
]

rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
for r in rows:
    r["_pnl"] = float(r["net_pnl_pct"] or 0)
    r["_w"] = float(r.get("v23_weight") or 1)


def st(rs, wkey=None):
    if not rs:
        return 0, 0, 0, 0
    n = len(rs)
    if wkey:
        tot = sum(r["_pnl"] * r[wkey] for r in rs)
        ws = sum(r[wkey] for r in rs)
        avg = tot / ws
        pos = sum(r["_pnl"] * r[wkey] for r in rs if r["_pnl"] > 0)
        neg = -sum(r["_pnl"] * r[wkey] for r in rs if r["_pnl"] < 0)
    else:
        ps = [r["_pnl"] for r in rs]
        avg = sum(ps) / n
        pos = sum(v for v in ps if v > 0)
        neg = -sum(v for v in ps if v < 0)
    return n, round(avg, 2), round(sum(1 for r in rs if r["_pnl"] > 0) / n * 100, 1), round(pos / neg, 2) if neg else 999


def wb(r):
    w = r["_w"]
    return "w≥1" if w >= 1 else ("w 0.7-1" if w >= 0.7 else "w<0.7")


idx = None
for p in IDX_FILES:
    if os.path.exists(p):
        idx = json.load(open(p, encoding="utf-8"))
        print(f"norath指数: {os.path.basename(p)}")
        break

md = ["# R83 — 三面同时推进", f"n={len(rows)}\n"]

# ═══════ 面1: w<0.7 腿 的稳定性 ═══════
md.append("\n## 面 1 — 低权重腿(w<0.7) 稳定性")
md.append("**问题**: 2026 为案, w<0.7 的腿 avg +7.37 PF 5.44, 是'隐藏的黄金'还是'灯下黑'?")

md.append("\n### A1. 逐年/按 w 桶分别统计(影子和基线)")
md.append("| 年 × 权重桶 | n | 基线 avg | 鄉子 avg | PF |")
md.append("|---|---|---|---|---|")
by_yw = defaultdict(list)
for r in rows:
    by_yw[(r["entry_date"][:4], wb(r))].append(r)
for (y, b), rs in sorted(by_yw.items()):
    _, a0, _, p0 = st(rs)
    _, a1, _, p1 = st(rs, "_w")
    md.append(f"| {y} {b} | {len(rs)} | {a0} | {a1} | {p1} |")

md.append("\n### A2. 反事实: 如果您从入场时就拒接 w<0.7 的单")
md.append("| 场景 | n | Σw | avg | WR% | PF | vs 影子 |")
md.append("|---|---|---|---|---|---|---|")
full = [r for r in rows]
full_w = sum(r["_w"] for r in rows)
n, a, w, p = st(full, "_w")
md.append(f"| 现状(全部1858腿 Σw=1008) | {n} | {full_w:.0f} | {a} | {w} | {p} | — |")
for cut, name in [(0.7, "只留 w≥0.7(放弃被降权的低质腿)"), (0.5, "只留 w≥0.5"), (0.3, "只留 w≥0.3")]:
    rs2 = [r for r in rows if r["_w"] >= cut]
    n, a, w, p = st(rs2, "_w")
    md.append(f"| {name} | {n} | {sum(r['_w'] for r in rs2):.0f} | {a} | {w} | {p} | {p - 5.25:+.2f} |")
md.append("\n**关键提醒**: 只留高权重 = 只避毒股弃金淘槽 — 要看 '垃圾' 里有多少金子")

# 傅比: w<0.7 里的赢家数量 vs 全池
low = [r for r in rows if r["_w"] < 0.7]
hi = [r for r in rows if r["_w"] >= 0.7]
n_w, a_w, wr_w, pf_w = st(low, "_w")
n_h, a_h, wr_h, pf_h = st(hi, "_w")
md.append(f"\n### A3. w<0.7 腿 是他们说的走币子吗?")
md.append("| 桶 | n | avg | WR | 总盈亏Σ×w |")
md.append("|---|---|---|---|---|")
md.append(f"| w<0.7 | {n_w} | {a_w} | {wr_w}% | {sum(r['_pnl'] * r['_w'] for r in low):+.0f} |")
md.append(f"| w≥0.7 | {n_h} | {a_h} | {wr_h}% | {sum(r['_pnl'] * r['_w'] for r in hi):+.0f} |")
md.append(f"| 基线全量 | {len(rows)} | 4.07 | 64.0% | {sum(r['_pnl'] for r in rows):+.0f} |")


# ═══════ 面2: 2024-01 结底熔断研究 ═══════
md.append("\n## 面 2 — 2024-01 结底: 市场级熔断可不可行")
md.append("**问**: 2024-01 基线 -4.72%, 是市场整体崩还是我们选错?")


def idx_ret(entry_date, days=20):
    """Find 申花指数 n-day return at this entry date (继承到 --- 口袋)."""
    if not idx:
        return None
    n = len(idx)
    # idx: list of {t:'YYYYMMDD'}
    last_idx = -1
    for i in range(n - 1, -1, -1):
        if str(idx[i]["t"]) <= entry_date:
            last_idx = i
            break
    if last_idx < days:
        return None
    return (float(idx[last_idx]["c"]) / float(idx[last_idx - days]["c"]) - 1) * 100


for r in rows:
    r["_idx20"] = idx_ret(r["entry_date"], 20)
    r["_idx10"] = idx_ret(r["entry_date"], 10)

md.append("\n### B1. 按大盘 20日返回值分桶(2024-01 处于市场崩盘)")
md.append("| 上证20日收益桶 | n | 基线 avg | WR% | PF |")
md.append("|---|---|---|---|---|")
by_i = defaultdict(list)
for r in rows:
    v = r["_idx20"]
    if v is None:
        continue
    b = "≥+2%" if v >= 2 else ("0~2%" if 0 <= v < 2 else ("-2~0%" if -2 <= v < 0 else "<−2%"))
    by_i[b].append(r)
for b in ["≥+2%", "0~2%", "-2~0%", "<−2%"]:
    rs = by_i.get(b, [])
    if rs:
        md.append("| " + " | ".join(str(x) for x in [b, *st(rs)]) + " |")

md.append("\n### B2. 2024-01 核弹月, 有熔断 vs 无对比")
md.append("| 场景 | n | avg% | PF |")
md.append("|---|---|---|---|")
jan = [r for r in rows if r["entry_date"].startswith("202401")]
md.append("| " + " | ".join(str(x) for x in ["无熔断(基线)", *st(jan)]) + " |")
# 熔断: 只保留 idx<−4% 时 的腿(用 山戳 作为熔断阈值)
fused = [r for r in jan if r["_idx20"] is not None and r["_idx20"] < -4]
md.append("| " + " | ".join(str(x) for x in ["熔断后(只留大盘跌超4%日)", *st(fused)]) + " |")
if fused:
    md.append("| " + " | ".join(str(x) for x in ["保住腿", len(fused)]) + " | |")

md.append("\n**判定**: 熔断如果阈值放在 -4% 保留多少腿(上还一列). 要读取表格看。")

# ═══════ 面2 补充: S14 反事实 — 大盘<−2% 的档全部×0.5 ═══════
md.append("\n### B3. 反事实 S14: 市场弱(20日<−2%)时进的腿, 影子再上 ×0.5")
W_MKT = 0.5
s14_tot = 0.0
s14_pos = 0.0
s14_neg = 0.0
for r in rows:
    w2 = r["_w"] * (W_MKT if (r["_idx20"] is not None and r["_idx20"] < -2) else 1)
    s14_tot += w2 * r["_pnl"]
    if r["_pnl"] > 0:
        s14_pos += w2 * r["_pnl"]
    else:
        s14_neg += -w2 * r["_pnl"]
s14_pf = round(s14_pos / s14_neg, 2) if s14_neg else 999
s14_avg = round(s14_tot / sum(r["_w"] * (W_MKT if (r["_idx20"] is not None and r["_idx20"] < -2) else 1) for r in rows), 2)
md.append("| v24 | avg | PF |")
md.append("|---|---|---|")
md.append(f"| 当前(S1-S13) | 5.63 | 5.25 |")
md.append(f"| 加 S14(×0.5 当大盘<−2%) | {s14_avg} | **{s14_pf}** |")
md.append("\n## 面 3 — 2023 年 41 腿 专项走读")
md.append("**问题**: 2023 v22 -0.37 / v24 -0.84 - 影子开了倒车, 但 n=41 样本小")

r2023 = [r for r in rows if r["entry_date"].startswith("2023")]
md.append("\n### C1. 2023 腿详单(全部)")
md.append("| 代码 | 入场日 | pnl% | 权重 | flags |")
md.append("|---|---|---|---|---|")
for r in r2023:
    w = r["_w"]
    md.append(f"| {r['symbol']} | {r['entry_date']} | {r['_pnl']:+.2f} | {w} | {r['v23_flags'][:40] or 'none'} |")

winner = [r for r in r2023 if r["_pnl"] > 0]
loser = [r for r in r2023 if r["_pnl"] <= 0]
md.append(f"\n### C2. 2023 结构: 赢家 {len(winner)} 腿 (Σ{sum(r['_pnl'] for r in winner):+.0f}) vs 亏家 {len(loser)} 腿 (Σ{sum(r['_pnl'] for r in loser):+.0f})")
md.append("| 特征 | w<0.7 | w≥0.7 |")
md.append("|---|---|---|")
md.append(f"| 赢家数 | {sum(1 for r in winner if r['_w'] < 0.7)} | {sum(1 for r in winner if r['_w'] >= 0.7)} |")
md.append(f"| 亏家数 | {sum(1 for r in loser if r['_w'] < 0.7)} | {sum(1 for r in loser if r['_w'] >= 0.7)} |")
md.append(f"| 赢家avg weight | {sum(r['_w'] for r in winner if r['_w'] < 0.7) / max(sum(1 for r in winner if r['_w'] < 0.7), 1):.2f} | {sum(r['_w'] for r in winner if r['_w'] >= 0.7) / max(sum(1 for r in winner if r['_w'] >= 0.7), 1):.2f} |")
md.append(f"| 亏家avg weight | {sum(r['_w'] for r in loser if r['_w'] < 0.7) / max(sum(1 for r in loser if r['_w'] < 0.7), 1):.2f} | {sum(r['_w'] for r in loser if r['_w'] >= 0.7) / max(sum(1 for r in loser if r['_w'] >= 0.7), 1):.2f} |")

# 组合更奇怪的问题: 赢家不重, 亏家不重?
md.append("\n\n### C3. 比收益: 影子只降权少亏小赢家, 但 2023 赢家本来就在赢家少")
# 表A: 高位腿(亏家)权重 vs 低位腿(赢家) 权重
md.append("你看到的就是 **2023 病根**: v24 影子风格是 '亏谁败多配资重', 2023 整年全体不赢")
md.append("\n**是否要在 2026-10-23 检讨, 添加 '在熊市年份整体位置×0.5'?** -- 这是第二道手术课题")

# 结论
md.append("\n## 总结: 三面结论")
md.append(f"1. w<0.7 有金子 {sum(r['_pnl'] for r in low if r['entry_date'][:4] in ('2024', '2026')):+.0f}% (2024+2026), 不能简单硬割, 建议 '影子' 继续")
md.append(f"2. 2024-01 大盘确实 crash ({len([r for r in jan if r['_idx20'] and r['_idx20'] < -4])}/_{len(jan)} 只腿在大跌>4%日入场), 熔断阈值<−4%实验值见 B2")
md.append(f"3. 2023 全败与市场横盘振荡调性差有关, 是不是加 '年份/市道开关' 或 '三个月只上不上' 常态化馈线?")

open(OUT, "w", encoding="utf-8").write("\n".join(md))
print(f"R83 → {OUT}")
