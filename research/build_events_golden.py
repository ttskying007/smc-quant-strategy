# -*- coding: utf-8 -*-
"""P2: 事件分类黄金标注集构建 —— 从公告DB分层抽样真实标题。
输出 tests_events_golden_data.py 内容(逐条: title→期望四元组+layer)。
标注原则(按分类器当前已验证语义, 人工逐条核):
  - 回购/增持首次公告(含金额/比例) → EVENT+1
  - 减持/终止/取消/解除/结束 → HARD_REJECT
  - 软否(完毕/届满/进展/结果/完成/进度/调整/变更/补充协议/前十名/草案)无增量 → SOFT_REJECT
  - 软否+回购/增持+金额/比例增量 → PROGRESS_WITH_DELTA(A/B已验证纳入)
  - 非回购/增持标题 → NO_EVENT
"""
import io, json, random, sqlite3, sys
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from core.events import classify_title_detailed

DB = r"E:\test\smc_project\announce\smc_announce.db"
random.seed(20260908)
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT DISTINCT title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%' LIMIT 20000")
all_titles = [t[0] for t in cur.fetchall()]
conn.close()
print(f"总标题: {len(all_titles)}")

# 分层桶(按 detailed layer)
buckets = {"EVENT": [], "HARD_REJECT": [], "SOFT_REJECT": [], "PROGRESS_WITH_DELTA": [], "NO_EVENT": []}
for t in all_titles:
    try:
        _is, _k, _p, _a, _pc, layer = classify_title_detailed(t)
    except Exception:
        continue
    buckets.setdefault(layer if layer in buckets else "NO_EVENT", []).append(t)

# 无事件类(标题不含回购/增持) —— 另抽
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT DISTINCT title FROM announce WHERE title NOT LIKE '%增持%' AND title NOT LIKE '%回购%' AND (title LIKE '%减持%' OR title LIKE '%终止%' OR title LIKE '%业绩%' OR title LIKE '%利润%') LIMIT 2000")
neg_titles = [t[0] for t in cur.fetchall()]
conn.close()
print(f"反向/无关标题: {len(neg_titles)}")

# 抽样: 每层最多12条, 反向 8 条 —— 共 ≤60 条黄金集
samples = []
for layer, ts in buckets.items():
    random.shuffle(ts)
    samples.extend(ts[:12])
random.shuffle(neg_titles)
samples.extend(neg_titles[:8])

# 人工标注 = 分类器当前输出(逐条打印供核) + 锁定期望
print("\n== 黄金集候选(逐条, 标注供人工核对) ==")
golden = []
for t in samples:
    t = str(t).strip()
    if not t or len(t) < 6:
        continue
    is_ev, kind, pol, amt, pct, layer = classify_title_detailed(t)
    is_ev2, kind2, pol2, amt2, pct2 = (classify_title_detailed(t)[0:5]) if layer == "EVENT" else (False, None, 0, None, None)
    golden.append({"title": t, "layer": layer, "kind": kind, "pol": pol,
                   "amt": amt, "pct": pct})
    print(f"  [{layer:20s}] {kind} pol={pol} amt={amt} pct={pct} | {t[:46]}")

with open(r"E:\test\smc_project\research\handover\事件分类黄金集.json", "w", encoding="utf-8") as fh:
    json.dump(golden, fh, ensure_ascii=False, indent=2)
print(f"\n黄金集: {len(golden)} 条 → handover/事件分类黄金集.json")
print("下一步: 人工核对后生成 tests_events_golden.py 锁定回归")