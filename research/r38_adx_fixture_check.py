# -*- coding: utf-8 -*-
"""r38_adx_fixture_check.py —— P1-7 注释方向复核(逐 bar 对齐 + 原样复现).

R38n 发现: R38n 实测"旧版通过更多"(3788 vs 3419) 与 core/indicators.py 注释
"旧单窗 DX 系统性偏低, ADX>=20 门过严错杀边界股" **方向相反**。

可能原因(本脚本验证):
 ① r38_adx_p1_7.py 的 legacy_adx 用 range(i-14, i) —— 与 gen_v20f 一致;
    core.adx14_of 用 range(lo, i+1) —— 含 bar i。存在 1-bar 窗口差。
 ② 两版对趋势/震荡序列的方向性本来就不同(单窗 DX 在震荡时→0, 趋势时→100;
    Wilder 平滑后向中值回归) —— 因此"系统性偏低"只在部分样本成立。

方法: ① 构造趋势/震荡/常量三种合成序列, 逐 bar 对比两版;
      ② 在真实数据上按 bar 对齐(同一 i) 对比, 统计分布;
      ③ 复现注释中的样例值(0.33/5.78/5.45 vs 13.06/7.55/13.46)。
纯研究, 不修改生产。
"""
import io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
from core.indicators import adx14_of as wilder_adx

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"

def legacy_adx_aligned(bs, i):
    """gen_v20f 原样: 窗口 range(i-14, i) (不含 i), 单窗 DX."""
    if i < 30: return None
    pd = md = ts = 0.0
    for k in range(i - 14, i):
        h, l, pc = bs[k]["h"], bs[k]["l"], bs[k - 1]["c"]
        up = h - bs[k-1]["h"]; dn = bs[k-1]["l"] - l
        pd += up if (up > dn and up > 0) else 0
        md += dn if (dn > up and dn > 0) else 0
        ts += max(h-l, abs(h-pc), abs(l-pc))
    if ts <= 0: return None
    pdi = 100*pd/ts; mdi = 100*md/ts
    if pdi+mdi == 0: return None
    return 100*abs(pdi-mdi)/(pdi+mdi)

def legacy_adx_samewin(bs, i):
    """同窗口版: range(i-13, i+1) (含 i, 与 core 的末尾 n 根一致)."""
    if i < 30: return None
    pd = md = ts = 0.0
    for k in range(i - 13, i + 1):
        h, l, pc = bs[k]["h"], bs[k]["l"], bs[k-1]["c"]
        up = h - bs[k-1]["h"]; dn = bs[k-1]["l"] - l
        pd += up if (up > dn and up > 0) else 0
        md += dn if (dn > up and dn > 0) else 0
        ts += max(h-l, abs(h-pc), abs(l-pc))
    if ts <= 0: return None
    pdi = 100*pd/ts; mdi = 100*md/ts
    if pdi+mdi == 0: return None
    return 100*abs(pdi-mdi)/(pdi+mdi)

print("="*92)
print("① 合成序列: 两版 ADX 方向性检验")
print("="*92)
def synth(kind, n=80):
    out = []
    for i in range(n):
        if kind == "flat":
            o=h=l=c=10.0
        elif kind == "up":
            o=10+i; h=10.8+i; l=9.9+i; c=10.5+i
        elif kind == "chop":
            d = 1.0 if i % 2 else -1.0
            o=10; h=10.5+d; l=9.5+d; c=10+d
        elif kind == "down":
            o=90-i; h=90.2-i; l=89.2-i; c=89.5-i
        out.append({"t": f"2026{i//28+1:02d}{i%28+1:02d}", "o": o, "h": h, "l": l, "c": c, "v": 1})
    return out

print(f"{'序列':<10}{'legacy(gen_v20f窗口)':>22}{'legacy(同窗口)':>16}{'Wilder(core)':>14}")
for kind in ("flat", "up", "chop", "down"):
    bs = synth(kind)
    i = len(bs) - 1
    l1 = legacy_adx_aligned(bs, i)
    l2 = legacy_adx_samewin(bs, i)
    w = wilder_adx(bs, i)
    f = lambda x: "None" if x is None else f"{x:.2f}"
    print(f"{kind:<10}{f(l1):>22}{f(l2):>16}{f(w):>14}")

print("\n" + "="*92)
print("② 真实数据: 逐 bar 对齐对比(40 股 × 各 3 点)")
print("="*92)
files = sorted(f for f in os.listdir(KT) if f.endswith("_daily_800.json"))[:40]
pairs = []
for fn in files:
    raw = json.load(open(os.path.join(KT, fn), encoding="utf-8"))
    bs = []
    for r in raw:
        t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
        if t and r.get("o") and r.get("h") and r.get("l") and r.get("c"):
            bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"])})
    bs.sort(key=lambda b: b["t"])
    if len(bs) < 200: continue
    for i in (99, 199, len(bs)-1):
        a = legacy_adx_aligned(bs, i); b = legacy_adx_samewin(bs, i); w = wilder_adx(bs, i)
        if a is None or b is None or w is None: continue
        pairs.append((a, b, w))

if pairs:
    d1 = sorted(w - a for a, b, w in pairs)
    d2 = sorted(w - b for a, b, w in pairs)
    n = len(d1)
    print(f"样本 n={n}")
    print(f"Wilder - legacy(gen_v20f窗口): 中位 {d1[n//2]:+.2f} | 均值 {sum(d1)/n:+.2f} | "
          f"P10 {d1[n//10]:+.2f} | P90 {d1[9*n//10]:+.2f}")
    print(f"Wilder - legacy(同窗口):       中位 {d2[n//2]:+.2f} | 均值 {sum(d2)/n:+.2f} | "
          f"P10 {d2[n//10]:+.2f} | P90 {d2[9*n//10]:+.2f}")
    # 通过率(>=20)
    for label, idx in (("legacy(gen_v20f窗口)", 0), ("legacy(同窗口)", 1), ("Wilder(core)", 2)):
        pass_n = sum(1 for p in pairs if p[idx] >= 20)
        print(f"  {label:<24} >=20 通过 {pass_n}/{n} ({100*pass_n/n:.1f}%)")
    # 注释声称的样例值检索
    print("\n③ 注释样例值检索(0.33/5.78/5.45 vs 13.06/7.55/13.46):")
    hits = 0
    for a, b, w in pairs:
        for la in (0.33, 5.78, 5.45):
            if abs(a - la) < 0.6 and any(abs(w - t) < 0.8 for t in (13.06, 7.55, 13.46)):
                hits += 1
    print(f"  近似命中数: {hits} (0 = 注释样例来自其他数据集/其他 bar 定义)")

print("\n" + "="*92)
print("裁定:")
print("  若 legacy(gen_v20f窗口) 与 legacy(同窗口) 方向一致且均偏高 → 注释'系统性偏低'")
print("  在聚合意义上不成立; 若两者方向不同 → 1-bar 窗口差是主因, 需对齐后重判 R38n。")
json.dump({"pairs": len(pairs)}, open(r"E:\test\smc_project\research\r38_adx_fixture_check.json", "w", encoding="utf-8"), ensure_ascii=False)
print("\n→ r38_adx_fixture_check.json")