# -*- coding: utf-8 -*-
"""R33: 信号组合粒度审计 — 结论: canonical CSV 不含子信号字段
发现: signal_chain 全量 1527 条均为 'insider-event' (src=EVENT), 无逐信号分解可能。
意义: "不同信号组合的效果差异" 在冻结基线层面**不可分析** ——
      需要 paper_ledger.sub_signals (仅PAPER有) 或重建含组合字段的回测输出。
建议(登记, 未实施): 下次 gen 重跑时在 CSV 增加 sub_signals/rank_components 列,
      以便未来做组合归因。当前禁止为此重跑 canonical (会破坏 139 处消费方的冻结基线)。
"""
import csv, os, sys, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
rows = [r for r in csv.DictReader(open(os.path.join(HERE, "combo_v20f_trades.csv"), encoding="utf-8-sig"))
        if (r.get("buy_price") or "").strip()]
chains = Counter(r.get("signal_chain") or "EMPTY" for r in rows)
srcs = Counter(r.get("src") for r in rows)
res = {
    "n": len(rows),
    "signal_chain_dist": dict(chains),
    "src_dist": dict(srcs),
    "columns": list(rows[0].keys()),
    "conclusion": "canonical CSV 无子信号粒度; 组合级分析需新字段, 冻结期内不可行",
    "paper_ledger_alternative": "paper_ledger.sub_signals 存在但样本<150, 暂不足统计"
}
print(json.dumps({k: v for k, v in res.items() if k != "columns"}, ensure_ascii=False, indent=2))
json.dump(res, open(os.path.join(HERE, "handover", "r33_signal_granularity_audit.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("写出 handover/r33_signal_granularity_audit.json")
