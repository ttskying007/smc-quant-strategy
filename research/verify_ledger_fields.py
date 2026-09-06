# -*- coding: utf-8 -*-
"""复审: 逐笔字段级验证器 —— 对最新回测数据包执行
1. 主键去重 (leg,symbol,entry_date)
2. 时间因果: buy_date <= sell_date（T+1）
3. 收益重算: net_pnl = (sell/buy - 1)*100 - FEE（vs CSV）
4. TP/SL 一致性: tp > buy > sl；sl < buy
5. R 倍数重算: rr = (sell-buy)/(buy-sl)
6. MFE/MAE 窗口: 从入场后（simulate 已保证）
"""
import csv, io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

CSV = r"E:\test\smc_project\research\handover\最新回测数据\逐笔交易全明细.csv"
FEE = 0.20  # config.FEE_PCT（双向下近似，仅校验量级）

rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))
print(f"总行数: {len(rows)}")

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + detail)

# 1. 主键去重
keys = [(r["leg"], r["symbol"], r["entry_date"]) for r in rows]
dups = len(keys) - len(set(keys))
ok(f"主键无重复 ({len(keys)} 笔)", dups == 0, f"dups={dups}")

# 2. SMC 行时间因果 + 收益重算
smc = [r for r in rows if r["leg"] == "SMC"]
n_time = n_ret = n_tp = n_r = 0
bad_time = []
for r in smc:
    bd, sd = r["buy_date"], r["sell_date"]
    if sd and bd and sd >= bd:
        n_time += 1
    else:
        bad_time.append((r["symbol"], r["entry_date"], bd, sd))
ok(f"SMC 时间因果 sell>=buy ({len(smc)} 笔)", n_time == len(smc), f"bad={len(bad_time)} first={bad_time[:2]}")

# 收益重算（近似：buy/sell 价重算 vs CSV net）
n_ret = 0
ret_diffs = []
for r in smc:
    try:
        buy, sell, net = float(r["buy_price"]), float(r["sell_price"]), float(r["net_pnl_pct"])
    except (ValueError, TypeError):
        continue
    if buy <= 0:
        continue
    calc = (sell / buy - 1) * 100 - FEE
    if abs(calc - net) < 0.5:  # 容忍费用建模差异
        n_ret += 1
    else:
        ret_diffs.append((r["symbol"], r["entry_date"], round(net, 2), round(calc, 2)))
ok(f"SMC 收益重算一致 ({len(smc)} 笔)", n_ret >= len(smc) * 0.95, f"diff={len(ret_diffs)} first={ret_diffs[:3]}")

# 3. TP/SL 一致性
n_tp = 0
for r in smc:
    try:
        buy, tp, sl = float(r["buy_price"]), float(r["tp"]), float(r["sl"])
    except (ValueError, TypeError):
        continue
    if tp > buy > sl:
        n_tp += 1
ok(f"SMC TP>buy>SL ({len(smc)} 笔)", n_tp == len(smc), f"bad={len(smc)-n_tp}")

# 4. R 倍数重算
n_r = 0
for r in smc:
    try:
        buy, sell, sl, rr = float(r["buy_price"]), float(r["sell_price"]), float(r["sl"]), float(r["rr_exit"])
    except (ValueError, TypeError):
        continue
    risk = buy - sl
    if risk <= 0:
        continue
    calc_r = (sell - buy) / risk
    if abs(calc_r - rr) < 0.05:
        n_r += 1
ok(f"SMC R倍数重算一致 ({len(smc)} 笔)", n_r >= len(smc) * 0.9, f"bad={len(smc)-n_r}")

# 5. MFE/MAE 合理性（simulate 已从入场后算）
n_m = 0
for r in smc:
    try:
        mfe, mae = float(r["mfe_pct"]), float(r["mae_pct"])
    except (ValueError, TypeError):
        continue
    if mae <= max(mfe * 0.5, -60) and mfe >= -10:
        n_m += 1
ok(f"SMC MFE/MAE 合理 ({len(smc)} 笔)", n_m >= len(smc) * 0.9, f"bad={len(smc)-n_m}")

print(f"\n结果: PASS={PASS} FAIL={FAIL}（SMC {len(smc)} 笔字段级验证）")
sys.exit(1 if FAIL else 0)
