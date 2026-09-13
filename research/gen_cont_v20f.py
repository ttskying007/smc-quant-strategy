# -*- coding: utf-8 -*-
"""gen_cont_v20f.py —— P2-1b: 延续腿 CSV 生成器。

FIX(2026-09-13, 第八轮审计 5.8) —— 重写移除三类泄漏(原实现延续腿历史结果不能
作为有效 OOS 证据):
  ① 未来数据(entry 日过滤): 原用 entry_idx=i+1 的 close/volume 算 VWAP、用
     entry 日窗口算 vol20 —— 决策时点(信号收盘后)这些数据不可知。改为全部
     用 signal 日(=i)及以前: VWAP 窗 [i-19, i], vol20 窗 [i-20, i)。
  ② 全局最新阈值(V_MED 回看历史): 原用每只股票"当前文件末端20日"波动构造
     全市场 V_MED 再应用到所有历史信号 —— 当前状态阈值回看历史。改为逐信号
     滚动截面: 每个信号日的全市场(已扫文件)20日波动中位数, 只含该日及以前
     数据; 两阶段扫描(先收集所有(signal日, vol20)对, 再按日聚合中位数)。
  ③ 口径统一: VWAP 阈值 0.09 → 0.10(与 continuation_scanner/sub_signals_cont
     一致, R13 修复的生产口径)。

退出: 保持原固定 10 交易日收盘退出(net=10日收益−FEE 0.2 双边) —— 退出语义
不属于本轮泄漏修复范围(属于 P1-6 成本模型统一批次), 不动。
产出: cont_v20f_new.csv(字段不变, 前端兼容)。
"""
import csv, io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
PIVOT = 3

