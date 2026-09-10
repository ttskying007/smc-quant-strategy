# -*- coding: utf-8 -*-
"""v4_d4_reclaim_off.py —— V4 D4①: RECLAIM 简化链 6000+ 笔全对照
预注册: 简化链 vs 完整链 全市场对照, |Δavg|>0.5pp → 简化作废(Family DB 结论不成立);
        |Δ|≤0.5pp → 简化采纳(RECLAIM 层从生产链移除, 链提速 ~20%)。
同 settle_from_record 统一退出(同 v3_full_replay_review 口径, 可直接对照其 6003 笔基准)。"""
import glob, io, json, os, sys, time
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from core.sequence import run_sequence_v2
from core.entry import fill_in_zone
from core.setup_exit import settle_from_record, EXIT_VERSION

KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
FEE = 0.2
OOS = "20250701"
FILES = sorted(glob.glob(KL + os.sep + "*_daily_800.json"))[::2]

def load_daily(fp):
    raw = json.load(open(fp, encoding="utf-8"))
    return [{"t": str(b.get("t"))[:8], "o": float(b["o"]), "h": float(b["h"]),
             "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v") or 0)} for b in raw]

def collect(require_reclaim):
    trades = []
    for fp in FILES:
        try:
            dd = load_daily(fp)
        except Exception:
            continue
        if len(dd) < 200:
            continue
        code = os.path.basename(fp).split("_")[0]
        n = len(dd)
        for i in range(150, n - 25):
            try:
                m = run_sequence_v2(dd, i, symbol=code, require_reclaim=require_reclaim)
                s = m.setup()
            except Exception:
                continue
            if s is None:
                continue
            poi = s["poi"]
            zone = {"zone_low": poi["low"], "zone_high": poi["high"],
                    "invalid_price": poi["low"] * 0.97, "optimal_entry": poi["mid"]}
            try:
                fill = fill_in_zone(dd, i, zone, max_bars=5, fill_mode="STRICT_LIMIT")
            except Exception:
                continue
            if fill is None or fill.get("fill_price") is None:
                continue
            res = settle_from_record(dd, fill["fill_idx"], fill["fill_price"],
                                     zone["invalid_price"], fee_pct=FEE)
            if res.get("status") in ("SL", "TP", "TIME"):
                trades.append((dd[i]["t"], res["ret_pct"]))
    return trades

def stats(pnl, oos_only=False):
    v = [p for d, p in pnl if (not oos_only or d >= OOS)]
    if not v:
        return {"n": 0}
    w = sum(x for x in v if x > 0); l = abs(sum(x for x in v if x <= 0))
    return {"n": len(v), "avg": round(sum(v) / len(v), 3),
            "wr": round(len([x for x in v if x > 0]) / len(v) * 100, 1),
            "pf": round(w / l, 2) if l else 99.0}

t0 = time.time()
CACHE_FULL = r"E:\test\smc_project\research\handover\v4_d4_full_cache.json"
if os.path.exists(CACHE_FULL):
    full = [tuple(x) for x in json.load(open(CACHE_FULL, encoding="utf-8"))]
    print(f"完整链缓存命中: {len(full)} 笔")
else:
    print("跑完整链(require_reclaim=True)...")
    full = collect(True)
    json.dump(full, open(CACHE_FULL, "w", encoding="utf-8"))
    print(f"  {len(full)} 笔, {time.time()-t0:.0f}s")
print("跑简化链(require_reclaim=False)...")
simp = collect(False)
print(f"  {len(simp)} 笔, {time.time()-t0:.0f}s")

sf, ss = stats(full), stats(simp)
sf_oos, ss_oos = stats(full, True), stats(simp, True)
delta_all = round(ss["avg"] - sf["avg"], 3)
delta_oos = round(ss_oos["avg"] - sf_oos["avg"], 3)

# 完整链应与 v3_full_replay_review 基准一致(6003笔) —— 一致性校验
base = json.load(open(r"E:\test\smc_project\research\handover\V3修正后全面回测复盘.json",
                      encoding="utf-8"))
base_n = base["total"]["all"]["n"]
consistent = abs(sf["n"] - base_n) <= 3

out = {"full_chain": {"all": sf, "oos": sf_oos},
       "simplified_chain": {"all": ss, "oos": ss_oos},
       "delta_avg_pp": {"all": delta_all, "oos": delta_oos},
       "baseline_consistency": {"v3_replay_n": base_n, "this_run_n": sf["n"], "ok": consistent},
       "preregistered_verdict": ("简化作废(Δ超0.5pp)" if abs(delta_all) > 0.5 or abs(delta_oos) > 0.5
                                  else ("简化采纳(Δ在线内)" if ss["n"] >= sf["n"] * 0.9
                                        else "简化作废(候选损失>10%)")),
       "exit_version": EXIT_VERSION}
json.dump(out, open(r"E:\test\smc_project\research\handover\V4_D4_RECLAIM简化.json", "w",
                    encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"\n完整链: 全期 {sf} / OOS {sf_oos}")
print(f"简化链: 全期 {ss} / OOS {ss_oos}")
print(f"Δavg: 全期 {delta_all}pp / OOS {delta_oos}pp")
print(f"基准一致性(v3回放 {base_n} vs 本次 {sf['n']}): {'OK' if consistent else 'MISMATCH!'}")
print(f"预注册判定: {out['preregistered_verdict']}")
print("已写 handover/V4_D4_RECLAIM简化.json")