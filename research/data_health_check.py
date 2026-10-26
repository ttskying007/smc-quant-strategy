# -*- coding: utf-8 -*-
"""P1-3: 数据源健康检查 + 失败告警（8/21 式故障兜底）
检查各数据源可用性 + 覆盖率，异常写告警文件（前端可显示）"""
import io, json, os, sys, time, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as CFG

ALERT_FILE = os.path.join(CFG.RESEARCH_DIR, "data_health.json")

def check_source(name, url, timeout=8):
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            b = r.read(200)
            return len(b) > 20, "OK" if len(b) > 20 else "EMPTY"
    except Exception as e:
        return False, str(e)[:60]

sources = {
    "sina": "https://hq.sinajs.cn/list=sh000001",
    "tencent": "https://qt.gtimg.cn/q=sh000001",
    "eastmoney": "https://push2.eastmoney.com/api/qt/stock/get?secid=1.000001&fields=f43",
    "ths_fuyao": "https://fuyao.aicubes.cn/api/a-share/prices/snapshot?thscodes=600519.SH",
    "netease": "https://api.money.126.net/data/feed/0000001,service",
}

status = {}
for name, url in sources.items():
    ok, detail = check_source(name, url)
    status[name] = {"ok": ok, "detail": detail}
    print(f"  {'✅' if ok else '❌'} {name}: {detail}")

# coverage from scanner
try:
    s = json.load(open(os.path.join(CFG.RESEARCH_DIR, "current_scanner_result.json"), encoding="utf-8"))
    coverage = s.get("coverage_pct", 0)
    latest = s.get("latest_date", "")
except Exception:
    coverage, latest = 0, ""

# FIX(2026-10-26, R146): 时序假警报修复 — 健康检查作为前置探测运行时, scanner 结果还是
# 昨天的(latest_date 停在上一交易日), 导致"数据滞后N日"误报整日挂着。兜底: 实测 3 只
# 流动性股的 K线缓存最大 bar 日期, 取 max(scanner, cache_probe) 作为真实数据新鲜度。
try:
    import glob as _glob
    _probe_max = ""
    _kline_dir = getattr(CFG, "KT_CACHE", "") or r"E:\test\smc_project\hermes\kline_cache_tencent"
    for _code in ("000001_SZ", "000651_SZ", "600519_SH"):
        for _fp in _glob.glob(os.path.join(_kline_dir, f"{_code}_daily_800.json")) or []:
            _d = json.load(open(_fp, encoding="utf-8"))
            _raw = _d if isinstance(_d, list) else (_d.get("klines") or _d.get("bars") or [])
            if _raw:
                _t = str((_raw[-1] or {}).get("t") or (_raw[-1] or {}).get("day") or "").replace("-", "")
                if _t > _probe_max:
                    _probe_max = _t
    if _probe_max > str(latest or ""):
        latest = _probe_max
except Exception:
    pass

alerts = []
if not any(v["ok"] for v in status.values()):
    alerts.append("所有数据源不可用（严重）")
if coverage < 95:
    alerts.append(f"数据覆盖率低 {coverage}%")
try:
    _latest_day = datetime.datetime.strptime(str(latest), "%Y%m%d").date()
    _lag_days = (datetime.date.today() - _latest_day).days
    # Monday after Friday is healthy; a longer gap indicates a stale feed.
    if _lag_days > 4:
        alerts.append(f"数据滞后 {latest}({_lag_days}日)")
except (TypeError, ValueError):
    if not latest:
        alerts.append("无有效最新交易日")

health = {
    "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "sources": status,
    "coverage": coverage,
    "latest": latest,
    "alerts": alerts,
}
os.makedirs(os.path.dirname(ALERT_FILE), exist_ok=True)
with open(ALERT_FILE, "w", encoding="utf-8") as fh:
    json.dump(health, fh, ensure_ascii=False, indent=2)
print(f"\n告警: {alerts if alerts else '无'}")
print(f"已写入 {ALERT_FILE}")
