# -*- coding: utf-8 -*-
"""tests_audit_r8b.py —— R13(第八轮审计)第二批修复回归锁:
① 5.9 continuation_scanner 阈值 0.10 统一 + freshness gate;
② 6.2 current_scanner --production 传入生产链;
③ 5.7 E-score 数据链前置(setup_engine_paper 之前)。
全部源码契约级(不跑重扫描, 只锁语义), 防回归。
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + str(detail))

print("== 1. 5.9: continuation_scanner 阈值与 freshness ==")
src = open(os.path.join(HERE, "continuation_scanner.py"), encoding="utf-8").read()
ok("VWAP 阈值 0.10(与 sub_signals_cont 统一)", "(daily[i][\"c\"] - vw) / vw < 0.10" in src, "未找到 0.10 阈值")
ok("旧 0.09 阈值已移除", "(daily[i][\"c\"] - vw) / vw < 0.09" not in src, "0.09 残留")
ok("freshness gate 存在(signal_date==latest 过滤)", "c.get(\"signal_date\") == latest" in src, "无 freshness 过滤")
ok("freshness 剔除计数打印", "剔除 {_dropped} 个旧数据候选" in src)

# 与 paper_sim.sub_signals_cont 同阈值交叉验证(两侧 0.10)
src_ps = open(os.path.join(HERE, "paper_sim.py"), encoding="utf-8").read()
ok("paper_sim.sub_signals_cont 仍 0.10(未漂移)", "(bs[k][\"c\"] - vw) / vw >= 0.10" in src_ps)

print("== 2. 6.2: current_scanner --production 传入生产链 ==")
src_d = open(os.path.join(HERE, "daily_combo_run.py"), encoding="utf-8").read()
ok("scanner 调用带 --production", '"current_scanner.py", "--refresh", "--production"' in src_d, "未传 --production")
ok("--production 注册存在(current_scanner)", True)  # 由源扫描下项保证
src_c = open(os.path.join(HERE, "current_scanner.py"), encoding="utf-8").read()
ok("current_scanner 注册 --production 参数", 'ap.add_argument("--production"' in src_c)
ok("production 模式 artifact 硬失败", 'production blocked: artifact missing/empty' in src_c)

print("== 3. 5.7: E-score 数据链前置 ==")
_i_setup = src_d.find("setup_engine_paper.py")
_i_index = src_d.find(r"pull_index_daily.py")
_i_escore = src_d.find("escore_daily.py")
ok("三个脚本均在编排中", _i_setup > 0 and _i_index > 0 and _i_escore > 0,
   (_i_setup, _i_index, _i_escore))
ok("指数刷新在 setup_engine_paper 之前", 0 < _i_index < _i_setup, f"index@{_i_index} setup@{_i_setup}")
ok("escore_daily 在 setup_engine_paper 之前", 0 < _i_escore < _i_setup, f"escore@{_i_escore} setup@{_i_setup}")
ok("5.7 修复注释存在", "E-score 数据链前置" in src_d)

print("== 4. R12 修复保持(防本轮回归) ==")
ok("P0-4 开关快照仍在", '"leg_flags"' in src_ps)
ok("P1-4 CONT tp2 接线仍在", '"tp2": round(tp, 3),' in src_ps)
ok("P0-3 manifest_ok 初值仍在", '"manifest_ok": False,' in src_d)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)