# -*- coding: utf-8 -*-
"""r38_event_expand.py —— R38 事件腿扩池探查: 公告类型供给与质量.

背景: 事件腿供给仅 1.1%(10151/98万), 是"选股量少"的根因。技术腿路线
经 OOS 检验已否决(R38h)。本脚本回到事件腿内部找扩池空间:
  ① 统计公告库中各事件类型的真实供给量(股权激励/业绩预告/大宗交易/
     股东增持/回购/员工持股/中标合同等)
  ② 对每类抽样核查 classify_title 的当前判定(是否被硬否/软否漏掉)
  ③ 给出可扩池的候选类型清单 + 增量规模估算

只做供给端探查, 不做收益回测(下一步在冻结基线口径下验证)。
纯研究, 不修改生产。
"""
import io, re, sqlite3, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
from core.events import classify_title

conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
cur.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM announce")
total, dmin, dmax = cur.fetchone()
print("="*92)
print(f"公告库: {total} 条, {dmin} ~ {dmax}")
print("="*92)

# ---- 候选事件类型关键词 ----
PATTERNS = {
    "股东增持":      r"增持",
    "股份回购":      r"回购",
    "股权激励":      r"股权激励|限制性股票|股票期权",
    "员工持股":      r"员工持股",
    "业绩预告":      r"业绩预告|业绩预增|业绩预减|业绩快报",
    "大宗交易":      r"大宗交易",
    "中标合同":      r"中标|合同|订单",
    "重大重组":      r"重大资产重组|收购|兼并",
    "定增":          r"非公开发行|向特定对象发行",
    "解禁减持":      r"减持|限售股上市流通",
    "分红送转":      r"分红|派息|转增",
    "诉讼风险":      r"诉讼|仲裁|处罚|立案|风险提示",
    "停牌退市":      r"停牌|退市|终止上市",
}
print(f"{'类型':<12}{'关键词命中':>10}{'其中正事件':>11}{'正事件占比':>11}{'样本标题':<50}")
print("-"*92)
rows_cache = {}
for name, pat in PATTERNS.items():
    cur.execute("SELECT COUNT(*) FROM announce WHERE date >= '2023-09-01' AND title LIKE ?", (f"%{pat.split('|')[0]}%",))
    hit = cur.fetchone()[0]
    cur.execute("SELECT title FROM announce WHERE date >= '2023-09-01' AND title LIKE ? LIMIT 3000", (f"%{pat.split('|')[0]}%",))
    titles = [r[0] for r in cur.fetchall()]
    pos = 0
    for t in titles:
        try:
            is_ev, kind, pol, _a, _p = classify_title(t)
        except Exception:
            continue
        if is_ev and pol > 0:
            pos += 1
    pct = f"{100*pos/len(titles):.1f}%" if titles else "-"
    sample = (titles[0][:46] if titles else "")
    print(f"{name:<12}{hit:>10}{pos:>11}{pct:>11}  {sample}")
    rows_cache[name] = titles

print("\n" + "="*92)
print("classify_title 对候选类型的判定分布(pol: >0正事件 / 0中性 / <0负事件):")
print("-"*92)
for name in ("股权激励", "业绩预告", "大宗交易", "中标合同", "定增"):
    dist = defaultdict(int)
    kinds = defaultdict(int)
    for t in rows_cache.get(name, []):
        try:
            is_ev, kind, pol, _a, _p = classify_title(t)
        except Exception:
            continue
        dist[pol] += 1
        kinds[kind] += 1
    print(f"  {name:<10} pol分布={dict(sorted(dist.items()))}  kind={dict(kinds)}")

print("\n" + "="*92)
print("结论方向:")
print("  · 上表'其中正事件'列 = 若直接把该类加入事件腿, 可获得的增量候选量级")
print("  · pol=0 的类型需要新增分类规则(而非放宽现有正事件判定), 否则会混入噪声")
print("  · 下一步: 对增量最大的 1-2 类, 在冻结基线口径下做收益验证(含 OOS)")