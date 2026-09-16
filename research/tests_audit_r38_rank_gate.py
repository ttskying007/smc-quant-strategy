# -*- coding: utf-8 -*-
"""tests_audit_r38_rank_gate.py —— R38ab rank 门槛接线回归锁.

背景: 2026-09-16 用户批准 EVENT 腿 rank 门槛接线(全链路审计 + 研究分叉双路径验证)。
本测试锁定接线的关键不变量, 防止后续改动静默破坏:

  ① CFG 开关存在且默认=3, env 可覆盖(=0 回滚路径可用);
  ② paper_sim 门槛代码位于**正确位置** —— rank_score 全部特征(含 L849/L851 增持
     强度)计算完之后, 才判定门槛; 若插在增持特征之前, 门槛口径会与验证时不符;
  ③ 门槛只作用于 EVENT 腿 —— 不得出现在 CONT 腿分支;
  ④ 门槛语义: rank_score < EVENT_RANK_GATE_MIN → continue(拒绝), 并记漏斗;
  ⑤ 反推校验: 用 r38_rank_chain_cands.json(审计候选缓存) 重放门槛,
     通过笔数应与 r38_combo_rank3_trades.csv 的 EVENT 数一致(口径未漂移)。

**安全约束**: 绝不调用 daily_selection()/realtime_monitor() —— 它们会写生产台账。
本测试只做静态源码检查 + 离线纯函数重放。
"""
import csv, io, json, os, re, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
PASS = FAIL = 0


def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  OK " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + " " + str(detail))


print("== 1. CFG 开关 ==")
import config as CFG
ok("EVENT_RANK_GATE_MIN 存在", hasattr(CFG, "EVENT_RANK_GATE_MIN"))
ok("默认值 = 3", getattr(CFG, "EVENT_RANK_GATE_MIN", None) == 3,
   getattr(CFG, "EVENT_RANK_GATE_MIN", None))
ok("非负", isinstance(CFG.EVENT_RANK_GATE_MIN, int) and CFG.EVENT_RANK_GATE_MIN >= 0)

print("== 2. paper_sim 门槛代码位置与语义 ==")
src = open(os.path.join(HERE, "paper_sim.py"), encoding="utf-8").read()
lines = src.split("\n")

# 定位关键锚点
i_insider = None      # L849/L851 增持强度加分
i_gate = None         # 门槛判定
i_risksize = None     # 风险归一仓位
for idx, ln in enumerate(lines):
    if "实质增持（≥1%）" in ln or "实质增持(≥1%)" in ln:
        i_insider = idx
    if "EVENT_RANK_GATE_MIN" in ln and "getattr" in ln:
        i_gate = idx
    if "风险归一仓位" in ln:
        i_risksize = idx

ok("找到增持强度特征锚点", i_insider is not None, i_insider)
ok("找到门槛判定锚点", i_gate is not None, i_gate)
ok("找到仓位计算锚点", i_risksize is not None, i_risksize)
if None not in (i_insider, i_gate, i_risksize):
    ok("门槛在增持特征之后(口径正确)", i_gate > i_insider, (i_insider, i_gate))
    ok("门槛在仓位计算之前(拒绝早于建单)", i_gate < i_risksize, (i_gate, i_risksize))

# 门槛语义: 小于门槛则 continue + 记漏斗
gate_block = "\n".join(lines[i_gate:i_gate + 12]) if i_gate is not None else ""
ok("门槛语义 = rank_score < MIN 则拒绝", "rank_score < _rank_gate" in gate_block, gate_block[:120])
ok("拒绝时 continue", "continue" in gate_block)
ok("拒绝记入漏斗(_sel_stats)", "skipped_rank" in gate_block)
ok("拒绝记入 _mark_funnel", "_mark_funnel" in gate_block)
ok("拒绝记入 _reject_records", "_reject_records" in gate_block)

print("== 3. 门槛仅作用于 EVENT 腿 ==")
# 门槛判定的缩进层级应与 EVENT 腿主体一致; 且全文只有一处该判定
n_gate_sites = sum(1 for ln in lines if "EVENT_RANK_GATE_MIN" in ln and "getattr" in ln)
ok("门槛判定全文仅 1 处", n_gate_sites == 1, n_gate_sites)
# CONT 腿不得引用该门槛
i_cont = None
for idx, ln in enumerate(lines):
    if "sub_signals_cont" in ln and "def " not in ln:
        i_cont = idx
        break
if i_cont is not None:
    cont_region = "\n".join(lines[i_cont:i_cont + 200])
    ok("CONT 腿区域不引用门槛", "EVENT_RANK_GATE_MIN" not in cont_region)
else:
    print("  SKIP CONT 腿定位")

print("== 4. 离线重放: 门槛通过数应与研究分叉一致 ==")
p_cands = os.path.join(HERE, "r38_rank_chain_cands.json")
p_fork = os.path.join(HERE, "r38_combo_rank3_trades.csv")
if os.path.exists(p_cands) and os.path.exists(p_fork):
    cands = json.load(open(p_cands, encoding="utf-8"))
    fork_rows = list(csv.DictReader(open(p_fork, encoding="utf-8-sig")))
    fork_ev = [r for r in fork_rows if r.get("src") == "EVENT"]
    passed = [c for c in cands if c["rank"] >= CFG.EVENT_RANK_GATE_MIN]
    # 注意: 分叉 CSV 已过月度 cap, 故 passed 应 >= fork_ev
    ok("门槛通过数 >= 分叉 EVENT 数(cap 前 >= cap 后)",
       len(passed) >= len(fork_ev), (len(passed), len(fork_ev)))
    # 反推: 分叉 EVENT 的 rank 应全部 >= 门槛
    bad = [r for r in fork_ev if int(float(r.get("rank") or 0)) < CFG.EVENT_RANK_GATE_MIN]
    ok("分叉 EVENT 无低于门槛者", not bad, len(bad))
    print("    候选 %d → 门槛通过 %d → 分叉 EVENT(cap后) %d"
          % (len(cands), len(passed), len(fork_ev)))
else:
    print("  SKIP 缺少审计缓存或分叉 CSV")

print("== 5. 回滚路径可用 ==")
ok("env 覆盖名 = SMC_EVENT_RANK_GATE_MIN",
   "SMC_EVENT_RANK_GATE_MIN" in src or "SMC_EVENT_RANK_GATE_MIN" in
   open(os.path.join(HERE, "config.py"), encoding="utf-8").read())
cfg_src = open(os.path.join(HERE, "config.py"), encoding="utf-8").read()
ok("config 含负值归零保护", "if EVENT_RANK_GATE_MIN < 0" in cfg_src)
ok("config 含 ValueError 兜底", "except ValueError" in cfg_src)

print("== 6. R12-R21 修复保持(接线未破坏既有) ==")
ok("leg_flags 仍在", '"leg_flags"' in src)
ok("R18 成交前 gate 仍在", "CAPACITY_REJECT_FILL" in src)
ok("时区单源仍在", "from core.time_cn import cn_now, cn_today" in src)
ok("R19 KT 环境变量化仍在", "kt = CFG.KT_CACHE" in src)
ok("_market_proxy(code, d8) 仍在", "def _market_proxy(code, d8=None)" in src)
ok("ADX 单源委托仍在", "from core.indicators import adx14_of as _adx_core" in src)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)