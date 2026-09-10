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

if any(d["d8"] == d_today for d in hist["days"]):
    print(f"{d_today} 已记录(幂等), 跳过")
    sys.exit(0)

f1 = breadth_newhigh_pct(d_today)
e, meta = escore_for_date(d_today, f1=f1, with_meta=True)
entry = {"d8": d_today, "e": e, "f1": meta.get("f1"), "f2": meta.get("f2_off_high"),
         "f3": meta.get("f3_r20"), "mid_proxy": meta.get("mid_proxy"),
         "mid_stale_days": meta.get("mid_stale_days"), "asof_stale": meta.get("asof_stale"),
         "exposure_coef": exposure_coef(e),
         "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S")}
hist["days"].append(entry)
hist["days"] = hist["days"][-KEEP:]
hist["version"] = _version_
json.dump(hist, open(HIST, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"E[{d_today}] = {e} (F1={entry['f1']}) 系数={entry['exposure_coef']} "
      f"陈旧={entry['asof_stale']}({entry['mid_stale_days']}d) → 已追加({len(hist['days'])}日)")