def bars(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
            out.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"]), "v": float(r["v"])})
    out.sort(key=lambda b: b["t"])
    return out


def is_swing_low(bs, j):
    if j < PIVOT or j + PIVOT >= len(bs):
        return False
    return bs[j]["l"] < min(bs[k]["l"] for k in range(j - PIVOT, j)) and bs[j]["l"] <= min(bs[k]["l"] for k in range(j + 1, j + PIVOT + 1))


def stage_of(bs, i):
    if i < 61:
        return None
    w60 = bs[i - 60:i]
    ret60 = w60[-1]["c"] / w60[0]["c"] - 1
    v20 = sum(x["v"] for x in bs[i - 20:i]) / 20
    v60 = sum(x["v"] for x in bs[i - 60:i]) / 60
    vt = v20 / v60 if v60 else 1
    if ret60 < -0.15 and vt < 0.9:
        return "ACCUM"
    if ret60 > 0.30 and vt > 1.3:
        return "DISTRIB"
    if ret60 > 0.20 and vt > 1.1:
        return "MARKUP"
    return "UPTREND" if ret60 > 0 else "DOWNTREND"


# ---- 阶段 1: 扫描全部候选(不阈值过滤), 收集 (signal日, vol20) 供逐日截面 ----
# vol20 = [i-20, i) 窗口日均真实波幅(全部为 signal 日以前数据, 无未来)
cands_raw = []
for p in sorted(os.listdir(KT)):
    if not p.endswith("_daily_800.json"):
        continue
    code = p.replace("_daily_800.json", "")
    daily = bars(os.path.join(KT, p))
    if len(daily) < 400:
        continue
    for i in range(80, len(daily) - 11):
        entry_idx = i + 1
        if entry_idx + 11 >= len(daily) or entry_idx < 130:
            continue
        if daily[entry_idx]["t"] < "20230901":
            continue
        st = stage_of(daily, i)
        if st != "MARKUP":
            continue
        sl_idx = None
        for j in range(i, PIVOT - 1, -1):
            if is_swing_low(daily, j):
                sl_idx = j
                break
        if sl_idx is None:
            continue
        if (i - sl_idx) > 5:
            continue
        if not (daily[i]["l"] <= daily[sl_idx]["l"] * 1.01 and daily[i - 1]["c"] > daily[sl_idx]["l"]):
            continue
        if daily[i]["c"] <= daily[sl_idx]["l"]:
            continue
        ep = daily[entry_idx]["o"]
        if daily[sl_idx]["l"] >= ep:
            continue
        # R17(第八轮 5.8①): VWAP 只用 signal 日及以前 [i-19, i]
        pv = sum(daily[k]["c"] * daily[k]["v"] for k in range(i - 19, i + 1))
        vol = sum(daily[k]["v"] for k in range(i - 19, i + 1))
        if vol <= 0:
            continue
        vw = pv / vol
        vw_gap = (daily[i]["c"] - vw) / vw
        # R17(第八轮 5.8③): 阈值 0.09 → 0.10(生产口径统一, R13)
        if vw_gap < 0.10:
            continue
        # R17(第八轮 5.8①): vol20 窗口 [i-20, i)(signal 日以前, 不含 entry)
        w20 = daily[i - 20:i]
        vol20 = sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20 if len(w20) == 20 else None
        if vol20 is None:
            continue
        # 收益在阶段3回填(需逐日 V_MED 阈值后判定); 此处存回填所需数据
        cands_raw.append({
            "code": code, "sym": code + (".SH" if code.startswith("6") else ".SZ"),
            "entry_idx": entry_idx, "entry_date": daily[entry_idx]["t"],
            "signal_date": daily[i]["t"], "ep": ep, "vol20": vol20,
            "exit_c": daily[entry_idx + 10]["c"],  # R17: 阶段1直接存退出收盘(同一遍历, 消除二次读盘的索引不一致面)
        })

# ---- 阶段 2: 逐 signal 日滚动截面中位数(只含该日已出现的候选, 无未来) ----
# R17(第八轮 5.8②): 原全局 V_MED 用"当前文件末端20日"构造再回看历史 —— 当前
# 状态阈值泄漏。改为: 对每个 signal 日 d, 用"signal 日 <= d 的全部候选 vol20"
# 的中位数作为该日阈值。历史日的阈值只由该日及以前的市场状态决定。
from collections import defaultdict
by_day = defaultdict(list)
for c in cands_raw:
    by_day[c["signal_date"]].append(c)
days_sorted = sorted(by_day)
vmed_by_day = {}
_running = []
for d in days_sorted:
    _running.extend(by_day[d])
    _running.sort(key=lambda x: x["vol20"])
    vmed_by_day[d] = _running[len(_running) // 2]["vol20"]

# ---- 阶段 3: 应用逐日 V_MED 阈值并回填收益(固定 10 交易日收盘退出, −FEE 0.2 双边) ----
out_rows = []
for d in days_sorted:
    for c in by_day[d]:
        if c["vol20"] >= vmed_by_day[d]:
            continue
        net = round((c["exit_c"] / c["ep"] - 1) * 100 - 0.20, 4)
        out_rows.append({"symbol": c["sym"], "entry_date": c["entry_date"],
                         "src": "CONT", "net_pnl_pct": net})
out_rows.sort(key=lambda r: r["entry_date"])

with open(r"E:\test\smc_project\research\cont_v20f_new.csv", "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["symbol", "entry_date", "src", "net_pnl_pct"])
    w.writeheader()
    for s in out_rows:
        w.writerow(s)

_n = len(out_rows)
_avg = sum(r["net_pnl_pct"] for r in out_rows) / _n if _n else 0
_wins = [r for r in out_rows if r["net_pnl_pct"] > 0]
_pf = (sum(r["net_pnl_pct"] for r in _wins) /
       abs(sum(r["net_pnl_pct"] for r in out_rows if r["net_pnl_pct"] <= 0))
       if any(r["net_pnl_pct"] <= 0 for r in out_rows) else 99)
print(f"新延续腿 CSV(R17 因果修复): {len(out_rows)} 笔 → cont_v20f_new.csv")
print(f"  signal日口径+逐日截面V_MED+阈值10% | avg={_avg:+.2f}% PF={_pf:.2f}")
print(f"  与旧版(泄漏)对照见 handover; 旧结果不再作为 OOS 证据(审计 §5.8)")