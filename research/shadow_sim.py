# -*- coding: utf-8 -*-
"""受控 Shadow（P1 门禁通过后）—— 事件腿真实信号 → shadow 账本
参数（保守，P1 验收建议）：容量50 / 单日5开 / 3x成本(FEE0.6) / MDD kill switch 10%
输出：shadow_ledger.json + shadow_status.json（含 kill switch 判定）+ 前端同步
"""
import io, json, os, sys, time
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import ledger_types as LT
import config as CFG

RESEARCH = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(RESEARCH, "shadow_ledger.json")
STATUS = os.path.join(RESEARCH, "shadow_status.json")

# 保守 Shadow 参数（P1 验收建议）
SHADOW_CFG = {
    "capacity": 50,          # 最大同时持仓
    "max_daily_open": 5,     # 单日新开上限
    "fee_mult": 3.0,         # 3x 成本
    "base_fee": 0.20,
    "kill_mdd": 0.10,        # 最大回撤 kill switch 10%
    "run_id": "shadow-" + time.strftime("%Y%m%d-%H%M%S"),
}

def pf(pn):
    if not pn:
        return 0, 0, 0
    w = [x for x in pn if x > 0]; l = [x for x in pn if x <= 0]
    return (sum(w)/abs(sum(l)) if l else 99, sum(pn)/len(pn), len(pn))

# 1. 真实事件腿信号（combo_v20f 最新）
import csv
CSV = os.path.join(RESEARCH, "combo_v20f_trades.csv")
rows = [r for r in csv.DictReader(open(CSV, encoding="utf-8-sig"))
        if r.get("src") == "EVENT" and r.get("net_pnl_pct") not in (None, "", "None")]
print(f"事件腿信号: {len(rows)}", flush=True)

# 2. 容量/单日开仓约束（同日超5 跳过 rank 低者——无 rank 排序用出现顺序）
by_day = defaultdict(list)
for r in rows:
    by_day[r["entry_date"]].append(r)
kept = []
for day in sorted(by_day):
    kept.extend(by_day[day][:SHADOW_CFG["max_daily_open"]])

# 3. 3x 成本计算
fee = SHADOW_CFG["base_fee"] * SHADOW_CFG["fee_mult"]
shadow_trades = []
equity = 1.0
eq_curve = [1.0]
peak = 1.0
mdd = 0.0
for r in kept[:SHADOW_CFG["capacity"] * 10]:  # 容量池上限
    pnl = float(r["net_pnl_pct"])
    # gross 还原后扣 3x 费用
    net3x = pnl + SHADOW_CFG["base_fee"] - fee
    tr = LT.annotate_trade({
        "symbol": r["symbol"], "entry_date": r["entry_date"],
        "net_pnl_pct": round(net3x, 4), "fee_used": round(fee, 2),
    }, "shadow", run_id=SHADOW_CFG["run_id"])
    shadow_trades.append(tr)
    equity *= (1 + 0.01 * net3x / 100)  # 1% 仓位
    eq_curve.append(equity)
    peak = max(peak, equity)
    mdd = max(mdd, (peak - equity) / peak)

# 4. kill switch 判定
p, a, n = pf([t["net_pnl_pct"] for t in shadow_trades])
kill = mdd >= SHADOW_CFG["kill_mdd"]
status = {
    "run_id": SHADOW_CFG["run_id"],
    "config": SHADOW_CFG,
    "trades": len(shadow_trades),
    "avg_pct": round(a, 2), "pf": round(p, 2),
    "equity_final": round(equity, 4), "max_drawdown": round(mdd * 100, 2),
    "kill_switch_triggered": kill,
    "action": "STOP_ALL" if kill else "CONTINUE",
    "capacity_used": min(len(set(t["symbol"] for t in shadow_trades)), SHADOW_CFG["capacity"]),
    "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
}

with open(OUT, "w", encoding="utf-8") as fh:
    json.dump({"ledger_type": "shadow", "config": SHADOW_CFG, "trades": shadow_trades}, fh, ensure_ascii=False, indent=1)
with open(STATUS, "w", encoding="utf-8") as fh:
    json.dump(status, fh, ensure_ascii=False, indent=1)

print(f"shadow: {len(shadow_trades)} 笔 avg={a:+.2f}% PF={p:.2f} MDD={mdd*100:.2f}% kill={kill}", flush=True)

# 5. 前端同步
import shutil
for d in (os.path.join(CFG.HERMES_DIR, "smc_monitor"), r"E:\root\.hermes\smc_monitor"):
    os.makedirs(d, exist_ok=True)
    shutil.copyfile(OUT, os.path.join(d, "shadow_ledger.json"))
    shutil.copyfile(STATUS, os.path.join(d, "shadow_status.json"))
print("shadow 账本+状态已同步前端双目录", flush=True)
