# -*- coding: utf-8 -*-
"""escore_daily.py —— E-score 每日快照累积器(D1 SHADOW 双臂前置)
每日(调度): 计算当日全市场广度 F1 + E → 追加 handover/escore_history.json(60日滚动)。
PAPER/SHADOW 消费方每日读最新快照, 不再各自全市场慢扫(单源)。
另: 对 PAPER 台账全部信号补当日 E 标注(下一交易日重估用)。"""
import io, json, os, sys, time
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from core.escore import escore_for_date, breadth_newhigh_pct, exposure_coef, _version_

HIST = r"E:\test\smc_project\research\handover\escore_history.json"
KEEP = 60

hist = {"days": [], "version": _version_}
if os.path.exists(HIST):
    try:
        hist = json.load(open(HIST, encoding="utf-8"))
    except Exception:
        pass

# 当日 = K线缓存最新交易日(从任一文件尾部读, 不假设今天是交易日)
import glob
d_today = None
for fp in sorted(glob.glob(r"E:\test\smc_project\hermes\kline_cache_tencent\*_daily_800.json"))[:5]:
    try:
        raw = json.load(open(fp, encoding="utf-8"))
        ts = [str(b.get("t"))[:8] for b in raw if b.get("t")]
        if ts and (d_today is None or ts[-1] > d_today):
            d_today = ts[-1]
    except Exception:
        continue

if not d_today:
    print("无K线数据, 跳过")
    sys.exit(0)

# ---- 历史回填(先于幂等检查): 快照缺日 → K 线日期序列回补(最多60日) ----
_dates = set()
for fp in sorted(glob.glob(r"E:\test\smc_project\hermes\kline_cache_tencent\*_daily_800.json"))[::20]:
    try:
        raw = json.load(open(fp, encoding="utf-8"))
        for b in raw[-70:]:
            t = str(b.get("t"))[:8]
            if len(t) == 8:
                _dates.add(t)
    except Exception:
        continue
known = {d["d8"] for d in hist.get("days", [])}
n_back = 0
for d8 in sorted(_dates)[-60:]:
    if d8 in known or d8 > d_today:
        continue
    f1x = breadth_newhigh_pct(d8)
    ex, mx = escore_for_date(d8, f1=f1x, with_meta=True)
    hist.setdefault("days", []).append({"d8": d8, "e": ex, "f1": mx.get("f1"),
                                        "f2": mx.get("f2_off_high"), "f3": mx.get("f3_r20"),
                                        "mid_proxy": mx.get("mid_proxy"),
                                        "mid_stale_days": mx.get("mid_stale_days"),
                                        "asof_stale": mx.get("asof_stale"),
                                        "exposure_coef": exposure_coef(ex),
                                        "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                                        "backfilled": True})
    n_back += 1
if n_back:
    print(f"历史回填 {n_back} 日")

if any(d["d8"] == d_today for d in hist["days"]):
    hist["days"].sort(key=lambda d: d["d8"])
    hist["days"] = hist["days"][-KEEP:]
    json.dump(hist, open(HIST, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"{d_today} 已记录(幂等, 回填已保存), 跳过当日新算")
    sys.exit(0)

# F1 带覆盖率门槛(数据新鲜度治理: 09:00 部分市场算的广度=脏E, 宁缺毋滥)
f1_meta = breadth_newhigh_pct(d_today, min_coverage=0.60)
if isinstance(f1_meta, tuple):
    f1, cov_meta = f1_meta
    if cov_meta.get("degraded"):
        print(f"⚠ F1 覆盖率 {cov_meta['coverage']} < 60%(数据未刷完) → E 置 None(脏数据宁缺)")
        f1 = None
else:
    f1 = f1_meta
    cov_meta = None
e, meta = escore_for_date(d_today, f1=f1, with_meta=True)
entry = {"d8": d_today, "e": e, "f1": meta.get("f1"), "f2": meta.get("f2_off_high"),
         "f3": meta.get("f3_r20"), "mid_proxy": meta.get("mid_proxy"),
         "mid_stale_days": meta.get("mid_stale_days"), "asof_stale": meta.get("asof_stale"),
         "exposure_coef": exposure_coef(e),
         "f1_coverage": (cov_meta or {}).get("coverage"),
         "f1_degraded": (cov_meta or {}).get("degraded"),
         "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S")}
hist["days"].append(entry)
hist["days"].sort(key=lambda d: d["d8"])
hist["days"] = hist["days"][-KEEP:]
hist["version"] = _version_
json.dump(hist, open(HIST, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"E[{d_today}] = {e} (F1={entry['f1']}) 系数={entry['exposure_coef']} "
      f"陈旧={entry['asof_stale']}({entry['mid_stale_days']}d) → 已追加(共{len(hist['days'])}日)")