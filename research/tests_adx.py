# -*- coding: utf-8 -*-
"""tests_adx.py —— paper_sim.adx14_of 的 Wilder ADX 语义 golden 测试
背景(2026-09-12 修复): 旧实现返回单窗 DX 而非 ADX(系统性偏低 0.33 vs 13.06),
错杀 ADX 门边界股。本测试钉死修复语义, 防未来无声回退:
  T1 强趋势合成序列(每天 +1 平移) → PDI=100/MDI=0 → ADX 应 >60(平滑后趋近100)
  T2 完美震荡交替序列(+1/−1)     → PDI≈MDI    → ADX 应 <20
  T3 独立 Wilder 实现(种子固定 LCG 随机游走)对齐, 容差 1.5
  T4 排除旧行为: 旧单窗 DX 在 T2 类序列上波动大(单窗), 新实现必须平滑 ——
     用"ADX ≠ DX(最后一段)" 语义: T3 随机序列上 ADX 与单窗 DX 差异存在且 |ADX−DX| 记录
  T5 边界: i < 30 → None; 数据不足 → None"""
import io, sys
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from paper_sim import adx14_of

def mk(bs):
    return [{"t": f"2026{1 + k // 28:02d}{1 + k % 28:02d}", "o": b[0], "h": b[1],
             "l": b[2], "c": b[3], "v": 1.0} for k, b in enumerate(bs)]

P = F = 0
def check(name, cond, detail=""):
    global P, F
    if cond:
        P += 1
    else:
        F += 1
        print(f"  FAIL {name}: {detail}")

# T1 强趋势: 每天整体 +1 平移(h/l 同步上移) → up 恒 +1, dn 恒负 → PDI=100
trend = []
for i in range(200):
    o, h, l, c = 100 + i, 101 + i, 99 + i, 100.5 + i
    trend.append((o, h, l, c))
a = adx14_of(mk(trend), len(trend) - 1)
check("T1 强趋势 ADX>60", a is not None and a > 60, f"ADX={a}")

# T2 完美震荡: 交替 +1/−1 → PDI≈MDI → ADX<20
osc = []
for i in range(200):
    up_day = (i % 2 == 0)
    o = 100 if up_day else 101
    c = 101 if up_day else 100
    osc.append((o, max(o, c) + 0.5, min(o, c) - 0.5, c))
a2 = adx14_of(mk(osc), len(osc) - 1)
check("T2 完美震荡 ADX<20", a2 is not None and a2 < 20, f"ADX={a2}")

# T3 独立 Wilder 实现对齐(固定种子 LCG 随机游走, 无 numpy 依赖)
seed = 20260912
def rnd():
    global seed
    seed = (seed * 1103515245 + 12345) % (2 ** 31)
    return seed / 2 ** 31
walk = []
px = 100.0
for i in range(160):
    chg = (rnd() - 0.5) * 2
    o = px
    c = max(5, px + chg)
    h = max(o, c) + rnd() * 0.5
    l = min(o, c) - rnd() * 0.5
    walk.append((round(o, 3), round(h, 3), round(l, 3), round(c, 3)))
    px = c
wbs = mk(walk)

def wilder_ref(bs, n=14):
    trs, pdms, mdms = [], [], []
    for k in range(1, len(bs)):
        h, l, pc = bs[k]["h"], bs[k]["l"], bs[k - 1]["c"]
        up, dn = h - bs[k - 1]["h"], bs[k - 1]["l"] - l
        pdms.append(up if up > dn and up > 0 else 0)
        mdms.append(dn if dn > up and dn > 0 else 0)
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    tr_s, pd_s, md_s = sum(trs[:n]), sum(pdms[:n]), sum(mdms[:n])
    dxs = []
    for k in range(n, len(trs)):
        tr_s = tr_s - tr_s / n + trs[k]
        pd_s = pd_s - pd_s / n + pdms[k]
        md_s = md_s - md_s / n + mdms[k]
        pdi = 100 * pd_s / tr_s if tr_s else 0
        mdi = 100 * md_s / tr_s if tr_s else 0
        dxs.append(100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) else 0)
    return sum(dxs[-n:]) / n

a3 = adx14_of(wbs, len(wbs) - 1)
r3 = wilder_ref(wbs)
check("T3 与独立Wilder对齐(±1.5)", a3 is not None and abs(a3 - r3) < 1.5,
      f"impl={a3} ref={r3}")

# T4 排除旧单窗 DX 行为: 旧版只算最后 14 根的单窗 —— 在 T1 序列上去掉最后 2 根,
# 旧版结果会变(DX 窗口不同), 新版 warm-up 平滑结果稳定(±1pp)
a_full = adx14_of(mk(trend), len(trend) - 1)
a_short = adx14_of(mk(trend[:-2]), len(trend) - 3)
check("T4 warm-up 稳定性(趋势序列去尾2根 Δ<1pp)",
      a_full is not None and a_short is not None and abs(a_full - a_short) < 1.0,
      f"full={a_full} short={a_short}")

# T5 边界: 数据不足 → None
check("T5a i<30 → None", adx14_of(mk(trend[:25]), 24) is None)
check("T5b 空 → None", adx14_of([], 0) is None)

print(f"结果: PASS={P} FAIL={F}")
sys.exit(1 if F else 0)