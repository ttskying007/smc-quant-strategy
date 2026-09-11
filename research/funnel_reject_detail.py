# -*- coding: utf-8 -*-
"""funnel_reject_detail.py —— V3-C 升级: 被拒候选身份+前向收益追踪(第五轮审计§二十)
缺口: funnel_history_accum 只记计数, 无被拒候选身份 → 无法回答"系统杀机会 vs 正确"。
本脚本(每日跑, 在 funnel_history_accum 之后):
  ① 从 selection_result.json 读当日全部候选(通过+被拒, 含 skip 原因字符串)
  ② 记录被拒候选 {code, date, reason} 到 funnel_reject_ledger.json(90 日滚动)
  ③ 回填: T+5/T+10/T+20 前向收益(次开买入口径, 与 L2 一致)—— 对已到期样本自动补
  ④ 汇总: 按原因分组的 fwd5/fwd10 均值 → 直接回答"每类拒绝放走了多少收益"
与 L2 追踪器互补: L2 管事件腿 soft-reject, 本工具管全漏斗(含 stage/adx/dup)。"""
import io, json, os, sys, time
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
SRC = r"E:\test\smc_project\research\selection_result.json"
LEDGER = r"E:\test\smc_project\research\handover\funnel_reject_ledger.json"
KEEP = 90

if not os.path.exists(SRC):
    print("无 selection_result.json, 跳过")
    sys.exit(0)
sr = json.load(open(SRC, encoding="utf-8"))
gen_day = str(sr.get("generated_at") or sr.get("selected_at") or time.strftime("%Y%m%d"))[:10].replace("-", "")

# ① 当日全部候选: 通过(days/new_orders) + 被拒(skipped_detail)
ledger = {"rejects": [], "summary": {}}
if os.path.exists(LEDGER):
    try:
        ledger = json.load(open(LEDGER, encoding="utf-8"))
    except Exception:
        pass
seen = {(r.get("code"), r.get("date")) for r in ledger.get("rejects", [])}
n_new = 0
for r in (sr.get("skipped_detail") or []):
    code = str(r.get("symbol") or r.get("code") or "").split(".")[0]
    # 日期规范化: "2026-09-10"→"20260910"; "2026-09-10 00:00:00"/"20260910" 均兼容
    _d = str(r.get("date") or r.get("signal_date") or gen_day)
    d8 = _d[:10].replace("-", "").replace("/", "")[:8]
    reason = str(r.get("reason") or r.get("skip_reason") or "?")[:60]
    if not code or (code, d8) in seen:
        continue
    ledger.setdefault("rejects", []).append({"code": code, "date": d8, "reason": reason,
                                             "fwd5": None, "fwd10": None, "filled": False})
    seen.add((code, d8))
    n_new += 1

# ② 前向回填(次开买入口径: T+1 开盘买, T+5/T+10 收盘卖, 与 L2 同)
_daily = {}
def get_daily(code):
    if code in _daily:
        return _daily[code]
    for suf in ("_SZ", "_SH", "_BJ"):
        fp = os.path.join(KT, f"{code}{suf}_daily_800.json")
        if os.path.exists(fp):
            try:
                raw = json.load(open(fp, encoding="utf-8"))
                d = [{"t": str(b["t"])[:8], "o": float(b["o"]), "c": float(b["c"])} for b in raw]
                _daily[code] = d
                return d
            except Exception:
                break
    _daily[code] = []
    return []

n_fill = 0
today8 = time.strftime("%Y%m%d")
for r in ledger.get("rejects", []):
    if r.get("fwd5") is not None:
        continue
    d = get_daily(r["code"])
    if not d:
        continue
    idx = {b["t"]: k for k, b in enumerate(d)}
    i0 = idx.get(r["date"])
    if i0 is None or i0 + 11 >= len(d):
        continue
    buy = d[i0 + 1]["o"]
    if buy <= 0:
        continue
    f5 = d[min(i0 + 5, len(d) - 1)]
    f10 = d[min(i0 + 10, len(d) - 1)]
    r["fwd5"] = round((f5["c"] / buy - 1) * 100, 2)
    r["fwd10"] = round((f10["c"] / buy - 1) * 100, 2)
    r["filled"] = True
    n_fill += 1

# ③ 90 日滚动
ledger["rejects"] = [r for r in ledger["rejects"]
                     if r["date"] >= "20260601"][-KEEP * 40:]   # 数量上限粗控
# ④ 汇总: 按原因组
from collections import defaultdict
grp = defaultdict(list)
for r in ledger["rejects"]:
    if r.get("fwd5") is not None:
        key = r["reason"][:24]
        grp[key].append((r["fwd5"], r["fwd10"]))
summary = {}
for k, v in sorted(grp.items(), key=lambda kv: -len(kv[1])):
    summary[k] = {"n": len(v),
                  "avg_fwd5": round(sum(a for a, _ in v) / len(v), 2),
                  "avg_fwd10": round(sum(b for _, b in v) / len(v), 2)}
ledger["summary"] = summary
ledger["days_accum"] = ledger.get("days_accum", 0) + (1 if n_new else 0)
json.dump(ledger, open(LEDGER, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"新拒 {n_new} | 回填 {n_fill} | 总 {len(ledger['rejects'])}")
for k, s in list(summary.items())[:8]:
    print(f"  {k}: n={s['n']} fwd5={s['avg_fwd5']} fwd10={s['avg_fwd10']}")