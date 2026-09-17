# -*- coding: utf-8 -*-
"""run_audit_tests.py —— 审计回归测试综合套件(汇总验证).

审计 Iteration 1 验收: 前视断言全通过; Iteration 2: 身份一致;
§10 测试与质量门槛。

统一运行 hermes/scripts 下全部 tests_audit_*.py 回归测试 + 编译检查,
输出逐项 PASS/FAIL 汇总。退出码 0 = 全部通过。

用法: python3 run_audit_tests.py
"""
import io
import os
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

# 全部审计回归测试(按依赖顺序)
TESTS = [
    "tests_audit_weekly_trend.py",          # §6.2 周线合成
    "tests_audit_rolling_lookahead.py",     # §3.4 参数层 look-ahead
    "tests_audit_v500_causality.py",        # §3.1/3.6 V500 因果性
    "tests_audit_v699_visible_target.py",   # §3.7 V699 消费语义
    "tests_audit_signal_time_contract.py",  # §3.3 时间语义
    "tests_audit_exit_cost_model.py",       # §3.5 成本模型
    "tests_audit_future_function.py",       # §3.1 静态检查
    "tests_audit_data_epoch.py",            # §2.2/§3.7 epoch
    "tests_audit_causal_stream.py",         # §3.2/§5.3 事件流
    "tests_audit_stream_vs_v697.py",        # Iter2 身份一致
    "tests_audit_triple_identity.py",       # Iter2 三路一致
    "tests_audit_execution_sim.py",         # §7.4 成交模拟
    "tests_audit_portfolio_sim.py",         # §7.4 组合资金
    "tests_audit_multi_tf.py",              # §6.1/6.2 多周期
    "tests_audit_strategy_contract.py",     # §5.2 合同
    "tests_audit_replay_chain.py",          # §5.1/5.3 端到端
    "tests_audit_research_gate.py",         # §10.3 研究门槛
    "tests_audit_funnel_diagnostic.py",     # §8.1/8.2 漏斗诊断
    "tests_audit_structural_sl_tp.py",      # §7.2/7.3 结构SL/TP
    "tests_audit_fvg_ob_events.py",         # §4.2/4.3 FVG/OB
]

# 本轮新建/修改的核心模块编译检查
COMPILE = [
    "v25/causal_stream.py",
    "v25/replay_chain.py",
    "v25/execution_simulator.py",
    "v25/portfolio_simulator.py",
    "v25/strategy_contract.py",
    "v25/multi_tf.py",
    "v25/data_epoch.py",
    "v11/signals_v11.py",
    "v11/rolling_backtest.py",
    "v11/v44_engine.py",
    "v11/v500_structural_backtest.py",
    "v25/v699_pure_smc_ssl_reclaim_replay.py",
]


def main():
    print("=" * 88)
    print("审计回归测试综合套件 — %d 个测试 + %d 个核心模块编译检查"
          % (len(TESTS), len(COMPILE)))
    print("=" * 88)

    # 1. 编译检查
    print("\n[1/2] 编译检查(核心模块 + 全量 compileall)")
    compile_fail = 0
    # 1a. 核心模块逐个 py_compile
    for mod in COMPILE:
        p = os.path.join(HERE, mod)
        r = subprocess.run([PY, "-m", "py_compile", p],
                           capture_output=True, text=True, encoding="utf-8")
        status = "OK" if r.returncode == 0 else "FAIL"
        if r.returncode != 0:
            compile_fail += 1
        print("  %-8s %s" % (status, mod))

    # 1b. 全量 compileall(审计 §11 验收: 整包编译通过)
    r_all = subprocess.run([PY, "-m", "compileall", "-q", HERE],
                           capture_output=True, text=True, encoding="utf-8")
    if r_all.returncode != 0:
        compile_fail += 1
    print("  %-8s hermes/scripts 全量 compileall(审计§11)"
          % ("OK" if r_all.returncode == 0 else "FAIL"))

    # 2. 回归测试
    print("\n[2/2] 回归测试(逐个运行, 收集 PASS/FAIL)")
    results = []
    for t in TESTS:
        p = os.path.join(HERE, t)
        r = subprocess.run([PY, "-X", "utf8", p],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=180)
        passed = r.returncode == 0
        # 从输出提取 PASS/FAIL 计数
        n_pass = n_fail = 0
        for line in r.stdout.split("\n"):
            if "结果: PASS=" in line:
                import re
                m = re.search(r"PASS=(\d+) FAIL=(\d+)", line)
                if m:
                    n_pass, n_fail = int(m.group(1)), int(m.group(2))
        results.append((t, passed, n_pass, n_fail))
        status = "PASS" if passed else "FAIL"
        print("  %-6s %-42s (PASS=%d FAIL=%d)" % (status, t, n_pass, n_fail))
        if not passed:
            # 打印失败详情尾部
            tail = [l for l in (r.stdout + r.stderr).split("\n") if "FAIL" in l]
            for line in tail[:3]:
                print("        " + line.strip())

    # 汇总
    print("\n" + "=" * 88)
    total_pass = sum(n for _, _, n, _ in results)
    total_fail = sum(n for _, _, _, n in results)
    tests_ok = sum(1 for _, ok, _, _ in results if ok)
    print("测试: %d/%d 通过 | 断言 PASS=%d FAIL=%d | 编译失败=%d"
          % (tests_ok, len(TESTS), total_pass, total_fail, compile_fail))
    print("=" * 88)
    ok_all = tests_ok == len(TESTS) and compile_fail == 0 and total_fail == 0
    print("总判定: %s" % ("✅ 全部通过" if ok_all else "❌ 有失败项"))
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()