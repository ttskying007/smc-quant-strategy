# -*- coding: utf-8 -*-
"""v4_escore_backfill_full.py —— E-score 全历史回填(一次性, V3-D S3 样本扩容)
瓶颈: escore_history 60 日滚动 → 结构腿×E 交叉 high 组仅 n=20(<30 PRELIMINARY)。
本脚本: bar 级 20D 新高标志一次预计算 → 逐日 O(1) 聚合 F1 → 全历史 E 数秒完成。
输出: handover/escore_history_full.json(全历史, 研究用; 60 日滚动版保持生产职责)。
覆盖: K 线缓存起点(2023-04)~最新; F2/F3 指数 canonical 全量。
幂等: 已有 full 文件则只补缺日。"""
import glob, io, json, os, sys, time
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
ETF = r"E:\test\smc_project\hermes\kline_cache_etf"
FULL = r"E:\test\smc_project\research\handover\escore_history_full.json"
MIN_SAMPLE = 200
_t0 = time.time()

# ---- ① bar 级 20D 新高标志: 逐文件一次, 聚合 date → (hits, n) ----
agg = {}          # d8 -> [hits, total]
n_files = 0
for fp in sorted(glob.glob(os.path.join(KL, "*_daily_800.json"))):
    try:
        raw = json.load(open(fp, encoding="utf-8"))
    except Exception:
        continue
    if len(raw) < 25:
        continue
    n_files += 1
    cl = [(str(b.get("t"))[:8], float(b["c"])) for b in raw if b.get("t")]
    cl.sort()
    # 每 bar 的 20D 新高(回看 20 根, 与 core.escore.breadth_newhigh_pct 同语义)
    stack_hi = []
    for k in range(20, len(cl)):
        d8, c = cl[k]
        win_max = max(x[1] for x in cl[k - 20:k])
        a = agg.setdefault(d8, [0, 0])
        a[1] += 1
        if c >= win_max:
            a[0] += 1
print(f"① bar级聚合: {n_files} 文件 → {len(agg)} 交易日 ({time.time()-_t0:.0f}s)")

# ---- ② 指数(512100 中证1000 + 上证) ----
def load_idx(fname):
    fp = os.path.join(ETF, fname)
    if not os.path.exists(fp):
        return []
    j = json.load(open(fp, encoding="utf-8"))
    bars = j if isinstance(j, list) else j.get("data") or []
    out = [(str(b.get("t"))[:10].replace("-", ""), float(b["c"])) for b in bars if b.get("t")]
    out.sort()
    return out

mid = load_idx("SH_512100_daily.json") or load_idx("512100_SH_day.json")
sh = load_idx("SH_000001_daily.json") or load_idx("000001_SH_day.json")

def idx_at(arr, d8, days=20):
    w = [x for x in arr if x[0] <= d8]
    if len(w) < days + 1:
        return None
    return {"r20": w[-1][1] / w[-1 - days][1] - 1,
            "off_high": w[-1][1] / max(x[1] for x in w[-days * 3:]) - 1}

# ---- ③ 全历史 E ----
hist = {"version": "escore_v1", "days": []}
if os.path.exists(FULL):
    try:
        hist = json.load(open(FULL, encoding="utf-8"))
    except Exception:
        hist = {"version": "escore_v1", "days": []}
known = {d.get("d8") for d in hist.get("days", [])}
n_new = 0
for d8 in sorted(agg):
    if d8 in known:
        continue
    hit, tot = agg[d8]
    if tot < MIN_SAMPLE:
        continue
    f1 = hit / tot
    m2 = idx_at(mid, d8)
    s3 = idx_at(sh, d8)
    if not m2 or not s3:
        continue
    e = 0.4 * min(1, max(0, f1 / 0.15)) \
        + 0.4 * min(1, max(0, -m2["off_high"] / 0.10)) \
        + 0.2 * min(1, max(0, s3["r20"] / 0.05))
    coef = (0.3 if e < 0.33 else 0.5 if e < 0.44 else 0.75 if e < 0.54 else 1.0)
    hist["days"].append({"d8": d8, "e": round(e, 4), "f1": round(f1, 4),
                         "f2": round(m2["off_high"], 4), "f3": round(s3["r20"], 4),
                         "mid_proxy": "512100",
                         "exposure_coef": coef,
                         "n_sample": tot,
                         "backfilled_full": True})
    n_new += 1
hist["days"].sort(key=lambda d: d["d8"])
json.dump(hist, open(FULL, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
days = hist["days"]
es = [d["e"] for d in days]
oos = [d for d in days if d["d8"] >= "20250701"]
print(f"②③ 全历史 E: 新增 {n_new} 日, 总 {len(days)} 日 "
      f"({days[0]['d8']}~{days[-1]['d8']}), OOS期 {len(oos)} 日 ({time.time()-_t0:.0f}s)")
print(f"   E 分布: min={min(es)} 中位={sorted(es)[len(es)//2]} max={max(es)}")
print("已写 handover/escore_history_full.json")