# -*- coding: utf-8 -*-
"""60min 数据全量补全（审计 PARTIAL_MULTI_TF 修复）
用腾讯 ifzq 接口刷新 kline_cache_60min 全部股票的 60min 缓存（count=500 覆盖更多历史）。
输出：每只更新状态 + 汇总；新数据 t 格式 YYYYMMDDHHMM（与原缓存一致）。
"""
import json, os, sys, time, urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
CACHE = r"E:\test\smc_project\hermes\kline_cache_60min"
UA = {"User-Agent": "Mozilla/5.0"}


def get_60min(symbol, count=500):
    code, market = symbol.split(".")
    prefix = "sh" if market == "SH" else "sz"
    tc = prefix + code
    url = "http://ifzq.gtimg.cn/appstock/app/kline/mkline?param=%s,m60,,%d" % (tc, count)
    try:
        req = urllib.request.Request(url, headers=UA)
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode("utf-8"))
        klines = data.get("data", {}).get(tc, {}).get("m60", [])
        if not klines:
            return None
        bars = []
        for k in klines:
            t_raw = str(k[0])  # "2026-09-04 15:00:00"
            t_num = t_raw.replace("-", "").replace(":", "").replace(" ", "")[:12]
            # 原缓存 date 格式 "2026-05-08 15:00:00"（保留兼容）
            _d = t_raw[:10] + " " + t_raw[11:19] if len(t_raw) >= 19 else t_raw
            bars.append({"t": int(t_num), "date": _d,
                         "o": float(k[1]), "c": float(k[2]),
                         "h": float(k[3]), "l": float(k[4]), "v": float(k[5])})
        return bars
    except Exception:
        return None


files = sorted(f for f in os.listdir(CACHE) if f.endswith("_60min_200.json"))
print("待更新股票数:", len(files))
ok = fail = skip = 0
latest_max = ""
for i, f in enumerate(files):
    sym = f.replace("_60min_200.json", "")
    if "_" in sym:
        code, market = sym.split("_", 1)
        sym = code + "." + ("SH" if market == "SH" else "SZ")
    bars = get_60min(sym, 500)
    if not bars:
        fail += 1
        continue
    latest = str(bars[-1]["t"])
    if latest > latest_max:
        latest_max = latest
    # 更新缓存（t 与 date 对齐原格式）
    out = os.path.join(CACHE, f)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(bars, fh, ensure_ascii=False)
    ok += 1
    if (i + 1) % 300 == 0:
        print("  %d/%d ok=%d fail=%d" % (i + 1, len(files), ok, fail), flush=True)
    time.sleep(0.15)

print("\n完成: ok=%d fail=%d | 最新 60m 日期: %s" % (ok, fail, latest_max))
