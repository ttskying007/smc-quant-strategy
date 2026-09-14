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
