# -*- coding: utf-8 -*-
"""V699 yearly imbalance root-cause + V88 loss commonality analysis."""
import csv, os, json, collections, datetime

HERMES = r"E:\test\smc_project\hermes"
AUD = os.path.join(HERMES, "smc_audit")

def load_rows(csv_path):
    rows = []
    with open(csv_path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append(r)
    return rows

print("=" * 70)
print("V699 年度失衡根因分析（17,600 笔纯SMC SSL-Reclaim 冻结回放）")
print("=" * 70)
v699_csv = os.path.join(AUD, "v699_pure_smc_ssl_reclaim_frozen_t1_replay_no_write_20260814_163915", "v699_frozen_t1_trades.csv")
rows = load_rows(v699_csv)
print("总笔数:", len(rows))

def pnl(r): return float(r["net_pnl_pct"])
def year(r): return str(r["entry_date"])[:4]

# 1. yearly overview with win/loss asymmetry
print("\n--- 1. 年度概览：胜率/盈亏不对称 ---")
by_y = collections.defaultdict(list)
for r in rows: by_y[year(r)].append(r)
for y in sorted(by_y):
    rs = by_y[y]
    n = len(rs)
    wins = [r for r in rs if pnl(r) > 0]
    losses = [r for r in rs if pnl(r) <= 0]
    aw = sum(pnl(r) for r in wins) / len(wins) if wins else 0
    al = sum(pnl(r) for r in losses) / len(losses) if losses else 0
    print(f"  {y}: n={n} WR={100*len(wins)/n:.1f}% avg={sum(pnl(r) for r in rs)/n:+.3f}% avgWin={aw:+.2f}% avgLoss={al:+.2f}% payoff={abs(aw/al) if al else 0:.3f}")

# 2. monthly worst/best
print("\n--- 2. 月度最差/最好（按月 WR 与 avg）---")
by_m = collections.defaultdict(list)
for r in rows: by_m[str(r["entry_date"])[:6]].append(r)
ms = sorted(by_m.items())
mstats = []
for m, rs in ms:
    n = len(rs)
    wins = [r for r in rs if pnl(r) > 0]
    mstats.append((m, n, 100*len(wins)/n, sum(pnl(r) for r in rs)/n))
print("最差 10 个月：")
for m, n, wr, avg in sorted(mstats, key=lambda x: x[3])[:10]:
    print(f"  {m}: n={n} WR={wr:.1f}% avg={avg:+.3f}%")
print("最好 10 个月：")
for m, n, wr, avg in sorted(mstats, key=lambda x: -x[3])[:10]:
    print(f"  {m}: n={n} WR={wr:.1f}% avg={avg:+.3f}%")

# 3. exit reason distribution by year
print("\n--- 3. 出场原因分布（按年）---")
reasons = collections.Counter()
for r in rows: reasons[r["reason"]] += 1
print("总体出场原因:", dict(reasons))
for y in ("2023", "2025", "2026"):
    rc = collections.Counter(r["reason"] for r in by_y[y])
    print(f"  {y}: {dict(rc)}")

# 4. hold bars distribution by year (exit speed)
print("\n--- 4. 平均持仓 K 线（按年）---")
for y in sorted(by_y):
    hs = [float(r["hold_bars"]) for r in by_y[y]]
    print(f"  {y}: avg hold={sum(hs)/len(hs):.1f} max={max(hs)}")

# 5. entry date gap: how many entries cluster in specific periods
print("\n--- 5. 2026 年逐月（看下半年是否更差）---")
for m in sorted(m for m in by_m if m.startswith("2026")):
    rs = by_m[m]
    n = len(rs)
    wins = [r for r in rs if pnl(r) > 0]
    print(f"  {m}: n={n} WR={100*len(wins)/n:.1f}% avg={sum(pnl(r) for r in rs)/n:+.3f}%")

print("\n" + "=" * 70)
print("V88 亏损单共性分析（106 笔，生产契约）")
print("=" * 70)
v88 = json.load(open(os.path.join(HERMES, "smc_opt_v88_production_contract", "v88_trades.json"), encoding="utf-8"))
losses = [t for t in v88 if float(t.get("pnl_pct") or 0) <= 0]
wins = [t for t in v88 if float(t.get("pnl_pct") or 0) > 0]
print(f"亏损单: {len(losses)} / 532，胜单: {len(wins)}")

print("\n--- 1. 亏损出场原因分布 ---")
print(dict(collections.Counter(t.get("exit_reason") for t in losses)))
print("\n--- 2. 亏损市场状态分布 ---")
print(dict(collections.Counter(t.get("market_state") for t in losses)))
print("\n--- 3. 亏损故事类型分布 ---")
print(dict(collections.Counter(t.get("story") for t in losses)))
print("\n--- 4. 亏损 POI 类型分布 ---")
print(dict(collections.Counter(t.get("poi_type") for t in losses)))
print("\n--- 5. 亏损趋势分布 ---")
print(dict(collections.Counter(t.get("trend_regime") for t in losses)))
print("\n--- 6. 亏损 vs 胜：平均持仓/风险 ---")
for name, ts in (("亏损", losses), ("胜", wins)):
    print(f"  {name}: avgHold={sum(float(t.get('hold_bars') or 0) for t in ts)/len(ts):.2f} avgRisk={sum(float(t.get('risk_pct') or 0) for t in ts)/len(ts):.2f}% avgMFE_r={sum(float(t.get('mfe_r') or 0) for t in ts)/len(ts):.2f}")
print("\n--- 7. 亏损单按年 ---")
print(dict(collections.Counter(str(t.get("entry_date"))[:4] for t in losses)))
print("\n--- 8. 亏损单按月（Top 月份）---")
mc = collections.Counter(str(t.get("entry_date"))[:6] for t in losses)
for m, c in mc.most_common(10):
    tot = sum(1 for t in v88 if str(t.get("entry_date"))[:6] == m)
    print(f"  {m}: 亏损 {c}/{tot} 笔")
print("\n--- 9. 亏损单样例（前 10 笔）---")
for t in sorted(losses, key=lambda x: float(x.get("pnl_pct") or 0))[:10]:
    print(f"  {t['symbol']} {t.get('entry_date')} pnl={t.get('pnl_pct')}% exit={t.get('exit_reason')} story={t.get('story')} state={t.get('market_state')} mae_r={t.get('mae_r')}")
