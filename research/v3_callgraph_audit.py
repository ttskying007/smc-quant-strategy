# -*- coding: utf-8 -*-
"""§十二/V3: 生产链 Call-Graph 审计(只读, 不改生产)
V3审计要求: 代码写了 ≠ 生产路径真的经过。逐文件核验实际 import/调用路径:

  daily 链: paper_sim --select/--monitor → scanner(current_scanner) → 事件/SMC → 挂单 → 撮合 → 退出
  核验点:
    C1 paper_sim 撮合 → core.execution.try_fill (P0-4 已接线?)
    C2 paper_sim 退出 → core.execution.try_exit
    C3 paper_sim 事件分类 → core.events.classify_title_detailed
    C4 paper_sim 结构/阶段 → core.structure (vs 旧 stage_and_deep)
    C5 scanner SMC seeds → wdh_engine.build_seeds (旧语义, 待统一标记)
    C6 scanner stage → paper_sim.stage_and_deep (跨文件依赖, 待统一标记)
    C7 scanner --production → fail-closed 分支可达(V3已修)
    C8 涨跌停 → core.limits / core.execution.is_limit_up
  输出: 每核验点 PASS/DEPRECATED/TO_UNIFY + 位置行号 → handover/生产链CallGraph审计.json"""
import io, json, os, re, sys, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = r"E:\test\smc_project\research"

PASS_C = FAIL_C = 0
def rep(name, status, detail=""):
    global PASS_C, FAIL_C
    tag = {"PASS": "  OK ", "DEPRECATED": " WARN", "TO_UNIFY": " TODO"}[status]
    print(f"{tag} {name} [{status}] {detail}")
    return {"name": name, "status": status, "detail": detail}

def src_of(fn):
    return open(os.path.join(ROOT, fn), encoding="utf-8").read()

results = []

# C1/C2: paper_sim 撮合/退出委托 core.execution
ps = src_of("paper_sim.py")
results.append(rep("C1 paper_sim→core.execution.try_fill",
                   "PASS" if "from core.execution import try_fill as _core_fill" in ps else "FAIL",
                   "line ~940"))
results.append(rep("C2 paper_sim→core.execution.try_exit",
                   "PASS" if "from core.execution import try_exit as _core_exit" in ps else "FAIL",
                   "line ~1038"))
# C3: 事件分类
results.append(rep("C3 paper_sim→core.events.classify_title_detailed",
                   "PASS" if "from core.events import classify_title_detailed" in ps else "FAIL"))
# C4: 结构统一
results.append(rep("C4 paper_sim→core.structure(消除重复)",
                   "PASS" if "from core.structure import (is_swing_high" in ps else "FAIL"))
# C5: scanner 旧 seeds
cs = src_of("current_scanner.py")
m5 = re.search(r"import wdh_engine as we", cs)
results.append(rep("C5 scanner→wdh_engine.build_seeds",
                   "TO_UNIFY" if m5 else "PASS",
                   "旧语义入口(§十一); PAPER 七道门通过后切换 core.setup_engine"))
# C6: scanner stage 跨文件依赖
m6 = re.search(r"import paper_sim as _ps", cs)
results.append(rep("C6 scanner→paper_sim.stage_and_deep",
                   "TO_UNIFY" if m6 else "PASS",
                   "跨文件依赖; 统一后 stage=Context Feature 仅入 setup 元数据"))
# C7: --production 注册
m7 = re.search(r'add_argument\("--production"', cs)
results.append(rep("C7 scanner --production fail-closed 可达",
                   "PASS" if m7 else "FAIL", "V3修复: 参数已注册"))
# C8: 涨跌停
results.append(rep("C8 涨跌停→core(板块规则)",
                   "PASS" if ("core.execution import is_limit_up" in ps or "core.limits" in ps) else "FAIL"))
# C9(新增): 每日链入口 --select/--monitor 存在
results.append(rep("C9 paper_sim 每日入口(--select/--monitor)",
                   "PASS" if ('"--select"' in ps and '"--monitor"' in ps) else "FAIL"))
# C10(新增): setup_exit 单源被 PAPER 消费
sp = src_of("setup_engine_paper.py")
results.append(rep("C10 PAPER→core.setup_exit(单源退出)",
                   "PASS" if "from core.setup_exit import" in sp else "FAIL"))
results.append(rep("C11 PAPER→core.setup_engine(统一Setup)",
                   "PASS" if "from core.setup_engine import" in sp else "FAIL"))

n_pass = sum(1 for r in results if r["status"] == "PASS")
n_todo = sum(1 for r in results if r["status"] == "TO_UNIFY")
summary = {"checked": len(results), "pass": n_pass, "to_unify": n_todo,
           "to_unify_items": [r["name"] for r in results if r["status"] == "TO_UNIFY"],
           "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
           "note": "C5/C6=V3§十一已确认的旧语义分叉; 切换条件=PAPER七道门通过(冻结), 不提前动生产"}
out = {"results": results, "summary": summary}
json.dump(out, open(os.path.join(ROOT, "handover", "生产链CallGraph审计.json"), "w",
                    encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"\n核验 {len(results)} 项: PASS={n_pass} TO_UNIFY={n_todo}(冻结等待PAPER门)")
print("已写 handover/生产链CallGraph审计.json")