# -*- coding: utf-8 -*-
"""gen_v23_shadow.py — R70: v23 影子组合(预注册, 不改生产)
规则(全部 as-weight, 即只降权不删除, 记录全貌):
  s1_choch  : breakout_kind 含 CHoCH    → weight ×0.5      (病灶 P1)
  s4_rank2  : rank == 2                 → weight ×0.5      (病灶 P4)
  s5_r5min  : risk_pct < 5%             → weight ×0.6      (病灶 P5)
  s6_whale  : 入场前90日内 积极公告 1次 → ×0.7, 3+次 → ×1.2 (R72 真金验证)
基线 = v22 冻结 1858 腿; v23 = 同腿 × 权重; 统计对比即可。
纪律: 不修改 v22 任何文件; v23 仅生成 combo_v23_shadow.csv + 统计。
"""
import csv, os, json, sqlite3, sys
from collections import defaultdict
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import config as CFG  # noqa: E402
from core.events import classify_title  # noqa: E402

SRC = os.path.join(ROOT, "combo_v22_trades.csv")
OUT = os.path.join(ROOT, "combo_v23_shadow.csv")
MD = os.path.join(ROOT, "handover", "R76_smc_full_audit.md")  # (旁注)
ENR_CSV = os.path.join(ROOT, "combo_v22_smc_full.csv")  # R76 产物


def _load_smc_env():
    """载入 R76 腿的 sweep_dir / dist_to_bsl"""
    m = {}
    if os.path.exists(ENR_CSV):
        for r in csv.DictReader(open(ENR_CSV, encoding="utf-8-sig")):
            m[r["symbol"] + "|" + r["entry_date"]] = r
    return m


SMC_ENV = _load_smc_env()

W_CHOCH = 0.5
W_RANK2 = 0.5
W_RISK_LT5 = 0.6
W_WHALE_3PLUS = 1.2   # 3+ 次积极公告 → 加权
W_WHALE_ONCE = 0.7    # 只披露 1 次 → 降权 (R72: 2.03/2.19 PF)
W_UP_TREND = 0.7      # 用户 2026-09-23 验收: up 趋势腿降权 (R69 D1: up PF 2.43 vs down 4.23)
W_SWEEP_BEAR = 0.6    # S8 (用户验收 R76): 入场近10bar有 bear sweep → 降权 (R76: 244腿 avg+1.46 PF2.02)
W_BSL_TIGHT = 0.7     # S9 (用户验收 R76): 入场贴近被攻克 BSL (<5%) → 降权 (R76: 354腿 avg~+1.0 PF~1.6)
W_IN_OB = 0.8         # S10 (R77, 用户拍板"要检查就要修"): 入场价 sedari 最近 OB 区 → 降权 (312腿 +2.59 PF2.53 vs 外 4.01)
W_MSS_BULL_FRESH = 0.7  # S11 (R78): 近2bar内 bull MSS 刚确认反转 → 追高界 → 降权 (57腿 ~PF1.4)
W_IN_OTE = 0.7        # S12 (R79): 入场价在最近脉冲的 OTE 61.8-79% 内 → 降权 (141腿 +1.72 PF1.87)
W_RANK_VR2_VC = 0.7   # S13 (R81): rank 分量 vr2 或 vol_cont 携带 → 降权 (vr2:135腿−2.82pp / vol_cont:139腿−1.20pp)
W_MKT_WEAK = 0.5      # S14 (R83 用户验收): 上证指数20日 < −2% 时入场 → 降权 (桶<−2%: 529腿 avg2.51/PF2.11 vs ≥+2%: 847腿 avg5.99/PF5.92)

IDX_JSON = os.path.join(ROOT, "idx_sh000001.json")  # 真上证指数(2023-01→2026-09, 904 bars)


def _load_idx():
    if os.path.exists(IDX_JSON):
        return json.load(open(IDX_JSON, encoding="utf-8"))
    return []


_IDX = _load_idx()


def _idx20(entry_date):
    """入场日的上证20日收益%. 无前视: 只用到当日闭市."""
    d = str(entry_date).replace("-", "")
    j = -1
    for i in range(len(_IDX) - 1, -1, -1):
        if str(_IDX[i]["t"]) <= d:
            j = i
            break
    if j < 20:
        return None
    return (float(_IDX[j]["c"]) / float(_IDX[j - 20]["c"]) - 1) * 100
W_RANK_VR2_VC = 0.7   # S13 (R81): rank 分量 vr2(放量追入)/vol_cont(量能持续) 负贡献 → 其中一个=1 即×0.7

V24_RULES = True  # 2026-09-23 用户定: 全部入影子生产打标


def _whale_counts(legs):
    conn = sqlite3.connect(CFG.ANNOUNCE_DB)
    by_code = defaultdict(list)
    for d, c, t in conn.execute("SELECT date, stock_code, title FROM announce"):
        is_ev, kind, pol, amt, pct = classify_title(t)
        if is_ev and pol > 0:
            by_code[c].append((d, kind))
    m = {}
    for r in legs:
        code = r["symbol"].split("_")[0].split(".")[0]
        d0 = datetime.strptime(r["entry_date"], "%Y%m%d")
        lo, hi = (d0 - timedelta(days=90)).strftime("%Y-%m-%d"), d0.strftime("%Y-%m-%d")
        n = sum(1 for a in by_code.get(code, []) if lo <= a[0] <= hi)
        m[r["symbol"] + "|" + r["entry_date"]] = n
    return m


