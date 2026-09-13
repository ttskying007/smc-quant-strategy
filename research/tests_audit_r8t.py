# -*- coding: utf-8 -*-
"""tests_audit_r8t.py —— R31(第八轮审计 6.1 首步)run_id 事务合同回归锁:
① run_id 顶部生成一次 + 全程传播(SMC_RUN_ID 环境变量 + run_status 携带
   + manifest 同源);
② run_transaction.json 输出索引(run_id/as_of/code_version/config_hash/
   cost_model_version/adx_impl_version/manifest_ok/eligible);
③ 一致性校验: run_status 与 manifest run_id 不一致 → eligible 强制 False;
④ 审计修复要求映射: "每一阶段输出带 run_id/as_of_date/source_hash/
   code_version/config_hash"。
"""
import os, sys, ast

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + str(detail))

src = open(os.path.join(HERE, "daily_combo_run.py"), encoding="utf-8").read()

print("== 1. run_id 生成与传播 ==")
ok("顶部统一生成(_run_main_steps 开头)", '_run_id = "daily-" + time.strftime' in src)
ok("环境变量传播(SMC_RUN_ID)", 'os.environ["SMC_RUN_ID"] = _run_id' in src)
ok("run_status 携带 run_id", '"run_id": _run_id, "code_version": _code_ver, "config_hash": _cfg_hash' in src)
ok("manifest 用同一 _run_id(不再重复生成)", "run_id=_run_id,  # R31(6.1)" in src)
ok("旧式重复生成已删", src.count('"daily-" + time.strftime') == 1, src.count('"daily-" + time.strftime'))
ok("run_id 打印行在", '[run_id] {_run_id}' in src)

print("== 2. code_version / config_hash ==")
ok("code_version = paper_sim sha256[:12]", '_code_ver = _hl.sha256(_f.read()).hexdigest()[:12]' in src)
ok("config_hash = config.py sha256[:12]", '_cfg_hash = _hl.sha256(_f.read()).hexdigest()[:12]' in src)
ok("两者都进 run_status", '"run_id": _run_id, "code_version": _code_ver' in src)

print("== 3. run_transaction.json ==")
ok("transaction 写入在", 'open(os.path.join(RESEARCH, "run_transaction.json"), "w"' in src)
_tx_block = src[src.find("_transaction = {"):]
ok("transaction 含 run_id/as_of/code/config", all(k in _tx_block[:600] for k in
   ('"run_id"', '"as_of_date"', '"code_version"', '"config_hash"')))
ok("transaction 含 cost_model_version(R28)", '"cost_model_version": "COST_V1_FEE_TOTAL_020_SLIP_SIDE_001"' in _tx_block)
ok("transaction 含 adx_impl_version(R22)", '"adx_impl_version": "ADX14_WILDER_20260912"' in _tx_block)
ok("transaction 含 manifest_ok/eligible/consistent", all(k in _tx_block for k in
   ('"manifest_ok"', '"production_eligible"', '"run_id_consistent"')))
ok("transaction 含 artifacts 索引", '"artifacts"' in _tx_block and "run_manifest.json" in _tx_block)
ok("transaction 含 R26 code_watch 标注", '"code_watch"' in _tx_block)

print("== 4. 一致性校验(fail-closed) ==")
ok("run_status run_id 一致性校验在", "_tx_consistent = (_rs_tx.get(\"run_id\") == _run_id)" in src)
ok("不一致 → eligible=False", "_production_eligible = False" in src[src.find("_tx_consistent"):src.find("_tx_consistent")+900])
ok("不一致警告打印在", "[run_tx] ⚠ run_id 不一致" in src)
ok("transaction 打印在", "[run_tx] {_run_id} eligible=" in src)

print("== 5. 审计 6.1 原文要求映射 ==")
# 原文: run_id/as_of_date/source_hash/code_version/config_hash
ok("as_of_date 传入(数据日期)", '"as_of_date": _data_date' in src)
ok("source_hash 由 manifest data_snapshot_id 承担(既有)",
   "data_snapshot_id" in open(os.path.join(HERE, "core", "manifest.py"), encoding="utf-8").read()
   and "data_asof=_data_date, data_snapshot_id=" in src)
ok("code_version/config_hash 顶部算入(新增)", "_code_ver" in src and "_cfg_hash" in src)
ok("下游校验合同注释在(消费产物前校验)", "消费产物前可校验" in src)

print("== 6. 6.1 已有前置(P0-3 冻结生命周期保持) ==")
ok("P0-3 冻结注释保持", "冻结生命周期" in src)
ok("P0-3 成功不回写保持", "成功路径不再回写 run_status.json" in src)
ok("validate_paths 保持(R19)", "if not CFG.validate_paths()" in src)

print("== 7. R12-R30 修复保持 ==")
ok("shadow_replay 调用在(R16)", "shadow_replay" in src)
ok("R26 事故复盘注释在(sim_scheduler 引用)", "R26" in open(os.path.join(HERE, "sim_scheduler.py"), encoding="utf-8").read())
src_ps = open(os.path.join(HERE, "paper_sim.py"), encoding="utf-8").read()
ok("R27 时段守卫仍在", "R27 交易时段守卫" in src_ps)
ok("R8 几何守卫仍在", "BAD_GEOMETRY_FILL_GE_SL" in src_ps)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)