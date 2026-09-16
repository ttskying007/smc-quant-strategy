# -*- coding: utf-8 -*-
"""r38_gate_funnel_deep.py —— 深挖今日(09-17)选股漏斗, 确认 rank 门槛状态.

背景: selection_funnel.json 已更新到 09-17 00:00:09(daily 完成), 但表面无
RANK_LT 痕迹。需区分两种可能:
  A. 今日候选全部 rank>=3, 门槛无事可做(正常)
  B. 门槛代码未生效(异常)

检查路径:
  ① 漏斗完整结构(generated_at/计数键)
  ② reject_by_reason / terminal_stage_counts 中与 rank/skipped 相关计数
  ③ reject_ledger.json 今日新增记录的 stage 分布(是否含 RANK_LT)
  ④ 对照: skipped_stage/skipped_adx 等既有拒绝是否正常出现(验证漏斗本身在记)
纯只读, 不修改生产。
"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = r"E:\test\smc_project\research"


def show(path, depth=0, max_depth=2, key_path=""):
    if not os.path.exists(path):
        print("  %s MISSING" % path)
        return
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        print("  %s parse err: %s" % (path, e))
        return
    print("=== %s (%s bytes) ===" % (path, os.path.getsize(path)))
    if isinstance(d, dict):
        for k, v in d.items():
            if isinstance(v, (dict, list)) and depth < max_depth:
                print("  [%s] %s: %s items" % (key_path, k, len(v)))
                show_v(v, depth + 1, key_path + "/" + k)
            else:
                sv = str(v)
                print("  [%s] %s = %s" % (key_path, k, sv[:120]))


def show_v(v, depth, kp):
    if isinstance(v, dict):
        for k, x in v.items():
            if isinstance(x, (dict, list)) and depth < 3:
                print("    " * depth + "[%s] %s: %d items" % (kp, k, len(x)))
                show_v(x, depth + 1, kp + "/" + k)
            else:
                print("    " * depth + "[%s] %s = %s" % (kp, k, str(x)[:100]))
    elif isinstance(v, list):
        for i, x in enumerate(v[:5]):
            print("    " * depth + "[%s][%d] = %s" % (kp, i, str(x)[:120]))


print("=" * 90)
print("今日选股漏斗深挖 (09-17 00:00:09)")
print("=" * 90)
show(os.path.join(HERE, "selection_funnel.json"))

print("\n" + "=" * 90)
print("reject_ledger 今日记录")
print("=" * 90)
p = os.path.join(HERE, "reject_ledger.json")
if os.path.exists(p):
    d = json.load(open(p, encoding="utf-8"))
    items = d if isinstance(d, list) else d.get("records", d.get("rejects", []))
    print("records n=%d" % (len(items) if isinstance(items, list) else "?"))
    if isinstance(items, list) and items:
        # 只看最近的(今日)
        stages = {}
        for it in items:
            if isinstance(it, dict):
                st = str(it.get("stage") or it.get("reason") or "?")
                stages[st] = stages.get(st, 0) + 1
        print("stage 分布(全部): %s" % stages)
        # 找 RANK 相关
        rank_hits = [it for it in items if isinstance(it, dict)
                     and ("RANK" in str(it.get("stage") or "").upper()
                          or "RANK" in str(it.get("reason") or "").upper())]
        print("含 RANK 记录数: %d" % len(rank_hits))
        for it in rank_hits[:5]:
            print("  ", {k: it.get(k) for k in ("code", "date", "stage", "reason", "rank_score")
                         if k in it})

print("\n" + "=" * 90)
print("对照: 既有拒绝(skipped_stage/skipped_adx)是否正常出现在漏斗")
print("=" * 90)
d = json.load(open(os.path.join(HERE, "selection_funnel.json"), encoding="utf-8"))
s = json.dumps(d, ensure_ascii=False)
for k in ("skipped_stage", "skipped_adx", "skipped_rank", "RANK_LT", "terminal_stage_counts",
          "reject_by_reason", "tri_decompose"):
    print("  %-22s present=%s" % (k, k in s))