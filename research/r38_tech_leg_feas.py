# -*- coding: utf-8 -*-
"""r38_tech_leg_feas.py —— R38 技术信号腿可行性: 全市场 SMC 扫损+FVG 候选池规模.
对 kline_cache_tencent 全部股票, 在 2026-08 一个月扫描:
  模式: ①前20日形成 swing low ②某日跌破该低点(扫损) ③次日收回低点上方
       ④收回日出现 FVG(跳空缺口) → 候选
统计候选池规模/月, 对比事件腿(2026-08 正事件数). 若技术腿候选 > 事件腿
10x → 技术腿是量少问题的规模化解法. 纯研究, 轻量(子集抽样). """
import io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
files = sorted(f for f in os.listdir(KT) if f.endswith("_daily_800.json"))
print(f"K线文件: {len(files)}")

def bars_of(path):
    raw = json.load(open(os.path.join(KT, path), encoding="utf-8"))
    bs = []
    for r in raw:
        t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
        if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
            bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]),
                       "c": float(r["c"]), "v": float(r["v"])})
    bs.sort(key=lambda b: b["t"])
    return bs

def scan_sweep_fvg(bs, start, end):
    """在 [start,end] 日期窗内找 扫损+FVG 模式. 返回候选数. """
    dates = [b["t"] for b in bs]
    cands = 0
    for i in range(20, len(bs)-1):
        d = bs[i]["t"]
        if not (start <= d <= end): continue
        # 前20日 swing low(不含最近3日)
        window = bs[max(0,i-20):i-3]
        if not window: continue
        prev_low = min(b["l"] for b in window)
        # ①跌破前低(扫损)
        if bs[i]["l"] < prev_low * 0.995:
            # ②次日收回
            if bs[i+1]["c"] > prev_low:
                # ③收回日跳空缺口(FVG): open > 前日 high
                if bs[i+1]["o"] > bs[i]["h"]:
                    cands += 1
    return cands

# 全量扫描 2026-08
total = 0
per_stock = defaultdict(int)
for path in files:
    try:
        bs = bars_of(path)
    except Exception:
        continue
    c = scan_sweep_fvg(bs, "20260801", "20260831")
    total += c
    if c: per_stock[path.split("_")[0]] = c
print(f"\n2026-08 全市场 扫损+FVG 候选: {total} 个 (涉及 {len(per_stock)} 只股票)")
print(f"对比: 2026-08 事件腿正事件(增持/回购) ≈ 178 条(公告库)")
print(f"技术腿/事件腿 ≈ {total/178:.1f}x —— 若成立, 技术腿是量少的规模化解法")

# 快速质量抽验: 这些候选 10 日收益(次日开盘买, 10日后卖)
import statistics
rets = []
for path in files:
    try: bs = bars_of(path)
    except: continue
    dates = [b["t"] for b in bs]
    for i in range(20, len(bs)-11):
        d = bs[i]["t"]
        if not ("20260801" <= d <= "20260831"): continue
        window = bs[max(0,i-20):i-3]
        if not window: continue
        prev_low = min(b["l"] for b in window)
        if bs[i]["l"] < prev_low*0.995 and bs[i+1]["c"] > prev_low and bs[i+1]["o"] > bs[i]["h"]:
            ep = bs[i+1]["o"]
            ex = bs[i+10]["c"]
            if ep > 0: rets.append((ex/ep-1)*100)
if rets:
    w = sum(1 for x in rets if x>0)
    print(f"\n技术腿候选 10日收益: n={len(rets)} avg={sum(rets)/len(rets):+.2f}% 胜率={100*w/len(rets):.1f}%")
    print(f"  (参考: 事件腿基线 avg≈+3.5%/笔, 10日持有)")
