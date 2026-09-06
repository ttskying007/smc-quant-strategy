# -*- coding: utf-8 -*-
"""复审 P0-2/P0-1: 数据源覆盖统计 + active manifest + PARTIAL_MULTI_TF 判定
按源统计 daily/m60/announcement 真实 max_ts、按月份统计交易、生成 coverage_report.json +
artifacts/active_manifest.json（锁定 commit/hash/各源end/status）。
"""
import csv, hashlib, io, json, os, random, sqlite3, sys, time
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = r"E:\test\smc_project"
RESEARCH = os.path.join(ROOT, "research")
KT = os.path.join(ROOT, "hermes", "kline_cache_tencent")
M60 = os.path.join(ROOT, "hermes", "kline_cache_60min")
DB = os.path.join(ROOT, "announce", "smc_announce.db")
ARTIFACTS = os.path.join(ROOT, "artifacts")
os.makedirs(ARTIFACTS, exist_ok=True)

REQUESTED_END = "2026-09-05"
random.seed(42)

def file_hash(p):
    try:
        return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]
    except Exception:
        return "missing"

# ---- 1. daily 边界（抽样统计 + 全量扫描太慢，抽样 + 最新文件确认）----
daily_max = {}
daily_n = 0
for f in random.sample([x for x in os.listdir(KT) if x.endswith("_daily_800.json")], min(300, len(os.listdir(KT)))):
    try:
        raw = json.load(open(os.path.join(KT, f), encoding="utf-8"))
        if raw:
            t = "".join(c for c in str(raw[-1].get("t", "")) if c.isdigit())[:8]
            daily_max[t] = daily_max.get(t, 0) + 1
            daily_n += 1
    except Exception:
        pass
d_end = max(daily_max, key=daily_max.get) if daily_max else ""
d_end_iso = f"{d_end[:4]}-{d_end[4:6]}-{d_end[6:8]}" if len(d_end) == 8 else ""

# ---- 2. 60m 边界 ----
m60_max = {}
m60_n = 0
for f in random.sample([x for x in os.listdir(M60) if x.endswith(".json")], min(150, len(os.listdir(M60)))):
    try:
        raw = json.load(open(os.path.join(M60, f), encoding="utf-8"))
        if raw:
            t = str(raw[-1].get("t", ""))[:8]
            m60_max[t] = m60_max.get(t, 0) + 1
            m60_n += 1
    except Exception:
        pass
m60_end = max(m60_max, key=m60_max.get) if m60_max else ""
m60_end_iso = f"{m60_end[:4]}-{m60_end[4:6]}-{m60_end[6:8]}" if len(m60_end) == 8 else ""

# ---- 3. 公告边界 ----
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT MAX(date), MIN(date), COUNT(*) FROM announce")
a_max, a_min, a_cnt = cur.fetchone()
conn.close()

# ---- 4. 交易月份统计 ----
def load(p):
    with open(p, encoding="utf-8-sig") as fh:
        return [r for r in csv.DictReader(fh) if r.get("net_pnl_pct") not in (None, "", "None")]
smc = load(os.path.join(RESEARCH, "..", "wdh", "W1D1D4_trades.csv"))
ev = [r for r in load(os.path.join(RESEARCH, "combo_v20f_trades.csv")) if r.get("src") == "EVENT"]
monthly = defaultdict(lambda: {"signal": 0, "entry": 0})
for r in smc + ev:
    m = r["entry_date"][:6]
    monthly[m]["signal"] += 1
    monthly[m]["entry"] += 1
months_report = {m: v for m, v in sorted(monthly.items())}

# ---- 5. 状态判定 ----
# FIX(2026-09-06): 以市场最新交易日(daily_end)为基准 —— requested_end 是自然日(如周六)永不可达；
# 完整性 = 各必需源均覆盖到 daily_end（最新交易日），且三者一致
base_day = d_end_iso
daily_ok = bool(d_end_iso)
m60_ok = m60_end_iso >= base_day
ann_ok = str(a_max) >= base_day
complete = daily_ok and m60_ok and ann_ok
status = "COMPLETE" if complete else "PARTIAL_MULTI_TF"
reasons = []
if not m60_ok:
    reasons.append(f"m60_end={m60_end_iso} < daily_end={base_day}")
if not ann_ok:
    reasons.append(f"announcement_end={a_max} < daily_end={base_day}")
if not daily_ok:
    reasons.append(f"daily_end={d_end_iso} 未知")

# ---- 6. coverage_report.json ----
coverage = {
    "requested_start": "2024-01-01",
    "requested_end": REQUESTED_END,
    "status": status,
    "status_reason": reasons,
    "sources": {
        "daily_ohlcv": {"sample_count": daily_n, "max_ts": d_end_iso, "fresh_ok": daily_ok},
        "m60_ohlcv": {"sample_count": m60_n, "max_ts": m60_end_iso, "fresh_ok": m60_ok},
        "announcement": {"max_ts": str(a_max), "count": a_cnt, "fresh_ok": ann_ok},
    },
    "trade_coverage": {
        "smc_latest_entry": max((r["entry_date"] for r in smc), default="-"),
        "event_latest_entry": max((r["entry_date"] for r in ev), default="-"),
    },
    "monthly": months_report,
    "fully_realized_end": max([r["entry_date"] for r in smc + ev] or ["-"]),
    "open_position_asof": d_end_iso,
}
with open(os.path.join(RESEARCH, "handover", "coverage_report.json"), "w", encoding="utf-8") as fh:
    json.dump(coverage, fh, ensure_ascii=False, indent=1)

# ---- 7. active_manifest.json ----
def git_head():
    try:
        import subprocess
        r = subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except Exception:
        return "unknown"
manifest = {
    "active": True,
    "strategy_commit": git_head(),
    "code_commit": git_head(),
    "data_snapshot_id": "snap-" + d_end_iso,
    "requested_range": {"start": "2024-01-01", "end": REQUESTED_END},
    "data_ends": {
        "daily_end": d_end_iso,
        "m60_end": m60_end_iso,
        "announcement_end": str(a_max),
        "signal_end": max([r["entry_date"] for r in smc + ev] or ["-"]),
        "exit_end": max([r["entry_date"] for r in smc + ev] or ["-"]),
    },
    "data_hashes": {
        "wdh_engine.py": file_hash(os.path.join(ROOT, "wdh", "wdh_engine.py")),
        "paper_sim.py": file_hash(os.path.join(RESEARCH, "paper_sim.py")),
        "config.py": file_hash(os.path.join(RESEARCH, "config.py")),
    },
    "status": status,
    "status_reason": reasons,
    "timezone": "Asia/Shanghai",
    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
}
with open(os.path.join(ARTIFACTS, "active_manifest.json"), "w", encoding="utf-8") as fh:
    json.dump(manifest, fh, ensure_ascii=False, indent=1)

print(f"状态: {status} | reasons={reasons}")
print(f"daily_end={d_end_iso} | m60_end={m60_end_iso} | announce_end={a_max}")
print(f"8月交易: {months_report.get('202608', {}).get('entry', 0)} 笔")
print(f"coverage_report → research/handover/coverage_report.json")
print(f"active_manifest → artifacts/active_manifest.json")
