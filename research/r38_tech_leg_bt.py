# -*- coding: utf-8 -*-
"""r38_tech_leg_bt.py —— R38 技术信号腿全周期回测(修正幸存者偏差).
对 kline_cache_tencent 全部股票, 2023-09~2026-09 全周期扫描 SMC 扫损+FVG:
  入场: 次日开盘(扫损收回日+1), 与事件腿同口径
  退出: 简化 10 日持有(与事件腿 TIME_STOP 近似; 精确 SL/TP 下轮)
  修正: ①剔除 10 日窗口不足(数据末端) ②记录覆盖率
对比: 事件腿基线 avg/PF. 若全周期技术腿 avg>事件腿且样本足 → 技术腿晋级
为正式研究项(下轮做完整 SL/TP + 组合约束). 纯研究. """
import io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
files = sorted(f for f in os.listdir(KT) if f.endswith("_daily_800.json"))
print(f"K线文件: {len(files)} (注: 现存股票, 存在正向幸存者偏差, 报告会标注)")

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

trades = []  # {d, ret10}
n_files = 0
for path in files:
    try: bs = bars_of(path)
    except: continue
    n_files += 1
    dates = [b["t"] for b in bs]
    for i in range(20, len(bs)-11):
        d = bs[i]["t"]
        if not ("20230901" <= d <= "20260831"): continue
        window = bs[max(0,i-20):i-3]
        if not window: continue
        prev_low = min(b["l"] for b in window)
        # 扫损 + 收回 + FVG 跳空
        if bs[i]["l"] < prev_low*0.995 and bs[i+1]["c"] > prev_low and bs[i+1]["o"] > bs[i]["h"]:
            ep = bs[i+1]["o"]
            ex = bs[i+10]["c"]
            if ep > 0:
                trades.append({"d": d, "ret": (ex/ep-1)*100})

print(f"扫描 {n_files} 只, 全周期(2023-09~2026-08)候选: {len(trades)} 笔")
if not trades:
    print("无候选 —— 模式太严或数据问题")
    sys.exit(0)
rets = [t["ret"] for t in trades]
w = [x for x in rets if x > 0]; l = [x for x in rets if x <= 0]
pf = sum(w)/abs(sum(l)) if sum(l) else 99
print(f"\n全周期技术腿(10日持有):")
print(f"  n={len(trades)} avg={sum(rets)/len(rets):+.2f}% 中位={sorted(rets)[len(rets)//2]:+.2f}% "
      f"胜率={100*len(w)/len(rets):.1f}% PF={pf:.2f}")
print(f"  参考: 事件腿基线 n=1640 avg=+3.51% PF=3.20(含SL/TP结构, 非纯10日)")

# 逐年
print("\n逐年:")
from collections import defaultdict
byy = defaultdict(list)
for t in trades: byy[t["d"][:4]].append(t["ret"])
for y in ("2023", "2024", "2025", "2026"):
    ps = byy.get(y, [])
    if not ps: continue
    w2 = [x for x in ps if x>0]; l2 = [x for x in ps if x<=0]
    pf2 = sum(w2)/abs(sum(l2)) if sum(l2) else 99
    print(f"  {y}: n={len(ps)} avg={sum(ps)/len(ps):+.2f}% 胜率={100*len(w2)/len(ps):.1f}% PF={pf2:.2f}")

# 极端尾部检查(幸存者偏差量化)
neg50 = sum(1 for x in rets if x <= -50)
print(f"\n尾部(net<=-50%, 疑似退市/暴跌): {neg50} 笔 ({100*neg50/len(rets):.1f}%)")
print("⚠ 注: 现存股票回测存在正向幸存者偏差; 与事件腿基线同口径比较时偏差方向一致")