def st(rows, wkey=None):
    n = len(rows)
    tw = sum(r[wkey] for r in rows) if wkey else n
    if not n or tw == 0:
        return n, round(tw, 1), 0, 0, 0
    if wkey:
        p = [float(r["net_pnl_pct"] or 0) * r[wkey] for r in rows]
    else:
        p = [float(r["net_pnl_pct"] or 0) for r in rows]
    avg = sum(p) / tw
    wr = sum(r[wkey] if wkey else 1 for r, v in zip(rows, p) if v > 0) / tw * 100
    pos = sum(v for v in p if v > 0)
    neg = -sum(v for v in p if v < 0)
    return n, round(tw, 1), round(avg, 2), round(wr, 1), round(pos / neg, 2) if neg else 999


rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
whale = _whale_counts(rows)
for r in rows:
    w = 1.0
    flags = []
    if "CHoCH" in (r.get("breakout_kind") or ""):
        w *= W_CHOCH; flags.append("s1_choch")
    if str(r.get("rank")) == "2":
        w *= W_RANK2; flags.append("s4_rank2")
    try:
        if float(r.get("risk_pct") or 0) < 5:
            w *= W_RISK_LT5; flags.append("s5_risk_lt5")
    except Exception:
        pass
    if r.get("src") == "EVENT":
        n_ev = whale.get(r["symbol"] + "|" + r["entry_date"], 1)
        r["whale_90d_n"] = n_ev
        if n_ev >= 3:
            w *= W_WHALE_3PLUS; flags.append("s6_whale_multi")
        elif n_ev <= 1:
            w *= W_WHALE_ONCE; flags.append("s6_whale_once")
    else:
        r["whale_90d_n"] = None
    # S7 (用户验收 2026-09-23): up 趋势腿 ×0.7 — up 系整体 PF 2.43 vs down 4.23
    if (r.get("trend_state") or "") == "up":
        w *= W_UP_TREND; flags.append("s7_up_trend")
    # S8/S9 (R76 用户验收): sweep 方向 + dist_to_bsl (源: combo_v22_smc_full.csv)
    enr = SMC_ENV.get(r["symbol"] + "|" + r["entry_date"])
    if enr:
        if enr.get("sweep_dir") == "bear":
            w *= W_SWEEP_BEAR; flags.append("s8_sweep_bear")
        d = enr.get("dist_to_bsl")
        try:
            if d is not None and float(d) < 5:
                w *= W_BSL_TIGHT; flags.append(f"s9_bsl_tight_{d}%")
        except Exception:
            pass
    # S10 (R77): 入价在最近 OB 区内 → 降权
    if enr and str(enr.get("in_ob")) == "True":
        w *= W_IN_OB; flags.append("s10_in_ob")
    # S11 (R78): 近2bar 内 bull MSS 刚确认 → 追高界 → 降权
    try:
        if enr and enr.get("mss_dir") == "bull" and int(enr.get("mss_bars_ago") or 999) <= 2:
            w *= W_MSS_BULL_FRESH; flags.append(f"s11_mss_bull@{enr['mss_bars_ago']}")
    except Exception:
        pass
    # S12 (R79): 入场价在 OTE 61.8-79% 回测带内(蝶形) → 降权
    if enr and str(enr.get("in_ote")) == "True":
        w *= W_IN_OTE; flags.append("s12_in_ote")
    # S13 (R81): rank 分量 vr2/vol_cont 出现 → 负贡献 → ×0.7
    try:
        _rc = json.loads(r.get("rank_components") or "{}") if r.get("rank_components") else {}
        if _rc.get("vr2") == 1 or _rc.get("vol_cont") == 1:
            w *= W_RANK_VR2_VC
            flags.append("s13_rank_" + ("vr2" if _rc.get("vr2") else "vol_cont"))
    except Exception:
        pass
    # S14 (R83): 大盘弱(上证20日 < −2%) 时降权
    m20 = _idx20(r["entry_date"])
    if m20 is not None and m20 < -2:
        w *= W_MKT_WEAK; flags.append(f"s14_mkt_weak_{m20:.1f}%")
    r["v23_weight"] = round(w, 3)
    r["v23_flags"] = "|".join(flags) or "none"

cols = list(rows[0].keys())
with open(OUT, "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)

print(f"v23 影子 legs: {len(rows)}")
print(f"含规则标记者: {sum(1 for r in rows if r['v23_flags'] != 'none')} 腿({sum(1 for r in rows if r['v23_flags'] != 'none')/len(rows)*100:.0f}%)")
print()
print("| 版本 | n | Σw | avg% | WR% | PF |")
print("|---|---|---|---|---|---|")
print("| v22 基线 |", " | ".join(str(x) for x in st(rows)), "|")
print("| v23 影子(加权) |", " | ".join(str(x) for x in st(rows, "v23_weight")), "|")
print()
print("逐年:")
by_y = defaultdict(list)
for r in rows:
    by_y[r["entry_date"][:4]].append(r)
print("| 年 | v22 avg/PF | v23 avg/PF |")
print("|---|---|---|")
for y in sorted(by_y):
    b = st(by_y[y]); v = st(by_y[y], "v23_weight")
    print(f"| {y} | {b[2]}%/PF {b[4]} | {v[2]}%/PF {v[4]} |")
